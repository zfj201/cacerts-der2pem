# Changelog

## v2.0.0 — 2026-10-09 (pre-release)

First public release; follows an unpublished local prototype.

- Companion format normalization for compatible AlwaysTrustUserCerts directory mounts.
- Android X.509 validation, old subject-hash filename checks and certificate-preserving PEM conversion.
- Per-certificate atomic publication with staged metadata, source checks and retained backups.
- Exact writable tmpfs mount selection, single-file mount refusal, boot wait and recurring scans.
- Explicit-PID read-only verification and diagnostic statuses.
- English/Chinese documentation and disposable-certificate tests.

Android 15 / KernelSU isolated tests passed. Full installation/reboot and Magisk verification remain outstanding.
