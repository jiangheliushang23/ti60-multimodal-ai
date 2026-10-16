## 最新融合基线：低开销 AE/AWB（2026-10-16 发布）

本分支已将 2026-10-15 实板验证的低开销融合副本同步到标准工程路径：
`fusion/ti60_multimodal/` 为硬件，`fusion/demo_multimodal/` 为固件。
摄像头、红外热图、SHT30 同屏，并由现有 RISC-V 执行自动曝光和自动白平衡。
当前未集成实时人体/跌倒推理、运动分析、融合报警、以太网预览或板端 HTTP。

原匹配版本 BIT `c40afb2b...`、固件 `73a2c010...`；摄像头约 30fps。
上次完整运行检查为 300.140 秒，视频/红外/自动控制未记录错误，用户确认三项及画质正常。
SHT 日志根因、首次启动异常和长期热稳定性仍待解决；未写 Flash。
本次源码整理不代表重新上板验收。

构建入口、完整指纹和已知边界见 [低开销融合交付说明](docs/FUSION_AUTO_LOWCOST_20261015.md)。
以下有日期的旧记录保留作历史参考，以本段及交付说明为准。

# Ti60F225I3-V4 项目工作约定

适用于本仓库及其子目录，相对路径均以仓库根目录为准。维护者本机工作区为 `C:/Users/20558/Documents/embedded`；队友使用自己的克隆目录，不要求复制本机用户名或路径。

目录迁移记录（2026-10-04）：用户已将根目录名从“嵌赛”改为“embedded”。历史日志、快照、导出和指纹清单保留原内容；读取其中的旧绝对路径时，将旧根目录映射到上述新目录，勿为迁移改写原始验证证据。

## 当前方向与 GitHub 协作（2026-10-04）

