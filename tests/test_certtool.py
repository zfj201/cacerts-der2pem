"""Run meaningful failure/isolation tests on the host; no device access."""
from pathlib import Path
import subprocess,tempfile,shutil,hashlib,sys,json
root=Path(__file__).resolve().parents[1]
from fixture import load_fixture
fixture, subject_hash = load_fixture(sys.argv[1] if len(sys.argv) > 1 else None)
with tempfile.TemporaryDirectory(prefix='d2p-test-') as tmp:
 t=Path(tmp); classes=t/'classes';classes.mkdir()
 subprocess.run(['javac','--release','8','-d',str(classes),str(root/'src/CertTool.java')],check=True)
 def call(*args,ok=True):
  r=subprocess.run(['java','-cp',str(classes),'CertTool',*map(str,args)],capture_output=True,text=True)
  assert (r.returncode==0)==ok,(args,r.stdout,r.stderr)
  return r
 def case(name):
  p=t/name;p.mkdir();(p/'live').mkdir();(p/'stage').mkdir();return p/'live',p/'stage'
 name=subject_hash+'.0'
 live,stage=case('normal');(live/name).write_bytes(fixture);(live/(subject_hash+'.10')).write_bytes(fixture)
 old_inode=(live/name).stat().st_ino
 call('prepare',live,stage);assert (live/name).read_bytes()==fixture
 call('commit',live,stage);assert (live/name).stat().st_ino!=old_inode
 call('verify',live)
 pem=(live/name).read_bytes();r=subprocess.run(['openssl','x509','-inform','PEM','-outform','DER'],input=pem,capture_output=True,check=True);assert r.stdout==fixture
 again=t/'again';again.mkdir();call('prepare',live,again);assert not list((again/'pem').iterdir())
 live,stage=case('invalid');(live/name).write_bytes(b'0garbage');call('prepare',live,stage,ok=False);assert (live/name).read_bytes()==b'0garbage'
 live,stage=case('truncated');(live/name).write_bytes(fixture[:100]);call('prepare',live,stage,ok=False);assert (live/name).read_bytes()==fixture[:100]
 live,stage=case('trailing');(live/name).write_bytes(fixture+b'extra');call('prepare',live,stage,ok=False)
 live,stage=case('wrong_hash');(live/'aaaaaaaa.0').write_bytes(fixture);call('prepare',live,stage,ok=False)
 live,stage=case('symlink');outside=t/'outside';outside.write_bytes(fixture);(live/name).symlink_to(outside);call('prepare',live,stage,ok=False);assert outside.read_bytes()==fixture
 live,stage=case('source_changed');(live/name).write_bytes(fixture);call('prepare',live,stage);(live/name).write_bytes(pem);call('commit',live,stage,ok=False);assert (live/name).read_bytes()==pem
 live,stage=case('stage_corrupt');(live/name).write_bytes(fixture);call('prepare',live,stage);(stage/'pem'/name).write_bytes(b'-----BEGIN CERTIFICATE-----\nMII=\n-----END CERTIFICATE-----\n');call('commit',live,stage,ok=False);assert (live/name).read_bytes()==fixture
 live,stage=case('empty');call('verify',live,ok=False)
 print('PASS: normal roundtrip, multi-digit suffix, inode replacement, idempotence, invalid/truncated/trailing DER, wrong hash, symlink, concurrent change, corrupt staged output, empty store')
