# TB371FC 原厂对应源码：来源、请求与工程使用边界

核验日期：2026-11-24（Asia/Shanghai）。

## 结论与工程决策

本次没有验证到与本机 **TB371FC / ZUI 16.0.474 / Linux 4.19.157-perf+** 精确对应的 Lenovo 官方完整源码包。官方门户的直接文本提取不完整，限定型号的检索也未找到可核对的下载包；这一结果不是“任何渠道都没有源码”的证明。

社区已有公开的 TB371FC 下游内核树和构建说明，作者报告了构建及实机结果；本轮没有独立重建这些社区树。它们可以提供板级线索及经过来源核验的代码，但与原厂分发二进制的对应关系需要另行证明。不能把相同 SoC、相同 4.19 基线或修改后的版本横幅当成对应源码。

因此，本项目采用 [主线 Linux 策略](MAINLINE_STRATEGY.md)：继续复用既有 SM8250 支持，补齐本机板级驱动和生命周期；原厂源码请求并行进行。重建下游 4.19 可以作为保留 Android 的独立候选研究，不能作为已经具备全部输入的确定性修补方案。

## 本机请求对象

数据来自同日[只读实机摘要](evidence/2026-11-24-live-android-baseline.json)：

| 字段 | 实测值 |
| --- | --- |
| 型号 / board | `TB371FC` / `spinel` |
| Android SoC 属性 | `SM8250` |
| Firmware / build | `TB371FC_CN_OPEN_USER_Q00028.1_U_ZUI_16.0.474_ST_241129` |
| Android / 安全补丁日期 | `14` / `2024-11-05` |
| 内核 | `4.19.157-perf+`，AArch64 |
| 内核构建日期 | `Fri Nov 29 19:47:27 CST 2024` |
| 解压后 live config SHA-256 | `23d3db565be3cd6cfc07bb90541d971dc70e6a6ce3516360155b8fd15590e726` |

该摘要不包含设备序列号、MAC、账号、原始输入事件或用户文件。配置摘要只绑定配置内容，不单独证明整个内核镜像与历史资产逐字节一致。

## 已核验的社区来源

