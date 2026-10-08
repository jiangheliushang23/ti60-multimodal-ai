# 团队协作

## 开始开发

维护者在仓库 Settings → Collaborators 中邀请队员，队员接受后克隆私有仓库。不要在聊天、Issue 或代码中放访问令牌。

```powershell
git clone https://github.com/jiangheliushang23/ti60-multimodal-ai.git
cd ti60-multimodal-ai
git switch -c feature/your-task
```

每项工作对应一个 Issue，写清输入、输出和验收。完成后提交 PR，正文引用 `Closes #编号`，列出测试与尚未验证部分。队友复核后合并到 main。此处是团队约定，尚未配置服务器分支保护规则。

## 已确认分工（2026-10-08）

| 负责人 | 工作范围 | 需要与其他成员约定 |
|---|---|---|
| 用户 | Windows 桌面上位机：显示、事件记录、本机确认、导出 | 传输方式、消息字段、帧号/时间戳、像素和结果来源 |
| 人体识别队友 | 人体识别算法 | 类别/位置/框等真实输出能力、置信度、推理时间和对应帧号 |
| Web/以太网队友 | 板端通信、以太网上报、RISC-V HTTP 服务 | 设备端接口、PC 接收方式、图像/热图格式、重连策略 |

姓名/GitHub 账号尚未提供，暂按角色记录，不设置 Issue assignee。板级重构建/集成、FPGA 运动分析、融合决策及本地报警的负责人仍需团队认领，不能假定已分配。

桌面代码见 [host/desktop](../host/desktop/README.md)，[通信草案](HOST_PROTOCOL.md) 供讨论，当前不代表通信队友已经认可或实现。顶层、XML、外围约束、公共寄存器与 DDR 所有权等修改仍需先协调。

共享开发板同一时刻由一位队员操作。下载/暂停 CPU 会影响其他人的观察，开始前在团队中协调；纯文档、主机测试不操作开发板。上板前检查当前源码与产物匹配。临时 JTAG 是当前默认，Flash 固化另行确认。

不要提交整个 outflow/work_syn/work_pnr、日志快照或工具目录。必要验收摘要放 docs，完整二进制与日志通过团队批准的附件方式交付并记录 SHA256。保留源文件已有版权声明。
