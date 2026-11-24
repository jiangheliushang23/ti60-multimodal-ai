# 参考资料

| 资料 | 版本及用途 |
| --- | --- |
| 易灵思 FPGA 创新设计赛道选题指南 | 赛题三「多模态 AI 智能终端」，印刷页 9–11。原件来自赛事资料包 |
| SC431HAI 数据手册 | 思特威 V1.1（2024-08-16），场同步、RAW10、电气及寄存器。原件来自摄像头资料包 |
| Ti60F225I3-V4 DEMO 板软硬件设计说明 | `260920`，开发板接口、供电、J4 与基础示例。原件来自 V4 开发板资料包 |
| Ti60F225A_V4_SCH | V4 主板原理图，核对 MIPI、HDMI、扩展接头和 RGMII。原件来自 V4 开发板资料包 |
| [Efinix Ti60 Data Sheet](https://www.efinixinc.com/docs-html/dsti60/topics/top_ds_titanium.html) | 器件资源、封装与接口时序 |
| [Efinity 工具和开发板资料](https://www.efinixinc.com/support/) | 软件、参考工程和 IP Manager。比赛使用的 TinyML 指南为 UG-TinyML Draft |
| [Sapphire RV32 SoC User Guide](https://www.efinixinc.com/support/docsdl.php?s=ef&pn=SAPPHIREUG) | RISC-V 软核、外设、BSP 与工具链 |
| [MLX90640 手册](https://media.melexis.com/-/media/files/documents/datasheets/mlx90640-datasheet-melexis.pdf) · [Melexis API](https://github.com/melexis/mlx90640-library) | 32 × 24 阵列、两子页、校准和温度计算 |
| [Sensirion SHT3x-DIS](https://sensirion.com/media/documents/213E6A3B/63A5A569/Datasheet_SHT3x_DIS.pdf) | I²C 测温湿、CRC 和转换公式 |
| YS-V6 / SYN6658 配套资料 | 模组使用手册（2021-02-27）和芯片开发手册 V1.42，核对 UART 9600 和 R3＋R6 配置。原件来自 2023-03-01 模组资料包 |
| [YOLOv5 v6.0](https://github.com/ultralytics/yolov5/releases/tag/v6.0) · [量化训练论文](https://openaccess.thecvf.com/content_cvpr_2018/html/Jacob_Quantization_and_Training_CVPR_2018_paper.html) | YOLOv5n 架构和 INT8 量化背景 |
| [TensorFlow Lite Micro](https://github.com/tensorflow/tflite-micro) | 量化算子及内存分配 |
| [lwIP 2.1 系列](https://www.nongnu.org/lwip/2_1_x/index.html) · [RFC 768](https://www.rfc-editor.org/info/rfc768/) · [RFC 9110](https://www.rfc-editor.org/info/rfc9110/) | RISC-V TCP/HTTP、PC UDP 传输及 HTTP 语义 |
| [Android WebView](https://developer.android.google.cn/develop/ui/views/layout/webapps/webview?hl=zh-cn) | Android App 加载局域网监控网页 |

报告第 43–44 页列出架构、检测、跟踪和跌倒分析文献。报告的原理图节选取自 Ti60 V4 板卡资料。 [作品报告](report.pdf)
