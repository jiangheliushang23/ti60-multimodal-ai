## 2026-10-16 最新融合源码入口

本分支已同步低开销 AE/AWB 硬件/固件；优先使用
[当前交付说明](FUSION_AUTO_LOWCOST_20261015.md)中的复现命令和证据边界。
自动控制测试及独立参考已入库，不依赖维护者未上传的 analysis 目录。
以下历史加载/验收脚本尚未全部适配新自动控制合同，不绕过其版本检查。

# 环境与构建

当前脚本以 Windows x64、Efinity 2026.1 和配套 RISC-V IDE 2026.1 为基准。源码仓库不包含商业工具和许可证。

## 工具准备

- 默认 Efinity：`C:/Efinity/2026.1`。
- RISC-V IDE/工具链：`C:/Efinity/efinity-riscv-ide-2026.1`。
- Python 3.12；离线固件仿真依赖 `unicorn==2.1.4`、`pyelftools==0.32`；摄像头空间纹理测试还依赖 `numpy`，在所用 Python 环境安装。
- RTL 测试使用 Icarus Verilog；当前脚本要求 `tools/iverilog/bin/iverilog.exe` 与 `vvp.exe`，该工具目录由队友自行准备。
- 串口/JTAG 工具随 Efinity 安装；加载前重新枚举设备，COM 号和 USB 地址不能照抄。

若工具安装路径不同，先修改对应构建脚本中的路径并单独提交，不改全局系统配置来冒充原机器。建议英文克隆路径。

## 固件（不操作开发板）

```powershell
python -B fusion/scripts/build_firmware.py
python -B fusion/tests/run_firmware_tests.py
```

当前只链接传感器固件，TinyML 模型/源码和库保留用于实时 AI 阶段。目录名 tinyml_pdti8 不代表当前已执行实时 Invoke。

## 硬件（不操作开发板）

```powershell
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

这里 pgm 是生成位流，不是下载。修改后的硬件源码尚未执行完上述全流程；需实际运行并检查告警、时序和测试，不能复用原机旧日志。

仓库保留 ROM `.bin/.hex/.mem`、`tinyml_lib.a`、SDK BSP 和必要 IP 源码，不将它们与编译输出一起删除。validation/.gitkeep 只用于建立输出目录。历史验证脚本可能引用未随仓库上传的旧快照；需要回退冻结运行版本时，先取得维护者的完整恢复包。

`prepare_project.py`、`prepare_camera_stage2.py`、`connect_camera_stage2.py`、`port_sensor_firmware.py` 是早期移植脚本，会依赖未上传的原始工程并覆盖文件，不是新克隆的初始化命令。不要为构建当前源码重跑这些脚本。

`run_sensors.py`、`restore_sensor_run.py` 会访问硬件，须先确认匹配版本及设备；本次仓库初始化不调用。仅关闭串口采集不会停止板上程序。
