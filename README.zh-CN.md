# cacerts-der2pem

[English](README.md) · [下载 Release](https://github.com/zfj201/cacerts-der2pem/releases)

这是 [AlwaysTrustUserCerts](https://github.com/NVISOsecurity/AlwaysTrustUserCerts) 的**证书格式补充模块**：对已注入、位于受支持目录挂载中的 CA 进行校验，将 DER 转换为 PEM。模块不自带 CA、不新增信任锚点、不替代上游注入模块，也不是 NVISO 官方发布或上游分支。

**v2.0.0 为预发布版本。** 已通过 Android 15 + KernelSU + AlwaysTrustUserCerts v1.3 环境下的隔离真机测试；新版完整安装、重启持久化及业务 HTTPS 回归尚未完成，不能视为全部兼容性已验证。

## 解决什么问题

证书“是否受信任”和“加载器是否能读懂文件格式”是两个问题。Java 证书解析器可以接受 DER 和 PEM，部分原生证书目录加载路径则要求 PEM。同一个应用的不同请求可能走不同 TLS 实现；应看实际请求的代码路径，而不是仅按原生页面或 WebView 页面区分。

当 AlwaysTrustUserCerts 的兼容配置把 DER 证书暴露到共享系统 CA 目录时，本模块补上格式规范化步骤。转换前后是同一张证书，DER 内容和 SHA-256 指纹保持一致。

它不能绕过证书绑定（pinning）、主机名校验或应用自有信任库，也不解决代理配置问题。TBS、Cronet、Flutter 是否受益需要按具体网络调用验证，不能一概而论。上游不同版本的注入布局也可能改变。

## 兼容范围

| 环境 | 支持与验证状态 |
| --- | --- |
| Android 8 / API 26+ | 实现最低要求；其他 Android 版本未真机验证 |
| Android 15 + KernelSU + AlwaysTrustUserCerts v1.3 | 隔离文件、挂载测试通过；尚未完成安装重启验收 |
| Magisk | 实现了 BusyBox 路径适配；未真机验证 |
| 其他 CA 注入模块 | 需满足相同目录布局；未验证 |
| system / Conscrypt APEX CA 目录 | 必须是服务可见的精确、可写 tmpfs 目录挂载 |
| 只读目录、单文件 bind mount、其他路径 | 不支持，不主动重挂载 |
| 手机端 OpenSSL | 不需要，使用 Android 自带 X.509 解析器 |

仅处理 `/system/etc/security/cacerts` 和 `/apex/com.android.conscrypt/cacerts`。BusyBox 须位于 `/data/adb/ksu/bin/busybox` 或 `/data/adb/magisk/busybox`，且提供 `flock` 等所需命令。SELinux 也须允许临时文件及证书标签设置。

## 实现方式

- 等待 `sys.boot_completed=1`，随后每 60 秒检查一次，覆盖后续注入和重挂载。
- 使用真实 X.509 解析器校验完整 DER、拒绝尾随 DER 数据、核对 `subject_hash_old` 文件名及 SHA-256；支持 `.10` 等多数字后缀。
- 在同一 tmpfs 目录中生成 64 列 PEM，保存原件和候选件备份，发布前设置 root:root、0644 和 `u:object_r:system_security_cacerts_file:s0`。
- 再次检查源文件及目录挂载 ID，逐文件执行 `ATOMIC_MOVE + REPLACE_EXISTING`。没有截断活跃文件后写入的降级逻辑。拒绝符号链接证书和单文件挂载。

原子性针对单张证书，不是整批事务：后续文件失败时，前面已成功的同证书 PEM 可能保留。检查可降低竞争风险，但不等于与任意外部写入或重挂载同步。目录 bind 可以看到替换后的目录项；单文件 bind 可能继续持有旧 inode，因此拒绝。已打开文件或缓存 TLS 上下文仍可能需要重启应用。

模块在启动完成后运行，不能保证早于应用首次初始化信任库。日志超过 256 KiB 轮转；备份不会自动清理，反复失败时需检查并停用。

## 安装与验收

1. 先单独配置并启用 AlwaysTrustUserCerts，安装你需要的 CA。
2. 从 [Releases](https://github.com/zfj201/cacerts-der2pem/releases) 下载 `cacerts-der2pem-v2.0.0.zip` 和 `SHA256SUMS`，可用 `shasum -a 256 -c SHA256SUMS` 校验。
3. 在 KernelSU 管理器安装模块 ZIP 并重启；Magisk 为尚未验证的兼容路径。不要安装 GitHub 自动生成的源码 ZIP。
4. 等待系统完成启动和扫描，检查状态，再重启目标应用并验证实际 HTTPS。

```sh
adb shell su -c 'cat /data/adb/modules/cacerts_der2pem/runtime/status'
adb shell su -c 'tail -n 80 /data/adb/modules/cacerts_der2pem/runtime/service.log'
```

| 状态 | 含义 |
| --- | --- |
| `WAITING_BOOT` | 等待系统启动完成 |
| `WAITING_WRITABLE_DIRECTORY_MOUNT` | 服务命名空间中没有受支持的目录挂载 |
| `ERROR_SEE_LOG` | 校验或转换失败，同时查看 `prepare.log` / `commit.log` |
| `READY_LOCAL_NAMESPACE` | 本轮本地检查通过，不代表应用已经信任或 HTTPS 成功 |

找到目标应用主进程 PID，显式替换下面的 `12345`，不要误用推送等后台进程：

```sh
adb shell su -c 'sh /data/adb/modules/cacerts_der2pem/verify.sh 12345'
```

脚本只读检查 `/proc/PID/root` 中的 CA 目录，输出指纹、权限和 SELinux 标签，对残留 DER 返回失败。必须把目标 CA 的 SHA-256 与原证书对应。root 能读取该视图，不代表应用进程自身有读取权限；全部为 PEM 也不能证明所需 CA 存在，更不能证明请求成功。

重启应用，观察新发生的 HTTPS 请求；手机再次重启后重复检查，才能验证持久性。遇到不支持的挂载或应用自有信任规则，仅靠本模块无法解决。

## 停用与回退

在根管理器停用或移除本模块后重启，上游模块将从原来源重建运行时目录。本模块不修改用户凭据、AlwaysTrustUserCerts 脚本或其持久源证书。仅停用而未重启时，已经转换的 PEM 仍可能存在于 tmpfs。诊断备份位于模块目录下 `runtime/backup.*`，不会自动覆盖恢复当前信任库。

## 构建和测试

依赖 JDK 17、Python 3、主机 OpenSSL、zip/unzip、Android SDK Build Tools 36.0.0 和 android-36 平台。设置 `ANDROID_SDK_ROOT` 或 `ANDROID_HOME`；默认回退到 `$HOME/Library/Android/sdk`。版本可覆盖：

```sh
python3 tests/test_certtool.py
D2P_BUILD_TOOLS=36.0.0 D2P_PLATFORM=android-36 sh pack.sh
```

主机测试默认生成一次性测试证书并删除私钥，也可传入自选 DER 测试文件路径。输出 `certtool.jar` 和 `cacerts-der2pem.zip`，不提交到 Git。安装包仅包含 `module.prop`、`customize.sh`、`service.sh`、`verify.sh`、`certtool.jar`。

可选真机测试需 root、adb、已构建 JAR，运行前请阅读脚本并指定测试设备：

```sh
ANDROID_SERIAL=YOUR_TEST_DEVICE python3 tests/test_device.py
ANDROID_SERIAL=YOUR_TEST_DEVICE python3 tests/test_mounts.py
```

第一个仅操作临时测试文件；第二个依赖 KernelSU BusyBox 的 `unshare`，在私有挂载命名空间内建立临时挂载，不操作活跃 CA 目录。两者都不安装模块或重启设备。测试输出被 Git 忽略。详细边界见 [验证记录](tests/VALIDATION.md)。

可选 GitHub Actions 配置保存在 `docs/ci-workflow.example.yml`，本次发布尚未启用。具有 GitHub 工作流权限的仓库所有者可将其放入 `.github/workflows/ci.yml`；上述本地构建和测试命令可直接使用。

## 许可与致谢

MIT。感谢 [NVISOsecurity/AlwaysTrustUserCerts](https://github.com/NVISOsecurity/AlwaysTrustUserCerts) 提供上游 CA 注入项目。本仓库不包含上游代码、个人证书、APK、抓包数据或应用逆向产物。
