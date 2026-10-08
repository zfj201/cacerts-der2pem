from pathlib import Path
import subprocess,shlex,sys,os
from fixture import load_fixture
fixture, subject_hash = load_fixture(sys.argv[1] if len(sys.argv) > 1 else None)
root=Path(__file__).resolve().parents[1];out=root/'tests/results';out.mkdir(exist_ok=True);adb=['adb'] + (['-s', os.environ['ANDROID_SERIAL']] if os.environ.get('ANDROID_SERIAL') else [])
def remote(s,timeout=30):return subprocess.run(adb+['shell','su -c '+shlex.quote(s)],capture_output=True,text=True,timeout=timeout)
r=remote('mktemp -d /data/local/tmp/d2p-v2-mount-test.XXXXXXXX');r.check_returncode();d=r.stdout.strip();assert d.startswith('/data/local/tmp/d2p-v2-mount-test.')
def send(name,b):subprocess.run(adb+['exec-in','su -c '+shlex.quote('cat > '+shlex.quote(d+'/'+name))],input=b,capture_output=True,check=True)
try:
 service=(root/'service.sh').read_text().replace('for live in /system/etc/security/cacerts /apex/com.android.conscrypt/cacerts; do',f'for live in {d}/live; do').replace('  sleep 60','  break # one test iteration only')
 send('service.sh',service.encode());send('certtool.jar',(root/'certtool.jar').read_bytes());send('cert.der',fixture)
 send('metadata-fail-service.sh',service.replace('umask 077','umask 077\nchcon() { return 1; } # test-only fault injection').encode())
 script='''
set -e
D=__DIR__
BB=/data/adb/ksu/bin/busybox
# This script is launched only in an unshared mount namespace.
$BB mount --make-rprivate /
mkdir "$D/live" "$D/alias"
$BB mount -t tmpfs -o mode=0755 tmpfs "$D/live"
$BB mount --bind "$D/live" "$D/alias"
cp "$D/cert.der" "$D/live/__HASH__.0"
/system/bin/sh "$D/service.sh"
export CLASSPATH="$D/certtool.jar"
/system/bin/app_process /system/bin CertTool verify "$D/alias"
cmp "$D/live/__HASH__.0" "$D/alias/__HASH__.0"
echo SHARED_DIRECTORY_REPLACEMENT_PASSED
cat "$D/runtime/service.log"
# Metadata failure must leave original DER unchanged.
cp "$D/cert.der" "$D/live/__HASH__.0"
/system/bin/sh "$D/metadata-fail-service.sh"
cmp "$D/live/__HASH__.0" "$D/cert.der"
echo METADATA_FAILURE_PRESERVES_ORIGINAL
# Individual bind mount must never be replaced.
$BB mount --bind "$D/live/__HASH__.0" "$D/live/__HASH__.0"
/system/bin/sh "$D/service.sh"
cmp "$D/live/__HASH__.0" "$D/cert.der"
grep 'Refusing individual file mount' "$D/runtime/commit.log"
echo FILE_MOUNT_REFUSAL_PASSED
$BB umount "$D/live/__HASH__.0"
# A directly read-only tmpfs must not be selected by service.sh.
$BB mount -o remount,ro "$D/live"
/system/bin/sh "$D/service.sh"
cmp "$D/live/__HASH__.0" "$D/cert.der"
echo READONLY_PRESERVES_ORIGINAL
'''.replace('__DIR__',shlex.quote(d)).replace('__HASH__', subject_hash)
 send('mount-test.sh',script.encode())
 r=remote('/data/adb/ksu/bin/busybox unshare -m /system/bin/sh '+shlex.quote(d+'/mount-test.sh'),90)
 (out/'android-isolated-mount-tests.txt').write_text(r.stdout+'\nSTDERR\n'+r.stderr)
 print('returncode',r.returncode);print(r.stdout);print(r.stderr);r.check_returncode()
finally:
 r=remote('rm -rf '+shlex.quote(d));r.check_returncode()
