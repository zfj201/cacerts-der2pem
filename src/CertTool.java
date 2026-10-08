import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.*;
import java.security.cert.*;
import java.util.*;
import java.util.regex.*;

/** Android API 26+. No network, key material, or trust-store policy changes. */
public final class CertTool {
    static final Pattern NAME = Pattern.compile("[0-9a-f]{8}\\.[0-9]+");
    static final Pattern PEM = Pattern.compile("-----BEGIN CERTIFICATE-----([A-Za-z0-9+/=\\r\\n\\t ]+)-----END CERTIFICATE-----");
    static final int LIMIT = 1024 * 1024;
    static byte[] read(Path p) throws Exception {
        if (Files.isSymbolicLink(p) || !Files.isRegularFile(p, LinkOption.NOFOLLOW_LINKS))
            throw new IOException("Not a regular non-symlink file: " + p);
        long size = Files.size(p);
        if (size <= 0 || size > LIMIT) throw new IOException("Invalid certificate size: " + p);
        byte[] b = Files.readAllBytes(p);
        if (b.length > LIMIT) throw new IOException("Certificate grew beyond limit: " + p);
        return b;
    }
    static String hex(byte[] b) {
        StringBuilder s = new StringBuilder();
        for (byte v : b) s.append(String.format(Locale.ROOT, "%02x", v & 255));
        return s.toString();
    }
    static String digest(byte[] b) throws Exception { return hex(MessageDigest.getInstance("SHA-256").digest(b)); }
    static final class Cert {
        final byte[] der;
        final String fingerprint, hash;
        final boolean wasPem;
        Cert(byte[] raw) throws Exception {
            wasPem = raw[0] != 0x30;
            byte[] bytes = raw;
            if (wasPem) {
                String text = new String(raw, StandardCharsets.US_ASCII);
                Matcher m = PEM.matcher(text);
                if (!m.find()) throw new CertificateException("No complete PEM certificate");
                bytes = Base64.getDecoder().decode(m.group(1).replaceAll("\\s", ""));
                if (m.find()) throw new CertificateException("Multiple certificates in one hash file");
            }
            ByteArrayInputStream in = new ByteArrayInputStream(bytes);
            X509Certificate cert = (X509Certificate) CertificateFactory.getInstance("X.509").generateCertificate(in);
            der = cert.getEncoded();
            if (in.available() != 0 || !Arrays.equals(bytes, der))
                throw new CertificateException("Trailing data or non-canonical DER");
            fingerprint = digest(der);
            byte[] md5 = MessageDigest.getInstance("MD5").digest(cert.getSubjectX500Principal().getEncoded());
            hash = String.format(Locale.ROOT, "%02x%02x%02x%02x", md5[3]&255, md5[2]&255, md5[1]&255, md5[0]&255);
        }
        byte[] pem() {
            return ("-----BEGIN CERTIFICATE-----\n" + Base64.getMimeEncoder(64, new byte[]{10}).encodeToString(der)
                    + "\n-----END CERTIFICATE-----\n").getBytes(StandardCharsets.US_ASCII);
        }
    }
    static List<Path> certs(Path dir) throws Exception {
        if (Files.isSymbolicLink(dir) || !Files.isDirectory(dir)) throw new IOException("Invalid directory: " + dir);
        List<Path> files = new ArrayList<>();
        try (DirectoryStream<Path> ds = Files.newDirectoryStream(dir)) {
            for (Path p : ds) if (NAME.matcher(p.getFileName().toString()).matches()) files.add(p);
        }
        Collections.sort(files);
        return files;
    }
    static void checkName(Path p, Cert c) throws Exception {
        if (!p.getFileName().toString().startsWith(c.hash + "."))
            throw new CertificateException("subject_hash_old mismatch: " + p.getFileName() + " expected " + c.hash);
    }
    static void writeNew(Path p, byte[] b) throws Exception {
        try (FileOutputStream out = new FileOutputStream(Files.createFile(p).toFile())) {
            out.write(b); out.getFD().sync();
        }
        if (!Arrays.equals(read(p), b)) throw new IOException("Staged write mismatch: " + p);
    }
    static void prepare(Path live, Path stage) throws Exception {
        Files.createDirectory(stage.resolve("originals"));
        Files.createDirectory(stage.resolve("pem"));
        int count = 0, checked = 0;
        for (Path p : certs(live)) {
            byte[] raw = read(p); Cert c = new Cert(raw); checkName(p, c); checked++;
            if (c.wasPem) continue;
            byte[] encoded = c.pem(); Cert again = new Cert(encoded);
            if (!Arrays.equals(c.der, again.der)) throw new CertificateException("Conversion changed certificate");
            Path name = p.getFileName();
            writeNew(stage.resolve("originals").resolve(name), raw);
            writeNew(stage.resolve("pem").resolve(name), encoded);
            System.out.println("CANDIDATE " + name + " " + c.fingerprint); count++;
        }
        if (checked == 0) throw new IOException("No certificates found");
        System.out.println("PREPARED checked=" + checked + " conversions=" + count);
    }
    static boolean fileMount(Path p) throws Exception {
        Path mi = Paths.get("/proc/self/mountinfo");
        if (!Files.exists(mi)) return false; // Host-side fixture tests only.
        String target = p.toAbsolutePath().toString();
        for (String line : Files.readAllLines(mi, StandardCharsets.UTF_8)) {
            String[] fields = line.split(" ");
            if (fields.length > 5 && fields[4].equals(target)) return true;
        }
        return false;
    }
    static void commit(Path live, Path stage) throws Exception {
        int count = 0;
        for (Path p : certs(stage.resolve("pem"))) {
            Path name = p.getFileName(), dest = live.resolve(name), original = stage.resolve("originals").resolve(name);
            byte[] old = read(original), replacement = read(p);
            Cert c = new Cert(replacement); checkName(dest, c);
            if (!c.wasPem || !Arrays.equals(new Cert(old).der, c.der)) throw new IOException("Staged certificate mismatch");
            if (fileMount(dest)) throw new IOException("Refusing individual file mount: " + dest);
            if (!Arrays.equals(read(dest), old)) throw new IOException("Source changed; retry next scan: " + dest);
            // No fallback to copy/truncate; a failed atomic move leaves the live file intact.
            Files.move(p, dest, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
            if (!Arrays.equals(read(dest), replacement)) throw new IOException("Post-commit mismatch: " + dest);
            System.out.println("CONVERTED " + name + " " + c.fingerprint); count++;
        }
        System.out.println("COMMITTED " + count);
    }
    static void verify(Path dir) throws Exception {
        int count = 0, der = 0;
        for (Path p : certs(dir)) {
            Cert c = new Cert(read(p)); checkName(p, c);count++;
            if (!c.wasPem) der++;
            System.out.println((c.wasPem ? "PEM " : "DER ") + p.getFileName() + " " + c.fingerprint);
        }
        if (count == 0) throw new IOException("No certificates found");
        System.out.println("VERIFIED count=" + count + " der=" + der);
        if (der != 0) throw new IOException("DER certificates remain");
    }
    public static void main(String[] args) {
        try {
            if (args.length == 2 && args[0].equals("verify")) verify(Paths.get(args[1]));
            else if (args.length == 3 && args[0].equals("prepare")) prepare(Paths.get(args[1]), Paths.get(args[2]));
            else if (args.length == 3 && args[0].equals("commit")) commit(Paths.get(args[1]), Paths.get(args[2]));
            else throw new IllegalArgumentException("Usage: verify DIRECTORY | prepare/commit DIRECTORY STAGE");
        } catch (Exception e) { System.err.println("ERROR " + e); System.exit(1); }
    }
}
