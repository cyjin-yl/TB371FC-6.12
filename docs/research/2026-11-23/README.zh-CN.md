# TB371FC Android 硬件取证与移植查漏，2026-11-23

本轮使用另一台真实 TB371FC 的 Android 14／`4.19.157-perf+` 作为参考，
对照上游工程 `d157b92721fbeeab823f56a677b3593babf3afe6`。
完整方法、证据清单及复现步骤见 [英文总览](README.md)。

## 构建进展与完成标准

**最新构建检查：[research5](research5-services-kernel.md) 已编译并完成传输；
[首次 Fedora v9 镜像尝试](fedora-r4f-image-failed.md) 在任何 VM 之前失败。
最近一次实际生产启动仍是 [v8](fedora-r4e-persistent-result-failed.md)：guest
检查通过，但一条 Enforcing AVC 使整轮失败。本机 Linux 仍为 0 次启动、0 项通过。**

已在 doesvm CT102 的隔离容器内构建 `6.12.114-tb371fc-research1` 内核、
配套模块和设备树。实际启动测试发现并修复了历史页表池在通用 ARM 虚拟机
中耗尽的问题；最终 Image 已在 QEMU 中进入 ARM64 用户态。这仍不是本机
平板的启动或外设通过记录，基础设备树也仍关闭原生内屏和触摸节点。

独立的 `6.12.114-tb371fc-research2-display` 也已完成全量构建、83 个配套模块
检查和 QEMU 用户态启动。它修正显示设备树与驱动匹配，启用原生显示路径；
其触摸节点仍关闭，实机点亮、硬件渲染与整机状态仍待测试。

后续[输入专项](input-integration.md)已实际编译两项 Novatek 修复及显示/输入
联合设备树，18 组从真实 C 源码提取的错误路径回归通过。独立的
[签名组合](input-signed-integration.md)保留原 research2 Image 和 82 个原模块，
仅替换 Novatek 模块并加入联合 DT。模块签名与 63 个导入符号 CRC 均已离线
核验；这不是运行内核接受签名或触摸、笔、键盘实际工作的证明。

后续 [research3](research3-system-kernel.md) 和
[research4](research4-system-kernel.md) 各自完成了全量 Image 与 84 个签名模块
的检查，保留同一份显示/输入联合 DT 和标准 Adreno SMMU 引用。
research4 还补齐了 [ARM64 BPF 原生函数入口的配置依赖](arm64-bpf-trampoline.md)，
实际对象中已生成对应插桩；配置和编译证据仍不能代替运行时限制行为或实机结果。

独立的 [Fedora 完整系统](fedora-system-integration.md)已用真实 research1
Image，经修正后的 dracut initramfs 启动 ext4 根文件系统，进入 systemd
多用户目标。通用 ARM64 QEMU 的最终启动为 SELinux Enforcing，实际加载的
策略为版本 33，PID 1 进入 `init_t`；83 个模块与 69 个固件的哈希全部匹配。
这补上了主机上的完整系统启动链。该冻结基线仍保留 autofs4、pids、BPF-LSM
和虚拟 GPIO 提示，平板实际硬件也没有被传入虚拟机或完成验收。

后续 [Fedora research3 实验](fedora-research3-system.md)保留为失败：
`systemd-run --wait --pipe` 在执行 pids/BPF 行为测试前连接重置。
[离线策略查询](selinux-access-query.md)查到具体的 FIFO 权限差异，
[复制资格补充](selinux-query-copy-followup.md)另行保留了 PRoot 目录元数据的边界。
[首次 research4 系统实验](fedora-research4-bus-failed.md)同样保留为失败：
真实 broker 回应普通查询，但连不带资源限制的 `--wait --pipe true` 都在
pids/BPF worker 之前重置。它与早期 udev 描述符丢失是两个独立问题。
匹配实际 Fedora 源码的[早期 SELinux 审查与原生启动程序](early-initramfs-selinux.md)
处理另一项已观察故障：旧 initramfs 缺少策略和可执行文件标签，切换根目录后
udev 保存的事件描述符被拒绝。新程序已两次编译为逐字节相同的 ARM ELF，
通过 API 加载检查和非 PID 1 负例。[随后 v5 的实际生产启动](fedora-r4b-early-failed.md)
加载了 Enforcing 策略，但在 `/var` 的文件系统标签关联检查被拒，尚未执行 systemd
就停止。[固定 rootfs/策略源码审查](selinux-rootfs-association.md)解释了普通 tmpfs
的不同 superblock 合同。新的[策略加载前 tmpfs 迁移入口与清理等待程序](tmpfs-initramfs-bootstrap.md)
已编译并通过有限入口检查，原生 e53 程序保留不动。[随后 v6 的实际运行](fedora-r4c-tmpfs-failed.md)
完成了 tmpfs 迁移、旧根清理，并读到同次启动中的 `init_t`/`udev_t`。
但完整验收仍失败：策略/API 文件系统标签产生 AVC，PID 1 接收 FIFO 时又被拒，
随后出现描述符截断和 `InconsistentMessage`，pids/BPF worker 尚未运行。
局部正证据与原始失败结果都保留，不提升为完整系统或实机通过。

