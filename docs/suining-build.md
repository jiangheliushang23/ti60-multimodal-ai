# BOM、接线与运行

适用于 `yolo_auto_v24_transfer_opt` 和 **Ti60F225I3-V4**。机械图记录摄像头和红外模块的试配样机。[外壳结构](images/enclosure-prototype.png)

## 硬件清单

| 数量 | 设备 | 连接或用途 |
| ---: | --- | --- |
| 1 | Ti60F225I3-V4 开发板及原配电源 | J4 摄像头、HDMI 输出、千兆网口、USB 下载和调试 |
| 1 | SC431HAI MIPI 模组及匹配的 22Pin FPC | 主板 J4，对照板卡的 Pin 1 和接触面方向 |
| 1 | SHT30 模组 | J28 独立 I²C，采集环境温湿度 |
| 1 | GY-MCU90640 模组 | J28 独立 I²C，采集 32 × 24 红外温度 |
| 1 | YS-V6（SYN6658）语音模块，R3＋R6 | UART、3.5 mm 音频输出 |
| 1 | 22Pin、0.5 mm FPC 转接板及排线 | 语音模块返回信号接入主板 J5-3 |
| 各 1 | HDMI 屏、HDMI 线、有源音箱、音频线 | 本地显示和语音 |
| 各 1 | USB 数据线、支持千兆的网线和 PC 网口 | 临时下载、日志和局域网监控 |

## 传感器与语音

| 模组 | 模组端 | 开发板端 |
| --- | --- | --- |
| SHT30 | SCL / SDA | J28-32（C5）/ J28-34（A4） |
| GY-MCU90640 | SCL / SDA | J28-37（B3）/ J28-39（C3），同名连接 |
| GY-MCU90640 | PS | 接公共地，选择原生 I²C。B0、RX、TX 悬空 |
| YS-V6 | RXD | J28-40（A12），FPGA 发往模块 |
| YS-V6 | TXD | J5-3（B12），经 FPC 转接返回 FPGA |
| YS-V6 | RDY | 悬空 |
| 三个模组 | 电源和公共地 | J28-1 为 3.3 V，J28-5 或 J28-6 为 GND |

针号按比赛用板的扩展子板接法记录，换板时按主板和扩展板原理图核对。接线时断电并核对 3.3 V 和 GND，J28-3 为 5 V。语音 UART 为 9600、8N1。主机日志独立使用 USB 串口，500000、8N1、GBK。

## PC 网页与 Android

PC 服务用 Python 3.11+。离线预览可直接在仓库根目录执行：

```powershell
python -m pip install -r network_monitor/requirements.txt
python -B -u -X utf8 network_monitor/host/fall_monitor.py --bind 127.0.0.1 --http-bind 127.0.0.1 --http-port 8002
```

[打开 PC 预览](http://127.0.0.1:8002/monitor.html)。连接板卡时，把直连 PC 网口设为 `192.168.0.3/24`，命令中把 `--bind` 改为 `192.168.0.3`。板卡向 PC 的 UDP 8080 发送视频及事件。板端 HTTP 入口为 `http://192.168.0.2/`，提供 `/api/status`、`/api/events` 和 `/snapshot.bmp`。

Android App（Android 8.0+）连接 PC 网页服务。使用 PC 的局域网 IP 和 `8002` 端口，`--http-bind` 配置为该局域网接口。安装包和 SHA-256 位于项目的 [Release](https://github.com/jiangheliushang23/ti60-multimodal-ai/releases/tag/v24-transfer-opt)。Windows 上可用 JDK（含 `javac` 和 `keytool`）从源码构建，`TI60_JAVA` 指向 JDK 根目录。脚本会下载 Android SDK 平台与构建工具，并使用本机签名文件。

```powershell
$env:TI60_JAVA = 'C:/path/to/JDK'
python -B -X utf8 mobile_app/build_android.py
```

## FPGA 和 RISC-V

使用短英文检出路径。历史构建使用 Efinity `2026.1.132.4.5`，RV32 编译工具随 Efinity RISC-V IDE 提供。IP 目录的 `settings.json` 保存原 IP 版本和配置。授权补充文件包括 Sapphire、CSI RX、DMA 和 FIFO 的生成文件、DDR3 与 TinyML 等配套 RTL、Sapphire ROM、TinyML 库与模型及回归数据。[工具入口与资料](references.md) · [逐文件路径和哈希](build-dependencies.json)

如果手头已有获准使用的 v24 完整工程，指向包含 `fusion/` 的工程根目录即可补齐。Efinity IP 也可以用对应版本的 IP Manager 按配置生成，DDR3 和示例 RTL 从匹配的开发板交付取得。对照清单取得与比赛快照一致的适配模型、回归输入和库。生成器版本产生的差异请作为独立构建记录。

```powershell
python -B scripts/board_dependencies.py --from-project C:/path/to/Ti60_v24
python -B scripts/board_dependencies.py
$env:TI60_EFINITY = 'C:/Efinity/2026.1'
$env:TI60_RISCV_BIN = 'C:/Efinity/efinity-riscv-ide-2026.1/toolchain/bin'
python -B -X utf8 delivery/build_yolo_auto_hardware.py --flow all
python -B -X utf8 fusion/demo_multimodal/software/standalone/tinyml_yolo_static/build.py --multimodal-live
```

也可在 Efinity GUI 打开 `fusion/ti60_yolo_auto/Ti60_Multimodal.xml` 运行构建。源码快照保留同名硬件和固件入口，环境变量和汇编资产路径已改为可移植配置。工具产物分别写入 FPGA `outflow/` 和固件 `build_multimodal_live/`。

实板复现使用已核对的同版 BIT 与 BIN。取得团队原配套产物时先对照 [v24 发布记录](v24-release.json) 中的两个 SHA-256，通过完整交付工程的 RISC-V IDE 预检及 DDR 完整读回后启动。外设验收依次检查摄像头进帧、HDMI 热图与环境参数、语音和两种网页入口。板测状态按每次实际运行的 BIT、BIN 和测试条件记录。
