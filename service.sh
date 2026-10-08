#!/system/bin/sh
# Normalize certificates only in existing directory mounts; never modify user credentials.
MODDIR=${0%/*}
umask 077
RUNDIR="$MODDIR/runtime"
mkdir -p "$RUNDIR" || exit 1
LOG="$RUNDIR/service.log"
# BusyBox owns the lock and launches the worker; mksh marks extra FDs close-on-exec.
BB=
for b in /data/adb/ksu/bin/busybox /data/adb/magisk/busybox; do
  [ -x "$b" ] && BB="$b" && break
done
[ -n "$BB" ] || { echo 'ERROR supported BusyBox unavailable' >> "$LOG"; exit 1; }
if [ "${1:-}" != --locked ]; then
  exec "$BB" flock -n "$RUNDIR/service.lock" /system/bin/sh "$0" --locked
fi
log() {
  [ ! -f "$LOG" ] || [ "$(wc -c < "$LOG")" -lt 262144 ] || mv -f "$LOG" "$LOG.previous"
  echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG"
}
status() { printf '%s\n' "$*" > "$RUNDIR/status.tmp" && mv -f "$RUNDIR/status.tmp" "$RUNDIR/status"; }
tool() { CLASSPATH="$MODDIR/certtool.jar" /system/bin/app_process /system/bin CertTool "$@"; }
# Fail closed unless the exact directory is a writable tmpfs mount in this namespace.
mount_id() {
  awk -v p="$1" '$5==p && $6 ~ /(^|,)rw(,|$)/ {for(i=7;i<=NF;i++) if($i=="-" && $(i+1)=="tmpfs") {id=$1}} END {print id}' /proc/self/mountinfo
}
active() { [ ! -e "$MODDIR/disable" ] && [ ! -e "$MODDIR/remove" ]; }
stage=
cleanup() { [ -z "$stage" ] || rm -rf "$stage"; }
trap 'cleanup; exit 0' TERM INT
trap cleanup EXIT
log 'START v2; waiting for boot completion'
status WAITING_BOOT
while [ "$(getprop sys.boot_completed)" != 1 ]; do active || exit 0; sleep 3; done
while active; do
  eligible=0; failed=0
  for live in /system/etc/security/cacerts /apex/com.android.conscrypt/cacerts; do
    active || exit 0
    mid=$(mount_id "$live")
    [ -n "$mid" ] || continue
    eligible=$((eligible + 1))
    stage=$(mktemp -d "$live/.der2pem.XXXXXXXX") || { failed=1; log "ERROR staging $live"; continue; }
    # Staging in the same tmpfs guarantees same-filesystem atomic replacement.
    if ! tool prepare "$live" "$stage" > "$RUNDIR/prepare.log" 2>&1; then
      failed=1; log "ERROR validation $live; see prepare.log"; cat "$RUNDIR/prepare.log" >> "$LOG"
      cleanup; stage=; continue
    fi
    found=0; ready=1
    for f in "$stage/pem/"*; do
      [ -f "$f" ] || continue
      found=1
      chown 0:0 "$f" && chmod 0644 "$f" && chcon u:object_r:system_security_cacerts_file:s0 "$f" || ready=0
    done
    if [ "$found" = 1 ]; then
      if [ "$ready" != 1 ]; then
        failed=1; log "ERROR metadata $live; live files untouched"
        cleanup; stage=; continue
      fi
      # Retain original/candidate copies for each attempted batch, outside transient tmpfs.
      backup="$RUNDIR/backup.$(date +%s).$$.$eligible"
      if ! mkdir "$backup" || ! cp -R "$stage/originals" "$backup/" || ! cp -R "$stage/pem" "$backup/"; then ready=0; fi
      for f in "$stage/originals/"*; do
        [ -f "$f" ] || continue
        cmp -s "$f" "$backup/originals/${f##*/}" || ready=0
        cmp -s "$stage/pem/${f##*/}" "$backup/pem/${f##*/}" || ready=0
      done
      [ "$mid" = "$(mount_id "$live")" ] || ready=0
      active || ready=0
      if [ "$ready" != 1 ]; then
        failed=1; log "ERROR precommit checks $live; live files untouched"
      elif tool commit "$live" "$stage" > "$RUNDIR/commit.log" 2>&1; then
        log "SUCCESS $live backup=$backup"; cat "$RUNDIR/commit.log" >> "$LOG"
      else
        failed=1; log "ERROR commit $live; earlier atomic replacements may have completed; backup=$backup"
        cat "$RUNDIR/commit.log" >> "$LOG"
      fi
    fi
    cleanup; stage=
  done
  if [ "$eligible" = 0 ]; then status WAITING_WRITABLE_DIRECTORY_MOUNT
  elif [ "$failed" != 0 ]; then status ERROR_SEE_LOG
  else status "READY_LOCAL_NAMESPACE $(date +%s)"; fi
  # Watch new injections/remounts after boot too. A cached TLS context still needs app restart.
  sleep 60
done
status STOPPED