后续[重载与三个接收方的权限审查](selinux-runtime-contract-query.md)分别检查
broker、PID 1 和 worker。先前[仅加入 map 的策略构建](selinux-policy-map-candidate.md)
保留其完整单权限比较，但[后续权限查询](selinux-postreload-contract-query.md)发现
同一 `init_t` 类型的两项进程操作仍被拒。新的[联合策略构建](selinux-policy-map-self-candidate.md)
从原始模块库另建副本，仅增加策略 `map` 和 `init_t` 对 `init_t` 的
`setcurrent`/`dyntransition`。完整 version 35 与新解析的 version 33 CIL
比较排除了其他规则或约束变化，原上下文和配置不变。
[独立的 54 项查询](selinux-postreload-combined-query.md)确认所需权限子集允许，
两个拒绝控制仍保持拒绝。

独立 [V2 入口程序](early-selinux-reload-loader.md)已编译并通过非 PID 1 拒绝检查。
它原本使用 map-only 策略构建的记录保留；新联合策略同长，必须另由新档案和
运行时固定完整哈希；这些构建记录保留其原有范围。
[随后 v7 的真实运行](fedora-r4d-reload-fd-failed.md)已观察到标准策略重载、
同类型上下文设置及同次启动的 API/journal 正确标签。真实 system-bus 路径
将三个经过核对的 FIFO 描述符传到受控 worker，noop 退出 0。
`TasksMax=3` 实际允许两个子进程、拒绝第三个并返回 `EAGAIN`，
`pids.events:max` 从 0 增至 1，所有自建子进程均已回收。

**v7 整体验收仍失败。** PL061 检查用了错误的驱动目录，尚未读取正确目录的
实际绑定；两项可见 Enforcing AVC 和被并发控制台输出破坏的 JSON 帧也保留为失败。
完整日志中有两次[匹配源码确认的 BPF 成功附着](systemd-bpf-runtime-contract.md)，
但基线 proc-open 和受限 `EPERM`／零字节测试都未运行。实际加载策略的导出
已独立保存，不能与离线转换文件混为一谈。后续独立构建和 v8 实际结果见下文；
不改写旧实验，也不把局部进展提升为整体验收或平板实机通过。

[标准服务权限诊断](selinux-varlink-cleanup.md)已分别查询离线候选与实际保存的
v7 策略。两次各 32 项结果确认已观察的链接删除、socket 写入拒绝，以及
后续必需的 `connectto` 缺口；后者尚未在本次日志中触发。固定客户端不需要
目标 socket 的 `getattr`，原始标签也正确。这只是所查权限子集一致，不能
推断两份完整策略等价。

新的[标准服务策略](selinux-standard-service-policy.md)已完成独立构建和原始／
候选完整 CIL 比较，仅改变五个 allow 元组中的六项权限，包含上述三项标准
服务缺口；原上下文、布尔量和其他限制保持不变。[独立 86 行离线查询](selinux-standard-service-av-query.md)
确认所需权限均允许、保留的拒绝控制仍被拒。这些记录来自一次执行，包含
79 个唯一元组，不能当作 86 次独立测试或真实服务运行。

