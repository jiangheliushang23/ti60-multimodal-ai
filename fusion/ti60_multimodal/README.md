## 当前优先级：2026-10-04 GitHub 团队协作

用户明确暂不处理温湿度日志问题，当前任务为创建私有仓库 `ti60-multimodal-ai`、整理源码与团队待办。SHT 异常保留为暂缓项，不再将其排查列为当前首要工作。仓库说明入口为根目录 `README.md` 与 `docs/`；GitHub 插件创建请求返回 403（Resource not accessible by integration），远端尚未创建，等待正常 GitHub 登录后继续。本次只整理文件，不重新构建、加载或暂停开发板。

# Ti60 多模态融合工程：同屏与红外分步调度

## 当前进展：2026-10-04 红外分步调度，显示已恢复

- 当前运行的是同屏硬件位流 `aeb4f6821e6222552fd73e5a8507028ed68b4a7d3293d274baeeeb3f88e2e467`，配套红外调度固件 `14b20b1a8ac5356e8a35fcf16c241d1506bda7b0bd44d2a3cbcd89fb18ba2834`、56,106 字节。恢复证据为 `fusion/ti60_multimodal/validation/restore_20261004_162900/`，用户明确确认“都恢复了”。未写 Flash。
- 红外等待 I²C、重试延时、等待子页、显示 ACK 已拆为状态机；温度计算每批处理 32 个像素位置，在批次间返回主循环。两分钟实测每批最大 8ms、普通服务步最大 15ms；EEPROM 参数提取仍有一次约 91ms 的初始化计算。当前没有运行实时 AI。
- 恢复版重新编译后的指纹一致，19 项实际链接固件 ISA 场景通过。短测视频约 30fps、红外无重试/错误，但 SHT 日志偶发十进制序号与两份十六进制值不一致，整体验收未通过，根因未定。后续纯串口观察还发现异常状态值及负数采样年龄，不能只归因于十进制打印。
- 打印诊断候选 `00733ced...` 未获得启动串口，调试期间重新加载/暂停 CPU 影响了显示；候选已撤回。照片及原始日志保留，不能把这次现象当作“无调试干预的长时失效”已复现，也未证明问题来自接线、打印函数或 DDR。
- 已完成 `observe_20261004_163502` 的 **1800.16秒纯UART接收观察**（约16:35–17:05），期间未重载、暂停CPU或写串口。1796条视频状态记录，摄像头/发布约29.99974fps，全部记录的视频错误计数为0；7080条红外发布连续、子页交替，零重试/错误/重新初始化。用户在观察期间再次确认“现在界面显示正常，继续推进”。本次未复现两路停止更新。
- **整体遥测验收未通过**：1761条SHT记录中有7条序号表示不一致、9条异常状态、2条异常时间戳/负数年龄；原始数据和独立完整行复核均保留。19项固件ISA场景及3005组实际链接数字格式输出离线检查通过，但不能代替真实缓存/总线/UART行为验证。采集脚本已结束，仅关闭主机串口，未停止板上程序。
- 工作目录硬件顶层/XML 与冻结位流源码存在模块拆分差异，新增 `fusion_camera_subsys.v`、`fusion_sensor_front.v`、`fusion_video_path.v`；保留这些改动，本轮未综合验证。硬件资源/时序及实板结论只对应冻结位流。`verify_build.py` 已报告 `hardware_source_matches_bitstream=false`，当前 `run_sensors.py` 会在操作硬件前拒绝该未构建组合；需完成源码核对、重构建与验证。详见 `fusion/ti60_multimodal/validation/ir_scheduler_20261004/hardware_source_audit.json`。
- 下一步先核实持续运行与日志可靠性，再完成实时帧银行所有权、cache 管理、缩放量化及可调度 AI/运动分析。清晰度继续暂停、真实采集 60fps 待完整模式表，事件与报警尚未接入。

详细异常证据、验证边界与后续排查顺序见 [本轮诊断记录](validation/ir_scheduler_20261004/README.md)。

## 历史：2026-10-03 阶段 2 接通

2026-10-03：当前源码已接入 SC431HAI、共享 DDR 三缓冲和视频/热图/温湿度同屏。Sapphire CPU 运行红外校准并读取 SHT30，TinyML 硬件保留。实时 AI、运动分析和事件报警尚未接入。阶段 2 架构、布局、内存和寄存器见 [STAGE2.md](STAGE2.md)。

