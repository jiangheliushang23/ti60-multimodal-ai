# Ti60 Multimodal AI

基于 Ti60F225I3 V4 的多模态 AI 智能终端，对应易灵思 FPGA 创新设计赛道「赛题三」。本仓库用于团队源码协作与任务管理。

## 当前状态（2026-10-04）

- SC431HAI 摄像头、GY-MCU90640 红外、SHT30 已接入；HDMI 左侧实景、右侧热图、底部温湿度，用户已确认显示正常。
- 摄像头为 1920×1080 RAW10、约 30fps；全视野缩放为 1280×720 RGB565，HDMI 输出 1920×1080@60Hz。HDMI 刷新率不代表采集帧率。
- 最近 1800.16 秒观察中，视频约 29.99974fps，红外连续发布 7080 次，视频错误计数与红外重试/错误均为 0。
- SHT 日志仍有序号、状态与时间戳异常，整体遥测验收未通过。**按用户要求暂停该问题排查，保留待办。**
- 实时 AI、运动分析、事件融合及报警尚未集成；现有模型仅输出有人/无人，不输出人体框或跌倒结果。
- **当前硬件源码包含未重新构建的模块拆分，与已验证位流不同。** 不能将旧位流的时序和实板结果算作当前源码通过。
- 六张静态测试图只属于历史模型测试，不纳入融合产品需求。清晰度问题暂缓，真实采集 60fps 等待完整传感器模式表。

私有仓库：https://github.com/jiangheliushang23/ti60-multimodal-ai 。任务认领见 [已登记的 Issues](docs/BACKLOG.md)。

## 从这里开始

| 内容 | 入口 |
|---|---|
| 当前状态、冻结版本、验证边界 | [项目状态](docs/STATUS.md) |
| 阶段任务与验收条件 | [路线图](docs/ROADMAP.md) |
| 环境与构建说明 | [构建指南](docs/BUILD.md) |
| 分工、分支与 PR 约定 | [协作指南](docs/TEAM_WORKFLOW.md) |
| 硬件工程 | [Ti60_Multimodal.xml](fusion/ti60_multimodal/Ti60_Multimodal.xml) |
| 顶层 RTL | [tinyml_soc_top.v](fusion/ti60_multimodal/src/tinyml_soc_top.v) |
| 固件入口 | [main.cc](fusion/demo_multimodal/software/standalone/tinyml_pdti8/src/main.cc) |
| HDMI、内存、寄存器说明 | [STAGE2.md](fusion/ti60_multimodal/STAGE2.md) |
| 第三方来源与依赖 | [THIRD_PARTY.md](docs/THIRD_PARTY.md) |

本仓库提交源码、IP 配置/必需初始化数据及部分测试夹具，不提交 Efinity、工具安装包、大型综合布局布线产物、完整历史运行快照、聊天导出或本机服务配置。历史文档中的未随仓库上传的证据链接，只能在维护者原工作区访问。原始工作区与恢复资料保留。