[审计可见性审查](audit-observability.md)解释了旧日志中共享 printk 抑制的边界。
独立[编译的 V3 入口](early-selinux-standard-services-loader.md)要求显式通用虚拟机
参数和实际设备树兼容串，在首次策略加载前只改变这一 limiter 的 interval，
并重新读取 interval 与 burst。其 72,528 字节 ELF 和新的[清理等待程序 V2](tmpfs-waiter-v2.md)
已通过有限的非 PID 1 拒绝检查；档案和运行配置仍须固定两份 ELF 与策略的
完整哈希，长度检查不能替代内容身份。这些构建证据保留原有范围，
后续实际运行的新观察单独记录如下。

[v8 的真实结果](fedora-r4e-persistent-result-failed.md)已完成全部既定 guest 行为
检查和普通结果文件传输，但**整轮仍失败**。真实总线及三个 FD 的转交成功，
四条实际路径各自核对 82 个 live-policy 元组；它们与一次 86 行／79 唯一元组的
离线候选查询分别记录。TasksMax 允许两个子进程、以 `EAGAIN` 拒绝第三个，
max-events 从 0 增至 1，子进程均回收。同一 worker 的 BPF 对照实际读到
181 字节基线数据，限制 `~proc` 后在 **`open` 阶段返回 `EPERM`／errno 1，
数据为零字节**。正确的 `pl061_gpio` 绑定、84 个模块与 69 个固件哈希、
模块签名强制执行、已加载 autofs4 和 taint 0 也已核对。

QEMU 正常关机退出 0；413,706 字节完整结果通过固定路径、文件元数据、哈希、
启动 ID 和 profile 检查只读取回，无解析错误，生产日志中所有既定丢失／抑制
计数为零。独立完整日志仍发现一项 Enforcing AVC：`journalctl --sync` 中的
`journalctl_t` 被拒绝创建自身 `unix_dgram_socket`。该命令虽退出 0，host
controller 仍为 false、pipeline 仍退出 1，不能忽略这条拒绝。后续源码诊断、
新候选与镜像失败另行记录如下。实际策略 `9d7aa2b3…` 私有保存、公开仅元数据，不与离线转换
文件等同。post-qualification、finalize 和 postboot e2fsck 都未运行；没有正的
udev 计数对，不能说队列为空或已全部保全。此前合成文件传输检查也不保证异常
终止后无需 journal replay 就能恢复。所有平板实机项目保持原状态。

### 后续构建检查点

[匹配实际版本的 socket 探测诊断](selinux-journalctl-socket-probe.md)已查明 v8 的
datagram 拒绝：systemd 创建 socket 以探测 xattr 支持，而固定内核会在 LSM
xattr 钩子之前拒绝这类特殊 inode 的 `user.*` 属性。对已保存的实际 v8 策略
直接查询也确认该缺口。新的[七权限候选](selinux-socket-probe-policy.md)只在
此前六项基础上增加自身 datagram `create`；完整 version 35／新解析 version 33
CIL 比较和 19 元组离线查询通过，12 项拒绝控制／诊断保持拒绝。
独立 [V4 入口](early-selinux-socket-probe-loader.md)已编译并通过非 PID 1 拒绝
检查，这些均为构建证据，原 v8 失败结果不改写。

[首次 v9／R4F 尝试](fedora-r4f-image-failed.md)在**任何虚拟机启动之前**失败。
两份新 initramfs 通过原有构建检查，但 `mkfs.ext4` 超过固定的 600 秒子进程
期限；连同清理，image 阶段为 615.382 秒，pipeline 退出 1。完整异常、原始
源码和未完成镜像保留。没有新的实际策略、FD、TasksMax、BPF 或零 AVC 结果；
独立恢复须另记输入与结果。同期 HDD 工作是资源背景，不能据此断言唯一故障原因。

另行构建的 [research5-services 内核](research5-services-kernel.md)已完成全量
编译和离线检查。相对 R4 恰有 14 项配置变化，补齐原始 Nix／Nura nftables
合同、Nura 明确选用的 zstd zram、通用 PL031 RTC 及新 release。84 个签名模块、
4,308 项导入 CRC、Image／BTF／公开证书和未变化的显示/输入联合 DT 均已核验；
106 个普通文件在共享构建器传输前后内容、模式与 owner 一致。
**这还不是 R5 系统启动**：原防火墙规则、OpenRC、zram、RTC、原生模块加载仍须
实际运行验证，不提升任何本机硬件项目。