最新实板证据：[run_20261003_224853](validation/run_20261003_224853/run_result.json)、[统计](validation/run_20261003_224853/measurement_summary.json)、[视频统计](validation/run_20261003_224853/video_summary.json)。临时 JTAG、53,834 字节程序 DDR 全量读回一致，未写 Flash。连续 120.19 秒共记录 3584 个完整摄像头帧并全部发布；稳态 29.996 fps，坏帧、行溢出、丢弃、AXI 读写错误及 HDMI FIFO 下溢均为 0。红外 462 条、SHT 117 条，序号连续、红外子页交替，0 重试/错误，显示提交应答通过。SHT 十进制/十六进制/二次读取对照一致。

用户回复“现在能了”，确认屏幕恢复显示；视频运动、热图响应、颜色方向尚未逐项再次确认，不能把 UART 代替这些目视项目。上一轮的 4 条 SHT 日志序号异常在本版未复现，根因尚未证明解决，保留冗余诊断；两分钟测试不等于最终 30 分钟稳定性验收。

当前位流 SHA256：`aeb4f6821e6222552fd73e5a8507028ed68b4a7d3293d274baeeeb3f88e2e467`；程序：`46547462a884b84a15219e8532204d174496debcb240fe93f71f72030863e212`。本版 CSI 仍为 1920×1080 RAW10 约 30fps，缩放显示为 1280×720，HDMI 扫描为 1080p60Hz，三个数字不可互换。

本阶段修复及实测过程（原始日志、匹配源码与失败结果均保留）：

- `validation/run_20261003_222420/`：摄像头第一条命令 NACK，定位为新适配层遗漏 J4 高有效复位反相，已修复。
- `validation/run_20261003_223326/`：初始化和曝光回读正常，但所有视频帧被拒绝。原新行桥错误地把 CSI DE 下降沿当成行结束。
- `validation/run_20261003_224207/`：改为累计有效像素后，120.20 秒采集 3585 个完整帧并全部发布，稳态 30.000 fps，视频错误/丢帧/下溢均为 0；实测每帧约 226,000 个 DE 连续段，证明存在大量行内空隙。红外 462 条/SHT 117 条，红外无错误和重试，但事后发现 4 条 SHT 十进制序号异常，已撤回脚本最初的整体 PASS，原日志不改。
- `validation/run_20261003_224853/`：相同位流，仅固件增加 SHT 序号的十六进制及二次读取对照，两分钟并发验证通过；同时收紧验收脚本，要求序号连续和表示一致。用户先反馈黑屏，随后回复“现在能了”，记录为当前已能显示；未替代视频运动和热图响应的逐项目视确认。

以下阶段 1 数据是已验证的历史恢复点，不能替代当前阶段 2 的验证。离线阶段 2 新增 4 项视频 RTL、17 项摄像头初始化/空间纹理检查；实际链接固件 13 项重新通过，详细记录在 `validation/`。

用户要求融合产品面向赛题三。新应用不含六图数组、图片 ROM、轮播、图片进度或六图自检；原摄像头、传感器和 AI 基线保留。最新设计依据见 [融合方案](../../analysis/multimodal_fusion_20261003/README.md)。

## 历史恢复点：2026-10-03 21:38 阶段 1

证据：[run_20261003_213831](validation/run_20261003_213831/run_result.json)，统计：[measurement_summary.json](validation/run_20261003_213831/measurement_summary.json)。

- 临时JTAG读到器件ID `0x10660A79`；程序 **52,738字节** DDR全量读回一致，未写Flash。
- 连续 **120.17秒**：462次有效热图发布、117次有效SHT采样；红外序号连续、子页交替，显示提交全部应答。**0次NACK重试、0错误状态、仅启动时初始化1次**。
- 红外读取中位 **60 ms**、校准/发布准备中位 **155 ms**；子页更新中位 **254 ms**（约3.93次/秒，完整两子页约1.97对/秒）。SHT采样约每1022 ms一次。以上包括阶段1软件工作，不能当成摄像头帧率或混合AI负载结果。
- 当前位流 SHA256：`7aac5039decd90ba8f79aad7561f7472d037a68aecc88f16433e2d0cb34994e1`；程序：`81c733809d447884ca6cf6fd69bbc35cb368955d2acbf89e87973db784173070`。匹配源码、ELF/程序、位流、测试、时序、引脚、DDR读回、UART原文均归档。
- 用户目视确认来自此前同布局368kHz版的热图响应；这版只改红外分频，页面RTL未变，未把UART应答冒充新的屏幕目视结果。
- 此次仅验证2分钟运行，未完成最终30分钟多模态并发测试；此前间歇失联的根因仍未单独确认。阶段1可以作为后续开发基线。

## 当前入口

