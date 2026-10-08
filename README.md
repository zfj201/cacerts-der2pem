# cacerts-der2pem

[中文说明](README.zh-CN.md) · [Releases](https://github.com/zfj201/cacerts-der2pem/releases)

A certificate-format companion for [AlwaysTrustUserCerts](https://github.com/NVISOsecurity/AlwaysTrustUserCerts). It validates existing certificates and converts DER files to PEM in supported, writable Android CA directory mounts. It ships no CA, adds no trust anchors, and does not replace the CA injection module.

**v2.0.0 is a pre-release.** Android 15 + KernelSU + AlwaysTrustUserCerts v1.3 passed isolated on-device tests. Full module installation, reboot persistence and application HTTPS regression testing remain outstanding. See [validation details](tests/VALIDATION.md).

## Why this exists

A CA can be trusted yet stored in a format that a particular certificate loader cannot read. Java certificate parsers can accept DER and PEM; some native directory-loading paths expect PEM. Different requests in the same app may use different TLS stacks. This depends on the request's code path, not whether a page looks native or uses a WebView.

For compatible AlwaysTrustUserCerts setups that expose DER certificates in a shared system trust directory, this module supplies the format-normalization step. DER and PEM encode the **same certificate**: conversion preserves its DER bytes and SHA-256 fingerprint. It does not bypass certificate pinning, hostname verification, or an application's private trust store. TBS, Cronet and Flutter compatibility must be checked per actual network path.

This is an independent companion project, not an official NVISO release or a fork of AlwaysTrustUserCerts. Its injection behavior and supported layouts may change between upstream versions.

## Support and limits

| Component | Status |
| --- | --- |
| Android 8 / API 26 or newer | Implementation minimum; other Android versions not device-tested |
| Android 15 + KernelSU + AlwaysTrustUserCerts v1.3 | Isolated device and mount tests passed; installation/reboot not yet tested |
| Magisk | BusyBox lookup implemented; not device-tested |
| `/system/etc/security/cacerts` | Supported only when it is an exact, writable tmpfs directory mount visible to the service |
| `/apex/com.android.conscrypt/cacerts` | Same requirement; app namespace visibility must be verified |
| Other CA injection modules | Conditional on the same layout; not tested |
| Read-only stores, single-file bind mounts, unrelated paths | Not supported; no automatic remount |
| OpenSSL on the phone | Not required; Android's X.509 parser is used |

BusyBox must be executable at `/data/adb/ksu/bin/busybox` or `/data/adb/magisk/busybox` and provide the commands used by the service, including `flock`. SELinux must permit staging and applying the certificate label.

## How it works

1. Wait for `sys.boot_completed=1`, then scan supported directory mounts every 60 seconds.
2. Parse real X.509 certificates, check canonical DER, reject trailing DER data, validate `subject_hash_old` names (`xxxxxxxx.0`, including `.10`), and compare certificate fingerprints.
3. Prepare 64-column PEM in the **same tmpfs directory**, retaining original and candidate copies under the module's private runtime directory.
4. Set root:root, mode `0644`, and `u:object_r:system_security_cacerts_file:s0` before publication. Recheck source contents and the directory mount ID.
5. Replace each file using `ATOMIC_MOVE` and `REPLACE_EXISTING`. There is no copy/truncate fallback. Reject individual file mounts and symlink certificate files.

Atomicity is per certificate, not per batch. Earlier successful replacements can remain if a later file fails. These checks reduce races but do not synchronize against arbitrary concurrent remounts or writers. Directory bind mounts see replacement directory entries; a single-file bind may retain the old inode, so it is refused. Already-open files and cached TLS contexts can retain old data until the app restarts.

The service starts after boot completion: it cannot guarantee that conversion precedes an app's first trust-store initialization. Logs rotate at 256 KiB; retained backups are not automatically pruned.

## Install

1. Install and configure AlwaysTrustUserCerts separately, including your intended CA. Keep it enabled.
2. Download `cacerts-der2pem-v2.0.0.zip` and `SHA256SUMS` from [Releases](https://github.com/zfj201/cacerts-der2pem/releases). Optionally verify with `shasum -a 256 -c SHA256SUMS`.
3. Install the module ZIP in KernelSU Manager and reboot. Magisk installation is an untested compatibility path.
4. Wait for boot and the scan, inspect status/logs, then restart the target app and verify its actual HTTPS behavior.

Use the **module ZIP asset**, not GitHub's automatically generated source-code ZIP.

## Verify

```sh
adb shell su -c 'cat /data/adb/modules/cacerts_der2pem/runtime/status'
adb shell su -c 'tail -n 80 /data/adb/modules/cacerts_der2pem/runtime/service.log'
```

| Status | Meaning |
| --- | --- |
| `WAITING_BOOT` | Boot has not completed |
| `WAITING_WRITABLE_DIRECTORY_MOUNT` | No supported directory mount is visible in the service namespace |
| `ERROR_SEE_LOG` | Validation or conversion failed; inspect `prepare.log` / `commit.log` too |
| `READY_LOCAL_NAMESPACE` | This scan passed locally; does **not** prove app trust or HTTPS success |

Find the intended app process PID and pass it explicitly (replace `12345`; do not accidentally choose a push/background process):

```sh
adb shell su -c 'sh /data/adb/modules/cacerts_der2pem/verify.sh 12345'
```

The read-only script inspects CA directories through `/proc/PID/root`, parses hash-named certificates, reports fingerprints, fails on DER remnants, and lists permissions/SELinux labels. Match the intended CA's SHA-256 against your original certificate. A root-readable view does not prove that the target process itself can read it. All-PEM output also does not prove that your CA is present or that an HTTPS request succeeds.

Restart the app and test newly generated requests; repeat after a device reboot to validate persistence. If unsupported mounts or application-specific trust rules are involved, this module alone cannot fix them.

## Disable / uninstall

Disable or remove the module in the root manager, then reboot. The upstream injector reconstructs its trust directory from its own sources. This module does not alter the user credential store, AlwaysTrustUserCerts scripts, or its persistent source certificates. Disabling without reboot does not immediately undo already-converted runtime files. Diagnostic copies live under `runtime/backup.*`; repeated failures can accumulate backups.

## Build and test

Requires JDK 17, Python 3, host OpenSSL, zip/unzip, Android SDK Build Tools 36.0.0 and platform android-36. Set `ANDROID_SDK_ROOT` (or `ANDROID_HOME`); the fallback is `$HOME/Library/Android/sdk`. Versions are overridable:

```sh
python3 tests/test_certtool.py
D2P_BUILD_TOOLS=36.0.0 D2P_PLATFORM=android-36 sh pack.sh
```

The host test generates an ephemeral test certificate and removes its private key. An optional DER fixture path can be supplied. Build outputs are `certtool.jar` and `cacerts-der2pem.zip`; neither belongs in Git. The ZIP contains only `module.prop`, `customize.sh`, `service.sh`, `verify.sh` and `certtool.jar`.

Optional device tests require an explicitly selected rooted test device, `adb`, and a built JAR:

```sh
ANDROID_SERIAL=YOUR_TEST_DEVICE python3 tests/test_device.py
ANDROID_SERIAL=YOUR_TEST_DEVICE python3 tests/test_mounts.py
```

The first test only uses disposable files. The second requires KernelSU BusyBox with `unshare` and creates temporary mounts inside a private mount namespace, not the live CA stores. Review the scripts before running them. Neither installs this module or reboots the device. Generated device output is ignored by Git. See [tests/VALIDATION.md](tests/VALIDATION.md) for the evidence boundary.

An optional GitHub Actions template is provided at `docs/ci-workflow.example.yml`. It is not active in this release; a repository owner with the required GitHub workflow permissions can place it at `.github/workflows/ci.yml`. Local build and test commands above are ready to use.

## License and credits

MIT. Thanks to [NVISOsecurity/AlwaysTrustUserCerts](https://github.com/NVISOsecurity/AlwaysTrustUserCerts) for the upstream CA injection project. No upstream code, user certificates, APKs, traffic captures or app-specific reverse-engineering artifacts are included here.