[Nura 原始入口的有限只读盘点](nura-entry-inventory.md)另行确认 BusyBox PID 1
和由原 inittab 调用的 OpenRC 顺序。它没有执行目标程序，也不能把服务定义或
先前导出的通用 rootfs 当作目标系统已启动。

[NixOS 后续构建](nixos-system-build.md)已实际完成固定的
`system.build.toplevel`，得到引用闭合的 894 个存储路径，合计
3,751,712,072 NAR 字节。ARM systemd 的版本命令和生成脚本的语法检查
在显式 PRoot/QEMU 下通过；尚未生成或启动 NixOS 根文件系统，也没有执行
激活脚本或集成研究内核、模块与私有固件。这推进了先前的包闭包检查，
但不等于系统启动或本机硬件通过。独立根文件系统／虚拟机实验仍在另行准备，
不把尚未执行的草稿登记成这次冻结成果。

[首次原生 Nix 注册根准备](nixos-store-preparation-failed.md)已有明确失败记录：
源内容验证退出 0，后续签名缓存复制触及原定 3600 秒超时，整个任务退出 1。
目标注册、完整目标校验、镜像、激活和 PID 1 启动均未到达。旧部分缓存与完整
原始日志保留，`require-sigs` 不变；独立 SSD 恢复不计为本次通过。

### 各发行版目前完成到哪里

| 候选 | 已完成的主机证据 | 尚未跨过的边界 |
| --- | --- | --- |
| Fedora，冻结 research1 系统 | systemd 多用户和 Enforcing 完整启动，83 模块与 69 固件哈希匹配 | 基线资源/GPIO 提示仍保留；未测试平板硬件 |
| Fedora，research3/research4 后续 | 两份 84 模块完整内核；v8 完成早期标签、真实 FD/TasksMax/BPF 行为、PL061 绑定及正常关机结果传输 | v8 失败保留；首次 v9 镜像在 VM 之前超时；后续运行/收尾及平板验收未完成 |
| NixOS | 完整 894 路径闭包，ARM 版本/语法检查；独立 R5 服务前提已编译 | 源校验后首次签名缓存复制超时；无合格注册根／镜像、激活或 PID 1 启动 |
| Nura/postmarketOS 实验 | 382 包目标 rootfs 已导出；实际 BusyBox/OpenRC 入口盘点与独立 R5 前提编译 | 目标未启动；早期缓存仅留 371 个版本，完整重建和硬件集成仍未完成 |

[早期发行版构建比较](distro-builds.md)保留早期实验正文，并新增后续状态导航；
原全文哈希记录在该页。正文中的包闭包及软件图形数字仍是当时的观测，
不应被读成上表中的最新完整系统状态。

[新的首阶段重建](first-stage-reconstruction.md)已编译公开源码的 4.19.325
替代内核和默认 HOLD 的救援 initramfs。该下游内核在通用 QEMU 中进入
Qualcomm SCM 路径后、PID 1 之前失败；同一个 initramfs 只在冻结的 research2
参考内核下通过了用户态检查。另有一个私有、未签名的 Android v2 格式候选，
保留本机 recovery_a 的原始 header、DTB、DTBO，并通过独立重解析。
它并非历史 V56.6/R201 链的恢复；没有验证引导器接受、实机入口、kexec 转移、
USB 救援通道或 AVB 信任。

后续[USB 静态快照](usb-transport-readiness.md)发现本机有两个 UDC，均为
`not attached`，Android 的 `g1` 配置在 `a600000.dwc3` 上；doesvm 当时没有
枚举到对应设备。[独立的救援用户态修订](first-stage-owner-udc.md)修正了
旧版要求“恰好一个控制器”的分支，只接受已观察到的主控制器；目标或必需
属性缺失、无效时保持 HOLD，不回退另一个控制器。10 个模拟文件谓词用例、
参考内核 PID 1 与新私有 v2 格式检查通过，实际 USB 绑定、入口和恢复仍未验证。
[双端 USB 跟进](usb-transport-followup.md)与[05:18 UTC 的再次复查](usb-transport-recheck.md)
均读到两 UDC 为 `not attached`、doesvm 无对应候选；这不推断物理线缆是否存在或
其他主机的状态。[此前上海 14:09 的双端复查](usb-transport-recheck-1409.md)
再次记录同一有限结果。[此前上海 15:46:57–59 的双端读取](usb-transport-recheck-20261123T074657Z.md)
也得到两 UDC `not attached`／`UNKNOWN`、相同主控制器配置和 14 项主机 USB
条目中无对应 vendor 候选；两端命令均退出 0。未改变 USB／启动状态，不能据此
诊断线缆或其他主机。入口和恢复控制仍是实机测试的硬门槛。