- 硬件工程：`Ti60_Multimodal.xml`，顶层 `src/tinyml_soc_top.v`。
- 外设接口：`src/fusion/fusion_apb.v`；SHT 跨时钟快照：`fusion_sht_cdc.v`。
- 当前 HDMI：`fusion_sensor_hdmi.v` 与 `src/fusion/fusion_page.v`；阶段 1 的 `thermal_page.v` 仅作为保留参考。
- 软件：`../demo_multimodal/software/standalone/tinyml_pdti8/src/main.cc`。目录名沿用 SDK，但当前程序是传感器程序；TinyML 软件源留待实时摄像头阶段，不调用 Invoke。
- 源码来源指纹：`validation/source_origins.json` 与 `camera_sources.json`；含新增摄像头来源的 1044 个来源文件未变，见 `baseline_preservation.json`。
- 构建、引脚、时序与当前产物指纹：`validation/build_verified.json`。

当前页面为左侧 1280×720 视频窗、右侧 512×384 热图、底部温湿度。右下事件/置信度显示 `--`，并明确提示融合判断尚未启用。页面坐标和显示格式见 STAGE2；UART 发布/应答与外接屏幕目视验收分别记录。

## 构建与验证

在工作区根目录执行：

```powershell
& .\fusion\scripts\build_hardware.ps1 -Flow interface
& 'C:\Users\20558\AppData\Local\Programs\Python\Python312\python.exe' -B fusion/scripts/refresh_constraints.py
& .\fusion\scripts\build_hardware.ps1 -Flow map
& .\fusion\scripts\build_hardware.ps1 -Flow pnr
& .\fusion\scripts\build_hardware.ps1 -Flow pgm
& 'C:\Users\20558\AppData\Local\Programs\Python\Python312\python.exe' -B fusion/scripts/build_firmware.py
& 'C:\Users\20558\AppData\Local\Programs\Python\Python312\python.exe' -B fusion/tests/run_rtl.py
```

`pgm` 只生成位流。`prepare_project.py` 是一次性建立目录脚本，已有目录会拒绝覆盖；不要拿它更新当前工程。`port_sensor_firmware.py`、`connect_camera_stage2.py` 是历史移植脚本，不能重跑来更新当前工程，否则会覆盖后续修复。正常构建不依赖这些脚本。

阶段 2 另运行 `fusion/tests/run_video_tests.py`（4 项视频 RTL）、`fusion/tests/run_camera_reuse_tests.py`（17 项初始化/ISP 场景）。完成全部 RTL、固件测试与 map/pnr/pgm 后，运行 `fusion/scripts/verify_build.py` 核对当前源码指纹、测试、时序和物理引脚；不得拿历史 PASS 代替新版本验证。

固件 ISA 验证使用已安装 `tools/thermal_python` 中的 Unicorn/pyelftools，运行 `fusion/tests/firmware_emulator.py <case>`。当前 19 场景：normal、cold、hot、timer_wrap、steady、nack、transient_nack、overrun、bus_timeout、no_new_data、bad_eeprom、bad_math、wrong_id、delayed_bus、delayed_display、display_timeout、recover_nack、recover_timeout、recover_no_data。可运行 `fusion/tests/run_firmware_tests.py` 一次完成全部场景。它运行实际链接的 `.bin`，不模拟 TinyML 自定义指令；校准/显示算法按独立合成辐射模型核对，仿真温差不能当作实物测温精度。

4 个 RTL 测试覆盖新 APB 的地址/忙写拒绝、图文提交、接收 RAM、SHT 异步冻结快照，以及复用总线的 832 字突发/拉伸和显示的完整 1080p 时序/热图/失效状态。832 字总线仿真耗时 60.061 ms（100 MHz / 100 分频；约250 kHz I²C）；PNG/PPM 来自仿真，不能当成显示器截图。

当前阶段 2 I3 构建：XLR **59,304/60,800**、RAM **233/256**、DSP **53/160**；已约束路径 setup/hold 最小余量 **+0.216/+0.026 ns**。79 个引脚核对通过；SHT=C5/A4、红外=B3/C3，两路独立 3.3 V I²C。J4 摄像头、DDR/TMDS/UART 引脚与各自已验证来源一致。仍有继承的时钟域排除、受保护 RTL latch 告警和组合回环切断；不是全 CDC/所有路径签核。仅余 1,496 XLR、23 RAM，后续新增硬件须重新评估资源和时序。

初次构建发现外围 XML 未复制到 GPIO，已修复 `comp_gpio` 名称及 schema 节点顺序，并重新 interface→map→pnr→pgm；没有下载那版缺引脚的位流。物理引脚不能仅凭 interface/map 的 PASS 判断。

## 总线与缓冲约定

