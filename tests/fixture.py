"""Generate an ephemeral test certificate, or load an explicitly supplied DER file."""
from pathlib import Path
import subprocess
import tempfile


def load_fixture(path=None):
    if path:
        data = Path(path).read_bytes()
    else:
        with tempfile.TemporaryDirectory(prefix="d2p-fixture-") as tmp:
            cert = Path(tmp) / "test.der"
            subprocess.run([
                "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                "-keyout", str(Path(tmp) / "test.key"), "-out", str(cert),
                "-outform", "DER", "-days", "1", "-subj", "/CN=DER2PEM disposable test CA",
            ], check=True, capture_output=True)
            data = cert.read_bytes()
    result = subprocess.run([
        "openssl", "x509", "-inform", "DER", "-subject_hash_old", "-noout",
    ], input=data, capture_output=True, check=True)
    subject_hash = result.stdout.decode().strip()
    assert len(subject_hash) == 8 and all(c in "0123456789abcdef" for c in subject_hash)
    return data, subject_hash