[最新上海 17:36:24–25／UTC 09:36 的双端复查](usb-transport-recheck-20261123T093624Z.md)
两端均退出 0：两 UDC 仍为 `not attached`／`UNKNOWN`，`g1` 仍配置在
`a600000.dwc3`、VID/PID 为 `17ef:7e31`，doesvm 的 14 项中无对应 vendor
候选。没有 USB／启动状态修改，也未证明数据／恢复连接；不推断线缆故障、
物理连接位置或另一主机状态。

- [research5 原服务前提、全量内核编译与共享传输](research5-services-kernel.md)
- [journalctl socket 探测诊断](selinux-journalctl-socket-probe.md)、
  [最小七权限策略](selinux-socket-probe-policy.md)、[V4 入口构建](early-selinux-socket-probe-loader.md)、
  [保留的 v9 首次镜像失败／零 VM](fedora-r4f-image-failed.md)
- [Nura 原 BusyBox／OpenRC 入口盘点](nura-entry-inventory.md)
- [内核构建、真实失败、修复与复测](kernel-build.md)
- [6.12 显示设备树与驱动匹配修复](diagnostic-dt-profiles.md)、
  [独立显示候选](research2-display-build.md)、[SSD 构建环境](ssd-builder.md)
- [GPU 加速缺口与验收](gpu-acceleration.md)、[实际固件打包结果](firmware.md)
- [本机 GPU 数字 ID 与当前 Adreno SMMU 配置](gpu-chipid.md)
- [research3 完整系统内核](research3-system-kernel.md)、
  [ARM64 BPF 依赖修正](arm64-bpf-trampoline.md)、[research4 完整系统内核](research4-system-kernel.md)
- [输入代码修复与联合 DT](input-integration.md)、[签名后的模块/内核组合](input-signed-integration.md)
- [69/70 文件的规范固件目录与无线选择缺口](stock-firmware-staging.md)
- [无线缓存版本字段、原始 getter 与板型选择证据边界](radio-board-selection.md)
- [CNSS IPC 接口边界](radio-ipc-readiness.md)、[kprobe 能力边界](radio-probe-capabilities.md)、
  [真实出厂内核的 tracepoint/CNSS 缓存审查](cnss-shipping-static.md)
- [早期发行版构建比较](distro-builds.md)、[Fedora](fedora-build.md)、[Nura](nura-build.md)、
  [NixOS 配置和实测](../../../distros/nixos/README.md)
- [NixOS 完整系统存储构建及尚未启动的边界](nixos-system-build.md)，以及
  [首次注册根准备的原始超时](nixos-store-preparation-failed.md)
- [Fedora systemd/Enforcing 完整系统启动](fedora-system-integration.md)、
  [固定策略格式兼容检查](selinux-compatibility.md)、
  [压缩 initramfs 的独立校验](evidence/initramfs-validation.json)
- [保留的 Fedora research3 系统失败](fedora-research3-system.md)、
  [首次 research4 broker/udev 失败](fedora-research4-bus-failed.md)、
  [离线 SELinux 权限查询](selinux-access-query.md)及[复制资格补充](selinux-query-copy-followup.md)
- [早期 SELinux 源码审查与原生启动程序](early-initramfs-selinux.md)、
  [保留的 v5 标签关联失败](fedora-r4b-early-failed.md)、
  [rootfs/策略固定源码审查](selinux-rootfs-association.md)与
  [新 tmpfs 入口和清理等待程序](tmpfs-initramfs-bootstrap.md)及
  [保留的 v6 局部进展与完整验收失败](fedora-r4c-tmpfs-failed.md)
- [重载与完整接收方权限审查](selinux-runtime-contract-query.md)、
  [保留的 map-only 构建](selinux-policy-map-candidate.md)及[后续缺权](selinux-postreload-contract-query.md)、
  [新联合策略完整比较](selinux-policy-map-self-candidate.md)、[独立权限子集核验](selinux-postreload-combined-query.md)、
  [独立 V2 入口构建](early-selinux-reload-loader.md)、[BPF 行为源码合同](systemd-bpf-runtime-contract.md)
