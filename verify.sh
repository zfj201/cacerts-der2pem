#!/system/bin/sh
# Explicit PID avoids selecting a background process accidentally. Read-only.
MODDIR=${0%/*}
case "${1:-}" in ''|*[!0-9]*) echo "Usage: sh $0 PID"; exit 2;; esac
PID="$1"
[ -d "/proc/$PID/root" ] || { echo 'Target PID unavailable'; exit 1; }
rc=0
seen=0
for d in /system/etc/security/cacerts /apex/com.android.conscrypt/cacerts; do
  dir="/proc/$PID/root$d"
  [ -d "$dir" ] || continue
  seen=$((seen + 1))
  echo "DIRECTORY $dir"
  CLASSPATH="$MODDIR/certtool.jar" /system/bin/app_process /system/bin CertTool verify "$dir" || rc=1
  ls -ldZ "$dir"
  ls -lZ "$dir" | grep -E "[0-9a-f]{8}\.[0-9]+$" || rc=1
done
[ "$seen" -gt 0 ] || { echo "No readable CA directories found"; exit 1; }
echo 'Match target CA fingerprints against originals. PEM/parse success does not prove a TLS connection succeeded.'
exit "$rc"