- 私有仓库：[jiangheliushang23/ti60-multimodal-ai](https://github.com/jiangheliushang23/ti60-multimodal-ai)。仓库创建、源码导入、四份 PDF 资料入库和六项 Issues 登记已完成，不再把创建仓库列为待办。
- 根目录 `AGENTS.md` 纳入版本管理。团队入口为 [README](README.md)、[项目状态](docs/STATUS.md)、[路线图](docs/ROADMAP.md)、[待办](docs/BACKLOG.md)、[协作指南](docs/TEAM_WORKFLOW.md) 和 [构建指南](docs/BUILD.md)。
- 用户明确暂不处理 SHT30 温湿度日志异常；保留 Issue #6，不能因为暂缓而宣称异常已修复。清晰度/对焦也暂缓；实际采集 ≥60fps 仍需匹配模组的完整模式表，不能用 HDMI 60Hz 代替。
- 后续产品路线为：核对并重构建当前模块拆分源码（#1）→ 实时人员分类（#2）、帧差运动（#3）→ 选定一个事件场景并实现融合/本地报警（#4）→ 选择至少两项任务 3 扩展（#5）。具体工作以用户当前请求和队员认领为准；更新文档不意味着开始上板调试。
- 开发任务用 Issue 约定接口和验收，通常在 `feature/...` 分支开发并提交 PR。顶层、XML、引脚/时钟约束、APB 和 DDR 协议先协调；不假设已配置分支保护或已邀请队友。
- 本机 `main` 跟踪 `origin/main`。GitHub 插件在本次初始化时返回过权限错误；已通过用户完成设备授权的 GitHub CLI 成功创建和推送。本机 CLI 位于 `tools/github-cli/bin/gh.exe`（不随仓库上传）。后续按实际权限使用工具，不读取或输出令牌，不假定队友继承本机登录状态。
- `docs/references/` 的四份 PDF 与 `manifest.json` 已入库。保留 ROM 初始化文件、BSP、模型和 `tinyml_lib.a`；工具安装包、大型构建产物、完整历史快照、聊天导出及本机服务配置不提交。
- 共享开发板同一时刻由一位队员操作。执行下载、暂停 CPU 等会影响画面的动作前协调使用；纯文档任务不访问开发板。

## 当前融合入口（2026-10-04）

- 当前产品开发在 `fusion/ti60_multimodal/` 和 `fusion/demo_multimodal/`，先读 `docs/STATUS.md`、融合 README 和 STAGE2；维护者本机另有根交接最新段。下文 2026-10-02 六图入口和资源数据均为保留的历史基线，不代表当前融合状态。
- 当前屏幕已由用户确认恢复，最近确认的运行组合为冻结硬件位流 `aeb4f682...` + 红外分步调度固件 `14b20b1a...`（完整 SHA256 见 `docs/STATUS.md`）。实时 AI 尚未接入，SHT 日志序号、状态及时间戳偶发异常未解决，不能称为整体验收通过。
- 当前目录硬件源码存在尚未重新构建的模块拆分；参见 `fusion/ti60_multimodal/validation/ir_scheduler_20261004/hardware_source_audit.json`。不要覆写这些改动，也不要把旧位流的时序/运行结果当成新源码验收。
- 2026-10-04 16:35 开始的纯串口观察已完成1800.16秒，未重新加载/暂停CPU：视频约30fps，红外7080次连续发布且无重试/错误；用户确认界面正常。SHT日志序号、状态和时间戳仍有异常，整体未通过；记录为 `fusion/ti60_multimodal/validation/observe_20261004_163502/`。主机采集结束不停止板上程序。

## 目标与协作方式

- 在 Ti60F225I3-V4 上实现摄像头、SHT30 温湿度、GY-MCU90640 红外热成像、本地 AI 推理与 HDMI 显示，逐步加入多模态判断和报警。
- 最终系统独立于电脑运行。电脑用于构建、加载和调试；当前临时加载方案不等于已经实现上电自启动。
- 默认使用中文沟通，先给结论，再说明改动、验证结果及尚未验证的部分。
- 用户要求“推进”“继续”“帮我做”时，在已授权范围内直接完成工作，不只给计划；已经明确的授权和选择无需反复确认。
- 文档、分析或布局讨论本身不代表需要重新配置开发板。按当前请求确定工作范围。
- 修改前先读相关源码和证据，保持改动集中。能复用已验证模块时优先复用，避免无关重构。

## 开始工作时先读什么

1. 阅读根 `README.md` 与 `docs/STATUS.md`，核对当前状态、源码/位流差异及暂停事项。
2. 阅读 `docs/BACKLOG.md`、相关 Issue，以及 `fusion/ti60_multimodal/README.md`、`STAGE2.md`；融合开发不从旧六图工程开始。
3. 涉及硬件时从 `docs/references/README.md` 找原文 PDF，结合实际约束和实物接线。构建入口见 `docs/BUILD.md`。
4. 原维护者工作区保留 `项目交接_新对话上下文_20261002.md`、`analysis/`、完整旧基线和 `validation/` 快照。这些大部分未入库，新克隆中不存在是预期情况；需要恢复/复核历史实板版本时获取对应资料，不能编造缺失证据或重跑移植脚本补齐。
5. 以有日期的最新记录及原始证据为准。记录不代表本次开发板仍保持同一配置；操作硬件前重新检查设备及版本。

## 项目说明与硬件资料来源

四份原文已保存于 [资料目录](docs/references/README.md)，优先使用仓库副本。原始文件名、字节数与 SHA256 见 [manifest.json](docs/references/manifest.json)，无需依赖维护者的 Downloads 路径。

| 资料 | 仓库路径 | 用途 |
|---|---|---|
| 选题指南 | `docs/references/competition/Efinix_FPGA_Competition_Guide.pdf` | 赛题与验收；共 3 页，印刷页 9–11 |
| SC431HAI 手册 | `docs/references/camera/SC431HAI_Datasheet_V1.1.pdf` | 接口、电气、寄存器；V1.1，2024-08-16，共 42 页 |
| V4 软硬件设计说明 | `docs/references/board/Ti60F225I3_V4_Design_260920.pdf` | 板级功能、时钟、电源、接口 |
| V4 原理图 | `docs/references/board/Ti60F225A_V4_Schematic.pdf` | 封装球、连接器、电压与线路 |

- 本项目对应选题指南的 **“赛题三：多模态 AI 智能终端”**。`task2_ai` 指该赛题内的任务 2，不是“赛题二”。指南 PDF 第 1 页上半部分属于前一个赛题的游戏图形加速内容，不应混入本项目要求。
- 维护者本机另存的指南和摄像头资料指纹、全文提取及关键页截图放在 `analysis/project_sources_20261002/`。指南 SHA256 与原 `task2_ai/evidence/requirements_source.json` 一致。
- 区分“赛题要求”“技术要点提示”“芯片规格”“本板实际能力”和“当前已完成状态”。资料不能代替硬件实测。

## 赛题任务与验收边界

| 任务 | 指南要求 | 当前工程的对应边界 |
|---|---|---|
| 任务 1：采集与 FPGA 预处理 | MIPI CSI 视频不低于 **720p@30fps**；I²C 红外温度及温湿度采集；滑动平均、异常值剔除、时间戳对齐；HDMI/LCD 同时显示视频、温度热力图和环境参数 | 冻结版本已实现视频、热图及环境参数同屏；预处理/时间戳对齐等完整要求仍需逐项验收，SHT 日志异常未解决 |
| 任务 2：多模态 AI 与感知决策 | Ti60 内部署 RISC-V，运行 TinyML 等视觉算法；帧差或光流运动分析；视觉、红外、环境融合；实现一个智能事件场景及本地报警显示 | 静态人员分类是历史模型证据；当前融合固件尚未接实时 Invoke、运动分析、融合决策和报警 |
| 任务 3：系统优化与智能拓展 | 从指南所列拓展中 **至少实现 2 项** | 尚不能凭已有 RISC-V 推理程序认定这一任务完成，须选择并分别验收具体功能 |

- 任务 2 的场景可选跌倒检测、智能空调控制、入侵检测，或自定义智能场景；不是必须同时实现三个。当前用户尚未最终选定，不擅自改成“必须做跌倒”。
- 异常事件的本地响应要求包括 **LED 闪烁、蜂鸣器、HDMI 红色边框、事件类型和置信度**。只显示 `PERSON/NO PERSON` 或分数，不等于完成报警功能。
- 任务 3 的选项为：千兆以太网事件上报、RISC-V 复杂决策/协议控制、多目标跟踪、行为预测、低功耗场景管理、Web 远程监控、SPI 语音播报。具体两项待确定，不把所有选项当作必做，也不把“能运行 RISC-V”自动算成复杂决策已完成。
- 指南的网络结构“不超过 5 层卷积 + 2 层全连接”、参数量 100K 以内，以及融合权重 60%/25%/15%，位于“技术要点提示”中；按建议记录，不作为未经确认的硬性阈值，不因此直接替换已验证模型。
- 指南提示的最终显示布局为“主区域视频、侧边热力图、底部环境参数”。当前融合页已采用左侧视频、右侧热图、底部环境参数布局；事件/置信度尚未启用，显示 `--`。
- 摄像头采集帧率、HDMI 刷新率和 AI 推理吞吐分别测量。1080p60 HDMI 时序、静态图轮播或模型推理耗时均不能证明达到 720p@30fps 摄像头采集要求。
- 参考算法或主机仿真不能代替“在 FPGA 端运行”的验收；完成状态必须指向对应位流、软件版本和实测证据。

## 工程入口与保留的基线

当前产品源码在 `fusion/`。下表历史基线主要保留于维护者本机，Git 仅带入当前构建/测试所需的少量参考文件。

| 用途 | 路径 |
|---|---|
| 当前融合硬件 | `fusion/ti60_multimodal/Ti60_Multimodal.xml` |
| 当前融合固件 | `fusion/demo_multimodal/software/standalone/tinyml_pdti8/src/main.cc` |
| 当前融合显示/视频 RTL | `fusion/ti60_multimodal/src/fusion/` |
| 当前构建与测试 | `fusion/scripts/`、`fusion/tests/` |
| 历史六图识别 + HDMI 硬件 | `task2_ai/soc_hdmi/Ti60F225_tinyml_helloworld.xml` |
| 历史六图软件入口 | `task2_ai/demo_pdti8_hdmi/software/standalone/tinyml_pdti8/src/main.cc` |
| 历史六图 HDMI RTL | `task2_ai/soc_hdmi/src/hdmi/` |
| HDMI 集成与实板证据 | `task2_ai/hdmi_20261002/` |
| 已验证的独立 TinyML 硬件基线 | `task2_ai/soc_v4/` |
| 已验证的独立 TinyML 软件基线 | `task2_ai/demo_pdti8/` |
| 原串口推理与启动调试证据 | `task2_ai/bringup_20261002/` |
| 用户指定的 SHT30 + 红外 + HDMI 历史 IDE 工程（无摄像头） | `C:\Users\20558\EfinityPrj\IR_Thermal_HDMI_v3_20260930\IR_Thermal_HDMI.xml` |
| 对应传感器源码、构建脚本与验证资料 | `sensors/ir_thermal_hdmi_v3_20260930/` |
| SHT30 与 HDMI 参考工程 | `sensors/sht30_hdmi_20260930/` |
| 摄像头参考与历史工作 | `camera/` |

- 继续融合 AI/HDMI 开发时使用 `fusion/ti60_multimodal` 与 `fusion/demo_multimodal`；`soc_hdmi`、`demo_pdti8_hdmi` 和原串口工程仅作历史参考，不覆盖原基线。
- 用户于 2026-10-02 指定上述外部工程为之前仅用 SHT30 和红外传感器、通过 HDMI 显示相关信息的工程；尚未集成摄像头。它与历史六图 AI/HDMI 工程原为两套独立基线；当前 `fusion/` 已复用相关模块，但原基线本身没有被覆盖为融合工程。
- 外部工程 RTL 位于 `src/`，工作区对应源码位于 `rtl/`，另含 `firmware/`、`tests/`、`validation/`。2026-10-02 核对的 11 个 RTL、工程 XML、外围约束、SDC、`firmware.hex` 和位流均逐文件 SHA256 一致，记录在 `analysis/project_sources_20261002/sensor_baseline_comparison.json`；不代表后续修改后仍同步。
- 该传感器工程的 GUI 入口使用外部英文路径；工作区 XML 是引用 `src/` 的构建副本，不能当作可直接打开的完整源码工程。工作区 `build.py` 会把 `rtl/` 等同步到外部目录并重新构建；资料登记时不要运行它。
- 大规模集成或实验性替换时，保留可恢复的已验证版本。不要覆盖或删除原摄像头、传感器工程及原始资料。
- 不直接编辑 `outflow`、`work_syn`、`work_pnr` 内的生成文件来代替源码修复。
- 重新运行采集脚本前检查其输出路径，保留需要存档的旧日志；日期相同不代表可以混用不同位流或程序的证据。

## 历史六图验收（2026-10-02，非当前产品状态）

- 用户选择使用现有六张内置图片，不要求另外提供用户图片。
- MobileNetV1 人员分类模型在实板完成六图推理，输出人员分数依次为 94%、27%、86%、72%、30%、6%。
- 当时模型输入为 96×96×1 灰度 INT8，输出为有人/无人两个类别；六个示例结果符合示例标签，不代表泛化准确率。
- HDMI 为 1920×1080、60 Hz；左侧 768×768 灰度图，右侧分类、人员分数条和耗时，底部六图进度。每次重新推理后停留约 3 秒，循环切换。
- 用户已确认“画面正常，能自动切换”；证据在 `screen_acceptance.json`。`loop_verified.json` 记录了不重新加载程序的持续循环。
- 当时集成程序为 1,415,700 字节，DDR 全量读回一致；六次显示提交均收到像素域应答。原串口基线的程序大小不同，不能混用。
- 首轮集成计时约 197 ms，包含 profiling/UART 日志开销，不能当作纯计算耗时，也不能据此宣称摄像头帧率。
- 当时使用临时 JTAG 配置和 DDR 程序加载，未写 Flash；断电后需重新加载。
- 当时位流尚未集成实时摄像头、SHT30 和红外输入；后续同屏集成已在 `fusion/` 完成，当前边界见本文开头。

## 板级约束与调试经验

- 器件为 **Ti60F225 / I3 / V4 板**。标准 Ti60 开发套件的快速启动文件不能未经适配直接视为本板可用文件。
- DDR 为 16 位、256 MiB。当前 CPU/加速器 225 MHz，外设/CLINT 100 MHz，DDR 物理时钟 400 MHz。
- HDMI 像素时钟 148.5 MHz，串行时钟 742.5 MHz，使用 TR0 PLL；DDR 使用 BR0，SoC 使用 TL0。复用已验证的 TMDS 引脚、极性和串行配置。
- FPGA 封装球 J2 的 25 MHz 参考时钟，与主板上名为 J2/J3 的跳帽不是同一概念。不要混淆，更不能仅凭名称调整电压。
- HDMI bank3A 为 1.8 V；DDR bank3B/4A/4B 为 1.5 V；UART RX/TX 为 R4/R14、3.3 V。更改前仍须核对当前原理图和约束。
- FT4232 为 `0403:6011`：**B 通道 JTAG**，OpenOCD `ftdi channel 1`，Programmer URL 后缀 `/2`；**C 通道 UART**，本次为 COM3、115200、8N1。
- USB bus/device 及 COM 号可能变化。下载前重新枚举，不硬编码沿用旧设备编号。
- 正确 JTAG ID 为 `0x10660A79`。Programmer 退出码为 0 不足以证明下载成功，须检查器件 ID 和完成日志。
- 当前融合加载入口为 `fusion/scripts/run_sensors.py`，它包含源码/产物匹配检查，不能绕过。V4 JTAG 配置参考 `task2_ai/hdmi_20261002/v4_jtag.cfg`；旧 `capture_inference.py` 仅属历史 AI 基线。上游 FTDI 配置和旧 `.launch` 文件可能与本机通道/路径不匹配。
- 采用实测成功的启动顺序：`init → halt → soft_reset_halt → load → dump/比对 → halt → soft_reset_halt → resume 0x1000`。
- 不同时启动多个占用同一 JTAG 或串口的进程。程序结束采集后可继续运行，关闭串口不等于停止 FPGA。
- 在用户要求的上板任务内，复用已有授权；默认临时 JTAG 加载。Flash 固化、改变接线/供电或覆盖已验证基线须有对应的明确授权，不从普通构建请求推断。

## 模型、显示与摄像头边界

- 用户于 2026-10-03 明确六张内置图仅用于模型测试，融合版需求以赛题为准。新融合工程不包含六图数据、图片 ROM、轮播/进度或六图自检入口，不将六图回归列为产品阶段或验收条件。旧六图结果仅作历史证据，复用模型与推理能力，实时识别以摄像头真实帧验收。
- `demo_pdti8` 是 INT8 人员分类示例，不是完整实时摄像头检测系统。当前分类模型不输出人体框，不能绘制伪造的检测框或声称已实现多人跟踪、跌倒识别。
- 分数来自实际 `Invoke()` 输出，不能把测试日志中的数值写死成产品结果。等待、运行中和错误状态不得显示为有效分类结果。
- 历史六图输入规则：前两张内置图片已经量化，直接复制到 INT8 输入；其他四张 uint8 灰度图需减 128。用于 HDMI 显示时，前两张要按有符号值加 128 恢复灰度。
- 历史六图显示寄存器使用 APB 基址 `0xF8100000` 的偏移 `0x1000..0x1018`；当前融合寄存器以 `fusion_apb.v`、固件及 `STAGE2.md` 为准，摄像头状态区位于偏移 `0x5000` 起。更改格式时同步软件、RTL、测试和文档。
- 跨时钟结果保持稳定直到应答，仅在垂直消隐更新整组显示元数据和结果，防止图文错配或撕裂。
- 接实时视频时，将显示支路与 AI 缩小/推理支路分开，AI 不能阻塞 HDMI 扫描；明确 DDR 缓冲区归属、帧号和结果对应关系。
- IMX219 与 SC431HAI 的寄存器、MIPI 配置、供电和排线映射不可混用。先确认实物型号和方向，再验证 CSI、颜色、方向与预处理。
- SHT30 与 GY-MCU90640 当前使用独立信号线。未核对地址、电平、上拉和总线访问方式前，不擅自合并 I²C 总线。
- 传感器 V3 工程的 `.peri.xml` 与两处 `pinout.csv` 已核对：SHT30 SCL/SDA 为 C5/A4，红外 SCL/SDA 为 B3/C3，均为 3.3 V LVCMOS。其 README 对应 J28-32/34 与 J28-37/39。旧交接把 SHT30 写成 J7/J28-37/39，与此工程不符；这是工程映射核对，操作硬件前仍须核对当前实物接线。
- 传感器 V3 的 PicoRV32 为 148.5 MHz，红外配置为 4 Hz 子页率，HDMI 为 60 Hz，三者不能混为采集帧率。其 HDMI 使用 BR0 PLL，而当前 AI 工程的 BR0 用于 DDR；集成时必须重新分配时钟资源，不能整份照搬外围约束。
- 红外测温不等于医学体温；人员分类不等于跌倒识别。功能名称须与实际算法和验证证据一致。

## SC431HAI 摄像头适配规则

用户已提供 SC431HAI V1.1 手册，后续该型号适配以此为依据。提供手册不代表模组已经接好、读到 ID 或输出视频；这些状态须分别验证。

- 手册第 2、13 页：支持 RAW RGB、8/10-bit、1/2/4-lane MIPI；列出的最大模式为 2560×1440 @ 30/60 fps。实际选择的 lane 数、位深、时钟及帧率须与模组和 Ti60 接收链路匹配，不能直接按最高模式初始化。
- 第 10–12 页：配置接口为 **16 位寄存器地址、8 位数据**。SID 低时七位地址 `0x30`，对应八位写/读地址 `0x60/0x61`；SID 高时七位地址 `0x32`，对应 `0x64/0x65`。先确认驱动 API 接收七位还是八位地址。
- 第 13 页：`0x3107` 应读出 `0xCD`，`0x3108` 应读出 `0x6B`，组合 Sensor ID 为 **`0xCD6B`**。这只是手册期望值，读到后才能记录实物识别成功。
- 第 2、33 页：芯片典型 AVDD=2.8 V、DVDD=1.2 V、DOVDD=1.8 V。芯片电源脚不等于摄像头模组连接器的输入供电；先查模组原理图、稳压和电平转换，再核对主板接口，不按芯片电压直接改接线。
- 上电/下电时序见第 8–9 页，复位/睡眠控制见第 10 页；XSHUTDN 拉低时不支持 I²C 读写。外部时钟条件见第 17、34 页。
- 模式初始化需采用与 SC431HAI、EXTCLK、lane 数及目标分辨率匹配的寄存器表，不把零散寄存器描述当作完整初始化表，不复用 IMX219 初始化序列。
- 镜像/倒置与窗口见第 30–31 页，测试图案见第 32 页；调整方向或裁剪后重新检查 Bayer 排列、颜色和模型输入方向。
- 推荐验证顺序：模组接线/供电/时钟核对 → I²C ACK 与 Sensor ID → 匹配模式初始化 → 测试图案/CSI 帧计数 → 真实视频的方向与颜色 → 至少 720p@30fps 实测 → AI 缩放、量化及结果叠加。

## 构建与验证

工具与依赖见 [docs/BUILD.md](docs/BUILD.md)。本机使用 Efinity `C:/Efinity/2026.1`、RISC-V IDE `C:/Efinity/efinity-riscv-ide-2026.1`、Python 3.12、Icarus Verilog `tools/iverilog/bin`；队友自行安装工具，路径不同时适配构建脚本。

当前融合工程从仓库根目录执行以下命令（均不下载开发板）：

```powershell
python -B fusion/scripts/build_firmware.py
python -B fusion/tests/run_firmware_tests.py
python -B fusion/tests/run_rtl.py
python -B fusion/tests/run_video_tests.py
python -B fusion/tests/run_camera_reuse_tests.py
& ./fusion/scripts/build_hardware.ps1 -Flow interface
python -B fusion/scripts/refresh_constraints.py
& ./fusion/scripts/build_hardware.ps1 -Flow map
& ./fusion/scripts/build_hardware.ps1 -Flow pnr
& ./fusion/scripts/build_hardware.ps1 -Flow pgm
python -B fusion/scripts/verify_build.py
```

- 这些命令是构建入口，不代表当前模块拆分已经通过全流程。按实际改动运行相应检查；纯文档只检查内容和链接，不编译/下载硬件。
- `pgm` 仅生成位流；`run_sensors.py`、`restore_sensor_run.py` 才涉及实板操作。软件 `.hex` 与 FPGA 位流 `.hex` 不能混淆。
- `prepare_project.py`、`prepare_camera_stage2.py`、`connect_camera_stage2.py`、`port_sensor_firmware.py` 为早期移植脚本，依赖旧工程并可能覆盖文件；不是新克隆的初始化步骤。
- 修改接口后重新生成接口约束；修改 RTL 后执行相关仿真、综合和布局布线，检查 setup/hold、资源及新增告警，不用放宽约束掩盖问题。Efinity GUI 使用经核验的英文路径工程。
- 当前融合的冻结位流使用 59,304/60,800 XLR、233/256 RAM、53 DSP；已约束路径 setup/hold 为 +0.216/+0.026 ns。数字仅对应冻结版本，最新模块拆分须重新测量；不把继承的时钟域排除或受保护 IP 告警当作完整 CDC/时序签核。
- 旧六图工程的 +0.306/+0.026 ns、45,653 XLR、200 RAM、47 DSP 属于 2026-10-02 历史结果，不能沿用到融合工程。
- `fusion/scripts/verify_build.py` 核对测试、引脚、时序和产物指纹；旧 PASS 日志不证明新源码通过。当前未构建组合已有 `hardware_source_matches_bitstream=false` 记录，加载前先解决版本匹配。
- 实板加载保留完整 DDR 比对、UART 输出及显示应答证据，并记录对应源码 commit、位流/固件 SHA256。需要恢复冻结版本时取得匹配快照，不把缺失历史文件视为可忽略的检查。

## 证据与交接

- 区分源码完成、仿真通过、构建通过、实板推理通过和屏幕目视验收，不把其中一个替代另一个。
- PNG 画面若来自 RTL 仿真，应标明仿真；显示端应答不能代替实物屏幕确认。用户确认结果记录来源，不写成代理亲自目视。
- 完成关键步骤后更新 `docs/STATUS.md`、对应融合 README/阶段说明及 Issue，记录源码 commit、验证方式、结果和未完成事项；维护者本机同步根交接。只有涉及历史 AI 基线时才更新 `task2_ai/STATUS.md`。
- 保留原始日志和产物哈希，不只写结论。向用户报告时优先给当前结果和入口链接，不倾倒完整日志。

## graphify

- 保留 `/graphify` 触发规则：当用户输入 `/graphify` 时，在执行其他任务动作前先读取并使用已安装的 graphify 技能或其指令。
- 本机已知技能路径：`C:\Users\20558\.agents\skills\graphify\SKILL.md`。原约定路径为 `~/.Codex/skills/graphify/SKILL.md`；若指定路径不存在，查找已安装版本，不假装已读取。
- 如果存在 `graphify-out/`，按技能说明使用其中资料；生成图谱不能替代当前源码、约束和实测证据的核对。
