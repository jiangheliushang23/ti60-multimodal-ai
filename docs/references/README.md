# 赛题与硬件资料

本目录保存项目此前使用的四份原文 PDF，供团队共同查阅。仓库文件采用英文路径，原始文件名记录如下；PDF 内容与用户提供的文件逐字节一致。

| 资料 | 用途 | 大小 |
|---|---|---|
| [SC431HAI 数据手册](camera/SC431HAI_Datasheet_V1.1.pdf) | 摄像头接口、电气参数、寄存器及模式能力；V1.1。 | 1.61 MiB |
| [Ti60 V4 开发板软硬件设计说明](board/Ti60F225I3_V4_Design_260920.pdf) | 开发板接口、时钟、电源及厂商示例说明；文件名版本 260920。 | 9.30 MiB |
| [易灵思 FPGA 创新设计赛道选题指南](competition/Efinix_FPGA_Competition_Guide.pdf) | 赛题三「多模态 AI 智能终端」任务与验收依据。 | 0.36 MiB |
| [Ti60 V4 原理图](board/Ti60F225A_V4_Schematic.pdf) | 封装球、连接器、电源、电平和线路核对。 | 0.53 MiB |

## 来源文件名

- `camera/SC431HAI_Datasheet_V1.1.pdf` ← `摄像头SC431HAI_数据手册_V1.1.pdf`
- `board/Ti60F225I3_V4_Design_260920.pdf` ← `TI60F225I3-V4 DEMO板软硬件设计说明-260920.pdf`
- `competition/Efinix_FPGA_Competition_Guide.pdf` ← `易灵思FPGA 创新设计赛道选题指南 (1).pdf`
- `board/Ti60F225A_V4_Schematic.pdf` ← `Ti60F225A_V4_SCH.pdf`

## 使用说明

- 赛题指南共 3 页，对应印刷页 9–11。本项目对应「赛题三：多模态 AI 智能终端」；第一页上半部分的前一个赛题内容不属于本项目要求。
- SC431HAI 芯片手册中的供电规格不等于摄像头模组连接器的供电定义；板级接线需结合 V4 原理图、当前约束与实物确认。
- 手册支持的最高分辨率/帧率不等于当前实测能力；项目实现进度见 [STATUS.md](../STATUS.md)。
- PDF 原文保留原厂版权与声明；第三方来源说明见 [THIRD_PARTY.md](../THIRD_PARTY.md)。

[manifest.json](manifest.json) 记录原始文件名、字节数及 SHA256，便于确认队员查阅的是同一版资料。SHA256 校验针对 PDF 原始字节，不经过重排或压缩。