APB 基址 `0xF8100000`，时钟 100 MHz。所有寄存器按 32 位对齐访问。

| 偏移 | 含义 |
|---|---|
| `0000 / 0004 / 0008` | 系统 ID `4D4D4631`、版本 `00010000`、单调毫秒计数 |
| `1000 / 1004` | 显示 ID `46555331`；状态 bit0 busy、bit1 ack、bit2 ready |
| `1010 / 1018` | 显示提交序号；写提交 |
| `1020..1054` | 14 字元数据；写暂存、读已提交快照 |
| `2000 / 2004 / 2008` | SHT 状态、`{raw_t,raw_h}`、符号位31及温度BCD |
| `200C / 2010 / 2014` | SHT 快照接收毫秒、湿度BCD、序号 |
| `3000 / 3004 / 3008 / 300C` | 红外 busy/start/read、16位寄存器地址、写数据、字数1..832 |
| `3010 / 3014 / 3018 / 301C` | 总线结果、当前毫秒、完成次数、完成毫秒 |
| `4000..4CFC` | 832 字红外接收缓冲，低16位有效；成功完成后读取 |
| `6000..6BFC` | 768 个热图颜色索引，低8位有效，写非显示银行 |

图像/元数据提交后冻结至像素域垂直消隐 ACK。忙写、非法地址、未对齐和图像读返回 APB error，不无限阻塞总线。软件先检查 ID/版本，等待显示有 2 秒超时。

SHT 的记录时间是 **CPU 域收到完整快照的时间**，不是精确转换时刻。红外当前仅记录总线完成/软件发布时刻；各子页采样年龄、摄像头时间对齐及过期模态剔除留待后续。SHT 滑动平均/异常值处理也尚未加入，不能因此认定赛题预处理完整。

软件链接区为 `0x1000..0x03FFFFFF`。S1 现在连接视频 AXI 主端，RGB565 三个银行从 `0x06000000/0x06200000/0x06400000` 起；原 RAW 预留区本阶段未使用。完整地址与所有权见 STAGE2。不能用旧摄像头从 0 起写的缓存覆盖应用。当前没有第二个 PicoRV32 和 128KiB 传感器程序 RAM。

## 上板与后续边界

`../scripts/run_sensors.py` 会重新枚举 FT4232 B/JTAG 和 C/UART，校验源码/位流/程序指纹，临时配置并全量读回 DDR，再按验证过的 reset/load/resume 顺序启动。仅临时 JTAG，不写 Flash；关闭串口后板上程序继续运行。断电后需要重新加载。

首轮 `validation/run_20261003_212746/` 已接通两类传感器和 HDMI，用户明确“显示正常，热图能随手变化”。完整日志也包含第42秒的一次 NACK 和重新初始化，故该轮不作为不中断稳定性通过。验收脚本已修正，不能只检查有效帧数而忽略错误状态。

120秒扩展测试 `run_20261003_213119/` 发生45次重试、23次错误状态和10次成功重新初始化；用户随后确认不小心碰动模块/接线。该轮明确判为稳定性未通过，物理根因未确认。随后250 kHz（原约368 kHz）静止接线测试已通过，4 Hz子页配置保持不变。接线状态与速率同时变化，这不是能单独归因的A/B试验。

当前固件对 NACK 仅重试整个幂等事务，最多3次，每次失败都记录；接收缓冲仅在完整成功后消费。持续失败仍显示错误并重新初始化，不用旧温度冒充有效数据。重试不代表已经确定或消除了物理总线根因。

同屏完成后下一阶段接真实帧 AI/运动分支。2026-10-04 已将红外改为分步服务，但计算总量仍约 170 余毫秒/子页，4Hz 子页占用显著 CPU 时间；初始化参数提取仍约 91ms。尚须加入实际帧号/银行所有权、cache 管理和图像缩放量化，并让 AI 算子间能够返回传感器服务、实测混合负载。不能把红外分批等同于 AI 已可并发。现有 TinyML 硬件被保留，但本版没有执行 Invoke，不能把同屏记录当作实时 AI 验收。

60fps 摄像头仍需要匹配 SC431HAI 的完整模式表；当前阶段不改变该结论。任务3两项拓展和事件场景也尚未最终选择。

阶段 2 实施前的算术预算保留在 [历史预算](../../analysis/multimodal_fusion_20261003/stage2_budget_after_sensor_bringup.json)；当前资源以本版实际构建报告为准。

加载脚本使用Efinity自带pyserial运行时。`bin/python3.bat` 的退出码可能被包装脚本覆盖；上板是否通过以 `run_result.json`、原始日志和 `analyze_sensor_run.py` 为准，不只看shell退出码。