- [v8 全部 guest 行为与结果传输通过、整轮因一项 AVC 失败](fedora-r4e-persistent-result-failed.md)，以及[完整结果文件](evidence/fedora-r4e-persistent-result-failed-guest.json)和[原始生产日志](evidence/fedora-r4e-persistent-result-failed-verify.log)。
- [v7 实际局部进展与完整验收失败](fedora-r4d-reload-fd-failed.md)，以及[同次启动的实际策略导出](evidence/fedora-r4d-loaded-policy-export.json)。
- [整机验收计划](acceptance.md)、[逐项验收账本](acceptance.json)
- [本机启动条件与已校验离机备份](boot-readiness.md)、[R241 诊断模块构建](r241-build.md)
- [首阶段源码与私有中间产物缺口审计](entry-source-audit.md)
- [新的公开首阶段编译、保留的 VM 失败与仅格式验证的 v2 候选](first-stage-reconstruction.md)
- [本机和 doesvm 的 USB 快照](usb-transport-readiness.md)、
  [双端跟进](usb-transport-followup.md)、[后续有界复查](usb-transport-recheck.md)、
  [14:09 双端复查](usb-transport-recheck-1409.md)、
  [此前 15:46 双端读取](usb-transport-recheck-20261123T074657Z.md)、
  [已独立检查的固定控制器救援修订](first-stage-owner-udc.md)
- [最终内核的固件请求、设备状态与加载规则](firmware-kernel-contract.md)
- [118 个专用固件文件的私有传输与完整性检查](stock-firmware-bundle.md)
- [本机摄像头、音频与传感器静态清单](android-peripheral-inventory.md)
- [出厂功放缓存选择](tfa9894-cached-metadata.md)、[独立未签名功放模块原型](tfa-module-prototype.md)

按本机所有者要求，只有全部已安装设备达到可验证的最佳状态，才称为完成。
编译通过、枚举成功、软件渲染、关闭设备绕过问题，以及没有对照测量的节电
结论，均不算相应功能完成。硬件、Android 参考、主机构建和主线实机证据分别记录。

“最佳状态”的验收下限是同条件 Android 基线：吞吐不降低、延迟和能耗不增加，
同时保留正常温控、隔离、完整功能与恢复能力。测量方法和不确定度要在 Linux
对比测试前固定；证据不足标为待定，不能通过降低目标来把未通过改成通过。
第 8 版账本仍是 **44 项：12 项明确阻塞、32 项尚未运行；本机主线 Linux
运行 0 次、硬件通过 0 项**。标为尚未运行的项目也可能依赖前置阻塞项。

## 已经回答的问题

