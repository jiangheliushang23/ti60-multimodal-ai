"""Exercise existing YMM1 RTL: actual green/red RGB border and unchanged video."""
from pathlib import Path
import hashlib,json,subprocess
ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'fusion/ti60_yolo_auto/validation/fall_detection'
SIM=Path('D:/modelsim/modelsim_ase/win32aloem')
def main():
    OUT.mkdir(parents=True,exist_ok=True)
    files=[Path(__file__).with_name('fall_overlay_tb.v')]
    files += [ROOT/'fusion/ti60_yolo_auto/src'/p for p in (
      'fusion/fusion_sensor_hdmi.v','hdmi/dvi_encoder.v','hdmi/encode.v','fusion/fusion_apb.v',
      'fusion/fusion_sht_cdc.v','fusion/multimodal_panel.v','fusion/snapshot_cdc.v','sensors/sht30_reader.v','sensors/sht30_bus.v',
      'sensors/sht30_values.v','sensors/mlx90640_bus.v','hdmi/sht30_font.v')]
    report=dict(complete=False,passed=False,board_accessed=False,inputs_sha256={
      p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),*files]})
    dest=OUT/'overlay_result.json'
    save=lambda:dest.write_text(json.dumps(report,indent=2),encoding='utf-8');save()
    if not (OUT/'work').exists():subprocess.run([str(SIM/'vlib.exe'),'work'],cwd=OUT,capture_output=True,check=True)
    for label,command in [('compile',[str(SIM/'vlog.exe'),'-sv',*map(str,files)]),
      ('simulate',[str(SIM/'vsim.exe'),'-c','-voptargs=+acc','fall_overlay_tb','-do','onerror {quit -code 1}; run -all; quit -f'])]:
        r=subprocess.run(command,cwd=OUT,capture_output=True,text=True,timeout=60)
        output=r.stdout+r.stderr;(OUT/(label+'.log')).write_text(output,encoding='utf-8')
        if r.returncode or '** Fatal' in output or '** Error' in output:raise RuntimeError(output)
    assert 'PASS fall overlay:' in output,output
    report.update(complete=True,passed=True,green_rgb='40ff60',red_rgb='ff4040',fpga_rebuild_required=False)
    save();print('PASS fall overlay RTL green/red, blank-time commit, recovery, no-person clear, stale hide')
    print(dest)
if __name__=='__main__':main()
