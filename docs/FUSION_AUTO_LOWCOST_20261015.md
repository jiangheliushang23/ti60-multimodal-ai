# 低开销自动曝光/白平衡融合基线

2026-10-16 将原隔离工程的已验证硬件和固件同步到本分支的标准源码路径。
原始硬件、固件、测试输入及产物均已与冻结清单核对；文本换行由 Git 规范化。
本次保留当前开发工作区，独立整理提交；没有重新配置开发板或写入 Flash。

## 源码与复现

| 内容 | 入口 |
|---|---|
| Efinity 硬件工程 | [Ti60_Multimodal.xml](../fusion/ti60_multimodal/Ti60_Multimodal.xml) |
| 外围/引脚/时钟约束 | [Ti60_Multimodal.peri.xml](../fusion/ti60_multimodal/Ti60_Multimodal.peri.xml) |
| 固件与非阻塞调度 | [main.cc](../fusion/demo_multimodal/software/standalone/tinyml_pdti8/src/main.cc) |
| 自动控制状态机 | [camera_auto.h](../fusion/demo_multimodal/software/standalone/tinyml_pdti8/src/camera_auto.h) |
| 整数曝光/白平衡决策 | [camera_control.h](../fusion/demo_multimodal/software/standalone/tinyml_pdti8/src/camera_control.h) |
| 统计/寄存器 RTL | [camera_auto_stats.v](../fusion/ti60_multimodal/src/fusion/camera_auto_stats.v)、[camera_auto_apb.v](../fusion/ti60_multimodal/src/fusion/camera_auto_apb.v) |
| 自动控制测试和冻结参考 | [camera_auto](../fusion/tests/camera_auto/) |
| 发布源码指纹 | [source_manifest.json](validation/fusion_auto_lowcost_20261015/source_manifest.json) |
| 原构建/实板摘要 | [summary.json](validation/fusion_auto_lowcost_20261015/summary.json) |
| 五分钟原始复核摘要 | [complete_review.json](validation/fusion_auto_lowcost_20261015/complete_review.json) |
| 用户目视反馈 | [user_acceptance.json](validation/fusion_auto_lowcost_20261015/user_acceptance.json) |

Windows x64，Efinity 2026.1、配套 RISC-V IDE 2026.1、Python 3.12、Icarus Verilog 和宿主 g++。
商业工具及本机工具目录不上传；工具路径不同请适配构建脚本。
下列命令从仓库根目录执行，均不访问开发板：

```powershell
# Icarus/g++ 不在默认路径时显式指定安装位置。
$env:IVERILOG = 'C:/path/to/iverilog/bin/iverilog.exe'
$env:VVP = 'C:/path/to/iverilog/bin/vvp.exe'
$env:CXX = 'C:/path/to/g++.exe'
python -B fusion/tests/camera_auto/run.py
python -B fusion/tests/camera_auto/control_test.py
python -B fusion/tests/check_subsystem_ports.py
python -B fusion/scripts/build_firmware.py
& ./fusion/scripts/build_hardware.ps1 -Flow interface
python -B fusion/scripts/refresh_constraints.py
& ./fusion/scripts/build_hardware.ps1 -Flow map
& ./fusion/scripts/build_hardware.ps1 -Flow pnr
& ./fusion/scripts/build_hardware.ps1 -Flow pgm
```

`pgm` 只生成位流。完整综合/布局布线和重新上板仍应绑定新产生的输入指纹、时序与产物，
不能把本报告的旧结果直接作为重构建结果。旧 `run_camera_reuse_tests.py`、
`verify_build.py`、`run_sensors.py` 的断言/证据格式对应早期冻结版本；
尚未改为本 AE/AWB 基线，不可绕过匹配检查加载。维护者的匹配恢复入口仍在本机隔离工程。
若要给队友交付可直接恢复的 BIT/固件，需另外提供匹配恢复包；本提交是源码交付。

## 行为与接口

保留 SC431HAI 初始化、CSI 模式、减黑电平16、去马赛克、Gamma、缩放、DDR 三缓冲及 HDMI 布局。
初始曝光2989半行、模拟增益0x8320、数字增益1倍保持。
FPGA 对完整有效 RAW 帧做稀疏亮度/颜色统计，现有 RISC-V 采用整数决策，
通过原 I2C 引擎分步写入并读回曝光/模拟增益；更新后等待4帧再采样。
白平衡为灰世界、1/8平滑和死区4，R/B Q8.8 在 ISP SOF 成对更新，G固定256。
无额外图像缓冲；I2C超时、NACK、模式异常或读回不符时冻结自动控制。

旧 APB `0xF8105000` 保留，新增 `0xF8105100`（ID `0x41555431`）。
新增窗口字节偏移：0x00 ID；0x04 busy；0x08 请求统计/CSI序号；
0x0C/0x10 AE绿色总和/clip；0x14..0x28 R/G/B总和及样本数；
0x2C/0x30 固定AE样本数16320/总样本32640；0x34 ISP SOF计数；
0x38/0x3C I2C命令/启动；0x40 I2C返回；0x44 R低16位/B高16位增益。
CSI序号、ISP SOF和HDMI显示帧号不可混用；CPU服务与红外分批主循环协作。

## 已完成的历史验证

- 28项 RTL 运行、615个 CPU 决策与冻结 FPGA 参考逐项一致，另覆盖自动控制调度和异常冻结。
- 全工程59,829/60,800 XLR，较端口修复基线净增267；233/256 RAM、51/160 DSP，剩971 XLR。
- 原引脚/时钟约束不变，已约束 setup/hold 最差 +0.156/+0.026ns；不是完整 CDC/时序签核。
- 2026-10-15 21:06 第二次完整重载：JTAG ID/完成日志与 DDR 固件全量读回通过。
- 300.140秒：CAM299、IR1168、AUTO294，摄像头约30fps；视频错误、红外重试/异常、自动fault、FATAL均0。
- 用户明确反馈“三项及画质都正常”。原记录时间和路径保留，不能视为本次重新运行。

匹配 BIT SHA256：`c40afb2b4d015d56e2d0f0689612d7319fe119b043df7f998c82cab4be029fdd`。
匹配固件 SHA256：`73a2c0106062c7e6661b001b97a62e2151e3364e004484ea4ba0440f2460b5e9`。
大型位流、生成目录、完整日志与历史恢复副本不进 Git；保留必要 IP/ROM 初始化数据。

## 未完成和关键异常

尚未接实时AI、运动分析、跌倒/融合报警、以太网预览或板端HTTP；CSI仍约30fps，非60fps。
SHT日志与光学清晰度排查继续暂停，没有芯片温度实测，五分钟不等于长期/热验证。
首次晚间重载出现无UART/图像及 `timed out while waiting for target halted`，完整重载恢复，根因未明。
早期内联固件出现 `FATAL trap mcause=00000004 mepc=00001618 mtval=000009e6`；
新增 `camera_service()` 禁止内联后未复现，不据此宣称根因修复。
下午主机采集曾报 `ClearCommError failed (PermissionError(13, '拒绝访问。', None, 5))`，
该记录不是板端trap，也不是完整五分钟通过的依据。

## 本次发布检查（2026-10-16）

独立检出目录重新通过28项RTL运行、615个CPU参考案例及调度检查、150个子系统端口检查。
固件重新编译为59,010字节，SHA256与上述实板验证版本完全一致。
484个发布输入已按Git暂存内容核验，57个工程文件引用均可找到；未重新综合或访问开发板。
结果见 [publication_check.json](validation/fusion_auto_lowcost_20261015/publication_check.json)。