| 问题 | 本机证据与结论 |
| --- | --- |
| 实际选择哪个面板？ | Android 启动参数选择天马 NT36532。已保存该面板的设备树、显示模式、初始化和关屏命令原始字节。 |
| DSC 如何分包？ | 本机明确配置每包一个 slice。后期 6.12 导出补丁将两个 slice 合包，与此不同；还不能单凭这一点归因历史半屏故障。 |
| 初始化表是否需要重猜？ | 原厂 ON 表共 88 条；其中 86 条厂商 payload 与仓库 6.12 天马实现逐条相同。后两条为 Sleep Out、Display On。 |
| 关屏有哪些具体差异？ | Android OFF 使用 HS 模式，Display Off 后等 15 ms，Sleep In 后等 60 ms；现有移植路径的模式和等待不同。 |
| 高刷与笔是否有关联？ | 原厂存在笔相关模式表：30/60/120 Hz 使用 B3=0x40，144 Hz 使用 B3=0x00。寄存器精确语义尚未证明，但显示与笔应联合验收。 |
| 原装键盘有什么协议基础？ | 604 字节 HID descriptor 已解析，包含触控板、键盘和媒体键三集合。没有 Input report ID 6，不能照抄另一款 PID 6127 的状态协议。 |
| 笔充电是否完全无源码？ | 实机绑定 CTN730，公开 GPL 下游实现也已找到。仍需拆清控制器、Android 生命周期依赖和主线接入方式。 |
| 当前是否通过 PD 充电？ | 尽管类别标签出现 USB_PD，运行字段是 HVDCP 3、pd_active=0。不能据类别标签宣称 PD 协商成功。 |
| Android 的限频是否固定？ | 静态快照和稍后 trace 出现不同频率范围，证明不能把某一时刻的限频外推到其他时刻。 |
| 本机传感器可以照抄历史矩阵吗？ | 本机 SensorService 报告 TDK-Invensense `icm4x6xx` 加速度计/陀螺仪，与历史 Bosch BMI3x0 不同；必须按本机身份继续核对驱动。 |
| 摄像头和功放身份都已确定吗？ | 本机枚举两颗摄像头及四个已绑定功放；后续共享 HQ 槽读到 `tfa98xx_QS.cnt`，但它在异步加载完成前登记，不能证明四颗独立选择、硅片/声学身份、校准或实际输出。 |
| `Adreno650v3` 要改成 `650.3` 吗？ | 本机实际数字 chip ID 是 `0x06050002`，与已有 `qcom,adreno-650.2` 解析及 catalog 一致。型号字符串的 v3 不能替代数字 patch 字段。 |
| 当前候选是否用了历史全局 GPU 页表？ | research1 及后续 research3/research4 联合 DT 检查均保留 `qcom,adreno-smmu`、`dma-coherent` 和正确 GPU 引用，历史 R185 的删除没有应用。运行时进程隔离与恢复仍未测试。 |
| 原厂固件是否已形成可供组装的目录？ | 已实际校验 69 文件 ELF 与 70 文件 MDT 规范目录及所有必需索引分段；WLAN 板型文件、BT ROM 选择、TFA 容器和运行认证仍不能据文件齐全视为完成。 |
| WLAN 缓存版本能选出板型文件吗？ | 已读到 FW 1.0.1.0.1596.0 和 BDF 版本、参考设计、客户、项目及修订字段。这些不是 CNSS 的 QMI `board_id`，也不是已选文件名，不能据此选择某个 `bdwlan`。 |
| 出厂内核静态分析是否闭合了 WLAN 选择？ | 已确认 helper 分发和 CNSS 缓存布局，但有效位未随缓存保存、对象生命周期未闭合，历史请求文件名也没有缓存。未实施动态 probe、读取 live memory 或随意选 BDF。 |
| 功放是否有实际编译路线？ | 独立 TFA9894 匹配原型已编译，含 BTF，75 个导入 CRC 一致；它仍未签名、未安装、未执行，保留 35 个警告，完整持久写保护、路由和容器集成待做。 |
| 旧救援 init 能识别本机 USB 拓扑吗？ | 本机有两个 UDC，旧版恰好一个控制器的分支会保持等待。独立新版本只选 Android 已配置的 `a600000.dwc3`，主机检查通过；数据连接、实际枚举与恢复控制仍未证。 |

详细分析分别位于 [显示](display.md)、[输入和笔](input-and-pen.md)、
[电源管理](power-management.md)。报告还记录了笔物理尺寸常量不一致、
IRQ 负错误处理以及双背光 probe 失败清理等静态源码问题；这些已有明确边界
的修复与编译结果，但没有写成已经在主线实机复现或消除的故障。

## 实际采样和验证

- 已保存经过限定采集与检查的设备树属性、HID 描述符、驱动绑定、输入能力、
  电池/USB/CPU 状态。原始属性带长度与 SHA-256，可重新离线解码。
- 第一段含 CPU idle 的约 8 秒 trace 出现 ring-buffer overrun，明确保留为不完整样本。
- 后一段低流量 profile 约 8.012 秒，保留 196 条 CPU 频率、12 条 GPU 频率、
  18 条 GPU 状态事件；所有已报告的缓冲区丢失计数为零。
- 两次保存的 trace 都确认全局 tracer 设置不变，自己创建的 instance 已清理。
- 公开证据不含真实按键内容、笔迹、应用进程名、MAC、凭据或网络配置。
- 本机平板仍运行 Android 参考系统，没有刷写镜像、启动新的主线内核，或改变屏幕、
  电压、充电策略、SELinux 与看门狗设置。
