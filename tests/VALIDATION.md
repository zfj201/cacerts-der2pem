# Validation / 验证边界

## v2 baseline — 2026-10-09

Before public packaging, the same runtime implementation passed:

- Host Java compilation, shell syntax and ZIP integrity checks.
- Independent OpenSSL DER → PEM → DER byte equality, multi-digit suffixes, inode replacement and idempotence.
- Rejection of malformed/truncated/trailing DER, wrong hash names, symlink inputs, concurrent source changes, corrupt staged PEM and empty stores.
- Android 15 `app_process` / DEX execution with isolated temporary certificates, ownership, mode and SELinux labeling checks.
- Private mount namespace tests: directory bind aliases observe replacements, metadata failures preserve originals, individual file binds are refused, and read-only tmpfs stores are unchanged.

A separate read-only audit of an already-repaired device store passed X.509/hash checks for 146 certificates. This was **not** a result of installing the v2 module.

The mount test found that Android mksh's close-on-exec handling broke fd-only `flock`. The service now uses BusyBox `flock` to own the lock while launching its worker; the isolated test passed after this change.

## Public packaging

Tests now generate disposable certificates instead of requiring a personal CA. Host tests and packaging are rerun for the release. Runtime behavior is unchanged; module author/version metadata is updated. The device helper no longer automatically audits the real system store, so tests are self-contained. Raw device logs, certificates and private analysis material are excluded.

## Not yet established

- Complete module installation and cold boot / reboot persistence.
- Boot ordering, target-app SELinux access and actual HTTPS regression after installation.
- Other Android versions, Magisk, other injectors and other ROM mount layouts.
- Exhaustive behavior under SIGKILL, disk faults, arbitrary concurrent writers/remounts or unusual provider-specific certificate encodings.

A passing host or isolated device test is not evidence that every app trusts the intended CA. The release is marked **pre-release** pending installation and reboot validation.

中文：当前证据覆盖主机及 Android 15 + KernelSU + AlwaysTrustUserCerts v1.3 环境下的隔离测试，不等于新版已完成安装、重启、应用 HTTPS 验收。其他组合未验证，因此按预发布交付。
