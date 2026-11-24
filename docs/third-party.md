# 第三方代码与配套资产

| 组件 | 来源与许可 |
| --- | --- |
| AXI 等 RTL 文件 | 保留文件中的 github-efx、Efinix 及其他作者声明和适用的许可全文 |
| MLX90640 API | Melexis，Apache-2.0。[上游许可](https://github.com/melexis/mlx90640-library/blob/master/LICENSE) |
| TensorFlow Lite Micro、FlatBuffers、gemmlowp、ruy | 保留文件中的作者与许可头。[Apache-2.0](licenses/Apache-2.0.txt) |
| lwIP | 相关源码保留 BSD 风格的版权和再分发条款，以及各附加组件的声明。 [lwIP](https://www.nongnu.org/lwip/2_1_x/index.html) |
| Efinity 生成 IP、开发板配套 RTL、ROM、TinyML 静态库 | 遵循对应厂商版本的使用及分发条款。按清单取得所需文件。[构建依赖](build-dependencies.json) |
| 192 × 96 INT8 模型与回归数据 | `raw96x192` 目录保留结构和量化元数据。通过授权渠道取得对应文件。YOLOv5 v6.0 的上游代码采用 GPL-3.0，适配模型的分发依据单独核对。[上游许可](https://github.com/ultralytics/yolov5/blob/v6.0/LICENSE) |

公开 Release 包含项目演示及项目 Android APK。复现工程所需的配对产物校验值见 [v24 发布记录](v24-release.json)。
