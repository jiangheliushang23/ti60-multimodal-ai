# 桌面上位机接口草案 v1（2026-10-08）

状态：桌面端已按本草案实现；人体算法与 Web/以太网队友尚未确认或实现。接口调整先讨论，再同步桌面代码、样例、测试和板端代码。

## 分工与赛题边界

- 人体识别队友输出真实算法结果与对应帧号/时间戳；当前模型为有人/无人分类，暂不要求它输出人体框、多人轨迹或跌倒结论。
- Web/以太网队友负责 Ti60 端采集/结果的封装、传输与板端轻量 HTTP 服务。
- 用户负责 PC 桌面程序：接收、显示、记录、报警提示和导出，不将模型推理或赛题要求的本地事件决策迁移到 PC 来代替 FPGA。
- 千兆以太网扩展要求经 RGMII 上传事件类型、时间、位置、置信度、缩略图到 PC 服务器；Web 扩展要求 FPGA 内 RISC-V 提供轻量 HTTP 服务。桌面 TCP 接收是 PC 服务器端的一种草案，不能代替这两项板端验收。

## 草案传输

PC 启动 TCP 接收，设备主动连接。默认联调地址 `127.0.0.1:9001`，正式联调改为 PC 的局域网接口。UTF-8 JSON，每条消息末尾加 LF，一条消息最多 1 MiB；TCP 的 recv 边界不等于消息边界。同一窗口同时接收一台设备。

公共字段：

| 字段 | 含义 |
|---|---|
| version | 固定整数 1 |
| type | telemetry / inference / thermal / video / event |
| device_id | 设备标识 |
| boot_id | 每次设备启动生成不同标识，用于区分序号复位 |
| seq | 非负整数，同一 boot 内每种 type 严格递增；重发可使用原序号 |
| timestamp_ms | 设备此次启动后的采样/事件时刻，uint32；不是 PC UTC 时间 |
| data | 对应类型的数据对象 |

PC 另存接收时间用于展示/导出，不把 PC 接收时间冒充设备采样时间。不同类型的序号独立，同类型重复/倒退序号不再次更新画面。重启或断线后重建状态；像素/AI/环境字段各自计算 5 秒到达超时。本机过期策略不等于板端多传感器时间对齐已完成。

```json
{"version":1,"type":"inference","device_id":"ti60-01","boot_id":"boot-1","seq":8,"timestamp_ms":12345,"data":{"frame_id":370,"valid":true,"person_score":0.88,"inference_ms":195.2}}
```

## 数据类型

| type | data | 规则 |
|---|---|---|
| telemetry | temperature_c、humidity_pct、sht_valid、ir_min_c、ir_max_c、ir_center_c、ir_valid、camera_fps、camera_frame_id、camera_errors | 部分更新；缺失字段不刷新。数值可为 null，表示不可用；valid=false 清除相关有效读数 |
| inference | frame_id、valid、person_score、inference_ms | 置信度 0..1；valid=false 不显示分数。只显示真实 Invoke 结果，不由 PC 猜测人体状态 |
| thermal | width=32、height=24、pixels_centi | 768 个摄氏温度百分之一的有符号整数，按行排列；无效像素为 null。完整矩阵才更新，min/max 统计不能替代像素 |
| video | frame_id、jpeg_base64 | 一张完整 JPEG，用于接口联调/低帧率预览；最终视频传输仍待队友确定 |
| event | event_id、event_type、confidence、frame_id | event_id 在当前 boot 内唯一；confidence 和 frame_id 可省略或为 null。本机确认不发送硬件控制命令 |

首版 event 未实现位置/缩略图归档、控制请求/应答、长期数据库、鉴权/加密、统一时钟映射；千兆以太网扩展完整验收前补齐位置/缩略图等指南字段。不要把当前草案描述成最终赛题完整协议。

## 接口待团队确认

1. 以太网队友是否采用主动连接 PC 的 TCP/JSONL？若选择 UDP、HTTP 或其他传输，调整适配层，不要求其复刻未讨论的草案。
2. 谁生成 device_id/boot_id、采样时间戳和帧号？视频、推理与事件必须可追溯同一帧。
3. 真实像素如何传输？确认图像格式、视频预览帧率、热图完整帧/子页及无效像素规则。
4. 算法最终输出类别、人体位置还是框？事件场景和融合逻辑尚待确认，不预先伪造输出字段。
5. 报警确认和参数修改是否需要下发？首版只在 PC 本机确认记录，板端控制需另行设计请求/应答。

## 当前串口适配

历史 CAM 的 period_ticks 为 50 MHz 计数，PC 按 50,000,000/period_ticks 显示采集帧率。SHT 检查 status=1、三个 seq 表示一致、非负有效年龄、BCD/数值范围；异常记录不冒充有效读数。IR 仅解码 min/max/center，绝不生成不存在的完整热图。这是只读历史数据处理，不修改或解决此前暂缓的板端 SHT 异常。
