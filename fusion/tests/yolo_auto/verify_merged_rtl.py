"""Regress the shipped YOLO/AE/AWB/sensor RTL, without touching the board."""
from pathlib import Path
import hashlib,json,re,subprocess
ROOT=Path(__file__).resolve().parents[3]
P=ROOT/'fusion/ti60_yolo_auto'; S=P/'src'; T=Path(__file__).resolve().parent
A=ROOT/'fusion/tests/camera_auto'; F=ROOT/'fusion/tests'
OUT=P/'validation/yolo_auto_rtl'; SIM=Path('D:/modelsim/modelsim_ase/win32aloem')

def main():
 OUT.mkdir(parents=True,exist_ok=True)
 sensor=[S/p for p in ('fusion/fusion_apb.v','fusion/fusion_sht_cdc.v','fusion/multimodal_panel.v',
  'sensors/sht30_reader.v','sensors/sht30_bus.v','sensors/sht30_values.v','sensors/mlx90640_bus.v','hdmi/sht30_font.v')]
 bridge=[S/'fusion/camera_line_bridge.v',S/'fusion/camera_auto_stats.v',S/'camera/frame_buffer_V4/DC_FIFO.v']
 groups={
 'lease':('camera_live_lease_tb',[T/'camera_live_lease_tb.v',S/'fusion/video_frame_lease.v'],[[]]),
 'retry':('camera_live_retry_tb',[T/'camera_live_retry_tb.v',S/'fusion/camera_setup_retry.v'],[[]]),
 'hdmi':('camera_live_hdmi_tb',[T/'multimodal_hdmi_tb.v',S/'fusion/fusion_sensor_hdmi.v',S/'fusion/snapshot_cdc.v',S/'hdmi/dvi_encoder.v',S/'hdmi/encode.v',*sensor],[[]]),
 'dual_hdmi':('dual_person_hdmi_tb',[T/'dual_person_hdmi_tb.v',S/'fusion/fusion_sensor_hdmi.v',S/'fusion/snapshot_cdc.v',S/'hdmi/dvi_encoder.v',S/'hdmi/encode.v',*sensor],[[]]),
 'thermal_bilinear':('thermal_bilinear_tb',[T/'thermal_bilinear_tb.v',S/'fusion/multimodal_panel.v',S/'hdmi/sht30_font.v'],[[]]),
 'panel_text_equivalence':('panel_text_equivalence_tb',[T/'panel_text_equivalence_tb.v',T/'fixtures/panel_text/multimodal_panel_reference.v',S/'fusion/multimodal_panel.v',S/'hdmi/sht30_font.v'],[[]]),
 'ddr':('camera_live_ddr_tb',[T/'multimodal_ddr_tb.v',S/'fusion/video_ddr.v',S/'camera/frame_buffer_V4/DC_FIFO.v'],[[]]),
 'ordering':('axi_read_after_write_guard_tb',[T/'axi_read_after_write_guard_tb.v',S/'fusion/axi_read_after_write_guard.v'],[[]]),
 'sensor_apb':('fusion_apb_tb',[T/'fusion_apb_tb.v',S/'fusion/fusion_apb.v',S/'sensors/mlx90640_bus.v'],[[]]),
 'ir_burst':('multimodal_ir_bus_tb',[T/'multimodal_ir_bus_tb.v',S/'sensors/mlx90640_bus.v'],[[]]),
 'sensor_cdc':('fusion_sht_cdc_tb',[T/'fusion_sht_cdc_tb.v',S/'fusion/fusion_sht_cdc.v'],[[]]),
 'sht_values':('multimodal_sht_values_tb',[T/'multimodal_sht_values_tb.v',S/'sensors/sht30_values.v'],[[]]),
 'line_bridge':('camera_line_bridge_tb',[T/'camera_line_bridge_tb.v',*bridge],[[]]),
 'full_width':('multimodal_full_width_tb',[T/'full_width_tb.v',*bridge],[[]]),
 'auto_apb':('auto_apb_tb',[A/'auto_apb_tb.v',S/'fusion/camera_auto_apb.v'],[[]]),
 'auto_stats':('compact_stats_tb',[A/'compact_stats_tb.v',S/'fusion/camera_auto_stats.v',A/'reference/rtl/sc431hai/sc_auto_stats.v'],[[]]),
 'setup':('stream_check_tb',[A/'reference/sim/setup_tb.v',S/'camera/sc431hai/sc431hai_setup.v',S/'camera/sc431hai/i2c_reg16.v'],[[f'+CASE={i}'] for i in range(17)]),
 'debayer':('debayer_tb',[F/'debayer_tb.v',*[S/'camera/debayer'/p for p in ('debayer_top_2to1.v','raw_to_rgb.v','line_buffer.v','rgb_gain_v1.v','true_dual_port_ram.v','camera_line_ram.v')]], [['-gGAIN_CASE=0'],['-gGAIN_CASE=1']]),
 'rgb_pack':('camera_rgb_pack_tb',[F/'camera_rgb_pack_tb.v',S/'fusion/camera_rgb_pack.v'],[[]]),
 }
 report=dict(complete=False,passed=False,board_accessed=False,tests={},inputs_sha256={})
 save=lambda:(OUT/'rtl_result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
 save()
 def run(command,label,simulation=False):
  log=OUT/(label+'.log')
  with log.open('wb') as stream:r=subprocess.run(list(map(str,command)),cwd=OUT,stdout=stream,stderr=subprocess.STDOUT,timeout=240)
  text=log.read_text(errors='replace')
  if r.returncode or '** Error:' in text or '** Fatal:' in text or re.search(r'Errors:\s*[1-9]',text) or (simulation and 'PASS' not in text):
   raise RuntimeError(f'{label}: {log}\n{text[-3500:]}')
  return str(log.relative_to(ROOT))
 if not (OUT/'work').exists():run([SIM/'vlib.exe','work'],'vlib')
 if 'EFX_DSP48' in (S/'fusion/multimodal_panel.v').read_text():
  vendor=Path('D:/efinity_merged/2026.1/sim_models/verilog/efx_dsp48.v')
  run([SIM/'vlog.exe','-sv','-timescale','1ns/1ps','-work','work',vendor],'vendor_dsp_compile')
  report['vendor_models_sha256']={str(vendor):hashlib.sha256(vendor.read_bytes()).hexdigest()}
 for label,(top,files,runs) in groups.items():
  for path in files:report['inputs_sha256'][path.relative_to(ROOT).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
  run([SIM/'vlog.exe','-sv','+incdir+'+str(T/'fixtures/thermal'),'+incdir+'+str(S/'camera/sc431hai'),'-work','work',*files],label+'_compile')
  for i,args in enumerate(runs):
   log=run([SIM/'vsim.exe','-c','-quiet','-lib','work',top,*args,'-do','run -all; quit -f'],label+f'_{i}',True)
   report['tests'][label+f'_{i}']=dict(passed=True,log=log);save();print('PASS',label,i,flush=True)
 for path in (Path(__file__),S/'camera/sc431hai/sc_sequence.vh',*list((T/'fixtures/thermal').glob('*'))):
  if path.is_file():report['inputs_sha256'][path.relative_to(ROOT).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
 report.update(complete=True,passed=True);save();print(OUT/'rtl_result.json')

if __name__=='__main__':main()