| 来源与固定版本 | 本次可读到的来源说明 | 可以使用的范围 |
| --- | --- | --- |
| [smith-dog/kernel-tb371fc，c3df39c](https://github.com/smith-dog/kernel-tb371fc/blob/c3df39c507c11eebb124224bd34e3ab701b6d1f3/README.md) | 基线明确为 `lss4/android_kernel_lenovo_paladin` 的 `11` 分支，即 TB-Q706F/Z GPL 包；另整合 CLO、其他社区驱动及重建的板级支持 | 追踪具体驱动与补丁。它不是 Lenovo 已提供本机原厂完整对应源码的证据 |
| 同一仓库 | 当前 README 声称合入 4.19.157 → 4.19.325，并纠正早期 4.19.198 横幅只是改过 SUBLEVEL | 当前补丁覆盖、构建与运行声明要分别核对；不能仅看 `uname` 判定 stable 修复范围 |
| [bampudding/linux_kernel_lenovo_tb371fc，b1d4656](https://github.com/bampudding/linux_kernel_lenovo_tb371fc/blob/b1d4656796d72d75b0daf716d15e8ecfd671c3e0/README.md) | README 明确为 4.19.235-derived，SUBLEVEL 标为 325；作者报告自己的实机验证 | 作为社区实现参考，不改写成完整 4.19.325 或本机已验证 |
| [tem423/android_kernel_lenovo_tb371fc](https://github.com/tem423/android_kernel_lenovo_tb371fc) | smith-dog 将 Novatek SPI 触摸和 KTZ8866a/b 背光来源指向此树；项目描述仍列出历史问题 | 保留原文件版权、许可证、固定提交及补丁差异后评估具体代码 |

smith-dog 的来源表还注明：音频 machine 按原厂 `audio_machine_kona.ko` 重建，功放固件来自原厂 `/vendor/firmware`。这说明已有社区适配工作可借鉴，也说明该树并非单纯的原厂对应源码导出。README 的营销年份存在不一致，本项目用 **TB371FC** 作为型号依据。

## 官方请求渠道与本次状态

已核验的正式电子渠道为 **Lenovo Ethics and Compliance Office：`ethics@lenovo.com`**。它是合规问题转办渠道，不是已经确认的专用内核源码邮箱。

来源为 Lenovo [Whistleblowing and Investigations Policy，CP-00024](https://www.lenovo.com/content/dam/lenovo/site-design/esg-document-library/global/corp-policies/policies/CP-00024_Lenovo_Whistleblowing_and_Investigations_Policy.pdf)：§3.1 包含客户等个人，§4.1 列出邮箱，§4.5 说明可将事项转交适当团队。

2026-11-24 03:21:47（Asia/Shanghai），项目所有者授权的正式请求已发送给该渠道，请求转交 Legal / Open Source Team。发送后读取回执，确认收件人、主题、完整正文及 `SENT` 状态。**这证明已发送，不代表 Lenovo 已受理、已确认违规或已交付源码。** 本文发布时尚无已核验的案件编号或源码答复。私人邮件标识、发件人地址和通信正文不写入公开仓库。

请求内容包括对应本机 firmware build 的 GPL 覆盖源码、板级修改、适用的 DTS/DTSI、发布配置、GPL 模块和接口定义、控制编译与安装的脚本，以及源码 revision / 工具链 / 构建映射说明；要求确认责任团队、case identifier 和预计答复日期。

Lenovo 的[一般移动设备开源通知](https://help.motorola.com/hc/apps/settings/legal/lenovo/en-us/T1507061259.html)另外列有邮寄路径：Legal Department，Open Source Team / Source Code Requests，8001 Development Dr., Morrisville, NC 27560。该通知并非本次从 TB371FC 固件内提取的专属 notice，邮件因此要求确认本 build 适用的要约和交付手续。本文没有替用户提交邮寄订单、付款或提供住址。

社区已有 [lenovo/gplcc#15](https://github.com/lenovo/gplcc/issues/15) 请求，2026-08-18 提出 TB371FC / 4.19.157-perf+；本次读到的两条评论不是 Lenovo 官方回复，并分别提及其他型号。该 issue 不是本项目此前发起的请求，也不证明厂商已正式受理或拒绝。仓库名称本身不建立指定交付渠道。

## GPL 与技术资产的区分

[GPLv2 §3](https://www.gnu.org/licenses/old-licenses/gpl-2.0.en.html#section3)规定分发受覆盖可执行代码时的源码交付安排，其中包括随附源码或符合条件的书面要约。没有找到公开下载页面，本身不足以证明不存在任何合规安排；源码是否完整、是否与交付版本对应则必须实际核验。

收到包后，按以下清单保存结果：

1. 包的官方来源、取得日期、大小、SHA-256、license / notice、宣称适用型号与 firmware build。
2. 原厂基线、完整补丁、板级 DTS/DTSI、配置、所需 GPL 模块及控制构建／安装的脚本。
3. 工具链和构建输入的实际可获取性，以及发布 build 与源码 revision 的映射。
4. 在隔离环境构建并记录产物、模块 ABI 和配置；先区分“能构建”与“对应该版本”，再进入设备资格和可恢复性检查。
5. 比对已知的 Novatek、双 KTZ8866、TFA98xx、键盘、USB/PD、面板、电源路径，将可复用内容接入 [驱动路线](DRIVER_ROADMAP.md)，更新真实验收记录。

固件二进制、额外芯片资料和所有闭源软件不能不加区分地宣布都必须按 GPL 提供源码。源码代码复用保留各文件许可证；跨 Linux、QEMU 与 XNU 可先共享可公开的硬件事实、协议说明和合成测试向量，代码移植与分发许可另行核对。原厂固件和私人镜像继续放在仓库外，以摘要和来源清单引用。