- 当前 boot/recovery/vbmeta/dtbo 的 A、B 两槽共 8 个分区已做本机及 doesvm
  离机备份，所有镜像重新读取后的长度与哈希一致。它们是当前分区备份，恢复测试仍未进行。
- 当前 Android 配置实际为 `CONFIG_KEXEC=n`、`CONFIG_MODULE_SIG_FORCE=y`；
  现有 root 不直接提供主线入口。Android 属性和内核参数的锁定状态也有分歧，
  后续要在实际启动入口核实，不能据其中一项直接操作解锁。
- 118 个明确选择的原厂固件文件（38,546,828 字节）已私有传到 doesvm；
  源文件重读、逐文件接收和归档校验一致。六组 ELF/MDT 检查均找到所需分段。
  WLAN 板型、蓝牙 ROM 分支、DSP/视频 ABI 以及安全认证与加载仍需单独验证。
- 之后已实际生成并重读校验两份规范固件树，保留两种 Novatek revision-6
  变体与两对蓝牙 ROM 候选；没有随意选择 WLAN board 文件或不匹配的 TFA 容器。
- 固定无线元数据和[当前保留的内核缓冲区](evidence/android-radio-boot-selection.json)
  都未给出可用的 WLAN board/BDF 或 BT ROM 选择证据。没有清日志或重启无线；
  缓冲区没有 token 不等于完整启动过程没有，也不能证明设备或固件不存在。
- 后续仅读取限定的 `/sys/kernel/wifi/wlan/fw/1/version`，取得缓存描述字段；
  初次严格解析失败及后续修正均保留，两次读取的 123 字节内容哈希一致。
  未重启无线、读取寄存器或选择候选板型，公开下游 getter 也不代表已证明与
  本机正在运行的二进制完全相同。
- 后续固定接口检查确认 `DEBUG_FS=n`，没有可用 CNSS IPC 入口；未读取 ring
  或推进游标。kprobe 路径也不可用，但正常 fork tracepoint 接口存在。
  对实际备份出厂 Image 的静态审查明确了缓存字段与 helper 合同，仍未跨过
  有效性/生命周期限制，没有加载 BPF 程序或执行内核内存读取。
- 功放只读取经审查的缓存属性，结合实际出厂模块/内核确认共享选择槽。
  单独编译的 TFA 原型没有取代 84 个签名运行模块，也未加载到任何硬件。
- 本机和 doesvm 的 USB 快照只读取白名单属性，没有改变 USB 角色、PD 或
  gadget。新救援 ramdisk 的参考虚拟机明确跳过 gadget 分支，因此不能用
  PID 1 成功来替代 USB 实际绑定、枚举或恢复通道验收。
- 04:00 UTC 的再次双端快照仍是两个 UDC `not attached`、主机 14 个 USB
  条目无对应候选。这个时刻的观测不能外推为所有线缆/主机组合均不可用。
- [独立 initramfs 检查](evidence/initramfs-validation.json)拒绝了旧 CPIO/gzip
  顺序错误，接受修正后的实际压缩文件，并核验固件、ARM ELF 与库缓存。
  旧失败和完整 Fedora VM 的最终成功分别保留，不以目录内容替代打包产物检查。

静态读取并非全部无副作用：`wakeup_count` 会等待唤醒事件收敛；CTN730 的
`cn_test` 虽然呈现为只读文件，却会启动测试。采集器已排除这些路径。
证据总览保留了失败采集与后续修正的说明。

## 接下来应完成的工作

已有固定输入、可重新构建且记录实际产物哈希的内核、设备树和模块组合；
独立构建的逐字节可复现性仍受构建包版本及私有签名密钥影响，尚未证明。
完整 Fedora rootfs/initramfs、签名输入组合和规范固件目录也已有各自的主机
验证，但仍需将选定产物绑定到实际可用的本机入口、恢复控制通道及原生板级
启动合同。默认 HOLD 的格式候选不代表引导器或 AVB 接受。此后依次核对
双 DSI/DSC/CTL、关屏时序、显示与笔模式切换、键盘连接生命周期。充电要明确单一控制者，
分别验证电池遥测、充电策略和真实协议。最后进行可重复的休眠恢复与功耗测量。

本轮已经缩小了这些工作的未知范围，但尚未证明原生高刷、完整手写、磁吸充电、
稳定休眠或节电收益。
