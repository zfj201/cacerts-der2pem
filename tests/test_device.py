import subprocess,shlex,json,sys,os
from pathlib import Path
from fixture import load_fixture
fixture, subject_hash = load_fixture(sys.argv[1] if len(sys.argv) > 1 else None)
root=Path(__file__).resolve().parents[1];out=root/'tests/results';out.mkdir(exist_ok=True)
adb=['adb'] + (['-s', os.environ['ANDROID_SERIAL']] if os.environ.get('ANDROID_SERIAL') else [])
def remote(s,timeout=30):return subprocess.run(adb+['shell','su -c '+shlex.quote(s)],capture_output=True,text=True,timeout=timeout)
r=remote('mktemp -d /data/local/tmp/d2p-v2-test.XXXXXXXX');r.check_returncode();d=r.stdout.strip();assert d.startswith('/data/local/tmp/d2p-v2-test.')
try:
 for name, data in [('certtool.jar', (root/'certtool.jar').read_bytes()), (subject_hash+'.0.original.der', fixture)]:
  subprocess.run(adb+['exec-in','su -c '+shlex.quote('cat > '+shlex.quote(d+'/'+name))],input=data,capture_output=True,check=True)
 s='''
set -e
D=__DIR__
export CLASSPATH="$D/certtool.jar"
tool() { /system/bin/app_process /system/bin CertTool "$@"; }
mkdir "$D/live" "$D/stage"
cp "$D/__HASH__.0.original.der" "$D/live/__HASH__.0"
cp "$D/__HASH__.0.original.der" "$D/live/__HASH__.10"
tool prepare "$D/live" "$D/stage"
cmp "$D/live/__HASH__.0" "$D/__HASH__.0.original.der"
stat -c 'BEFORE_INODE=%i' "$D/live/__HASH__.0"
chown 0:0 "$D/stage/pem/"*
chmod 0644 "$D/stage/pem/"*
chcon u:object_r:system_security_cacerts_file:s0 "$D/stage/pem/"*
tool commit "$D/live" "$D/stage"
stat -c 'AFTER_INODE=%i' "$D/live/__HASH__.0"
tool verify "$D/live"
ls -lZ "$D/live/__HASH__.0"
mkdir "$D/again"
tool prepare "$D/live" "$D/again"
mkdir "$D/bad" "$D/badstage"
printf '0garbage' > "$D/bad/__HASH__.0"
if tool prepare "$D/bad" "$D/badstage"; then echo BAD_ACCEPTED; exit 1; fi
[ "$(cat "$D/bad/__HASH__.0")" = '0garbage' ]
mkdir "$D/changed" "$D/changedstage"
cp "$D/__HASH__.0.original.der" "$D/changed/__HASH__.0"
tool prepare "$D/changed" "$D/changedstage"
cp "$D/live/__HASH__.0" "$D/changed/__HASH__.0"
if tool commit "$D/changed" "$D/changedstage"; then echo CHANGE_ACCEPTED; exit 1; fi
cmp "$D/live/__HASH__.0" "$D/changed/__HASH__.0"
echo ISOLATED_TESTS_PASSED
'''.replace('__DIR__',shlex.quote(d)).replace('__HASH__', subject_hash)
 r=remote(s,60);(out/'android-device-tests.txt').write_text(r.stdout+'\nSTDERR\n'+r.stderr)
 print('returncode',r.returncode);print('\n'.join(l for l in r.stdout.splitlines() if not l.startswith('PEM ')));print(r.stderr[:1600]);r.check_returncode()
 # Copy converted public certificate for independent OpenSSL comparison.
 r=subprocess.run(adb+['exec-out','su -c '+shlex.quote('cat '+d+'/live/'+subject_hash+'.0')],capture_output=True,check=True)
 (out/'converted-public-ca.pem').write_bytes(r.stdout)
 r=subprocess.run(['openssl','x509','-inform','PEM','-outform','DER'],input=r.stdout,capture_output=True,check=True)
 assert r.stdout==fixture
 print('Device output roundtrip matches original DER')
finally:
 r=remote('rm -rf '+shlex.quote(d));r.check_returncode()
