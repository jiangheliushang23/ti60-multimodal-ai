"""Run camera regressions and simultaneous sensor/overlay tests, without hardware."""
from pathlib import Path
import hashlib,json,re,subprocess
ROOT=Path(__file__).resolve().parents[3]
PROJECT=ROOT/'fusion/ti60_yolo_auto'
OUT=PROJECT/'validation/multimodal_live'
TESTS=ROOT/'fusion/tests'
SIM=Path('D:/modelsim/modelsim_ase/win32aloem')

def main():
 OUT.mkdir(parents=True,exist_ok=True)
 report=dict(complete=False,passed=False,board_accessed=False,tests={},inputs_sha256={})
 report['inputs_sha256'][Path(__file__).relative_to(ROOT).as_posix()]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
 save=lambda:(OUT/'rtl_result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
 save()
 # Reuse the current ownership/CDC tests, applying them to the changed FIFO depth.
 tb=(PROJECT/'validation/camera_live/camera_live_ddr_tb.v').read_text()
 (OUT/'multimodal_ddr_tb.v').write_text(tb)
 tb=(TESTS/'camera_live_hdmi_tb.v').read_text().replace('59434d32','59415531')
 extra=r'''
  release dut.h;release dut.v;
  repeat(6)@(posedge cpu_clk);
  // Independent thermal and YOLO mailboxes may both be pending until blank.
  put(16'h6000,128);put(16'h1020,1);put(16'h1024,32'h00002500);
  put(16'h1028,32'h00003600);put(16'h102c,32'h00003300);put(16'h1018,1);
  address=16'h1004;#1;if(!read_data[0])$fatal(1,"thermal commit not busy");
  put(16'h1080,32'h0050);put(16'h1084,32'h0175);put(16'h1088,32'h0095);
  put(16'h1078,74);put(16'h1060,3);put(16'h106c,1);
  // Busy sensor RAM rejects writes, without blocking the independent AI mailbox.
  @(negedge cpu_clk);address=16'h6000;select=1;enable=1;write=1;#1;
  if(!error)$fatal(1,"busy heatmap writes were accepted");
  @(negedge cpu_clk);select=0;enable=0;write=0;
  repeat(10)@(posedge pixel_clk);
  if(dut.panel.record_frame[31:0]!==0)$fatal(1,"thermal metadata changed before blank");
  blank();repeat(6)@(posedge cpu_clk);
  address=16'h1004;#1;if(read_data[0])$fatal(1,"thermal ACK missing");
  address=16'h107c;#1;if(read_data!==74)$fatal(1,"AI ACK lost to sensor commit");
  if(dut.panel.record_frame[95:0]!=={32'h3600,32'h2500,32'd1})$fatal(1,"thermal metadata torn");
  if(dut.metrics_shown!=={32'h0095,32'h0175,32'h0050})$fatal(1,"display metrics torn");
  force dut.h=1360;force dut.v=192;
  repeat(6)@(posedge pixel_clk);#1;
  if(dut.rgb!==24'h00ff00)$fatal(1,"thermal pixel pipeline/alignment wrong");
  release dut.h;release dut.v;
  // Updating the non-displayed thermal bank cannot disturb the shown heatmap.
  put(16'h6000,255);
  force dut.h=1360;force dut.v=192;repeat(6)@(posedge pixel_clk);#1;
  if(dut.rgb!==24'h00ff00)$fatal(1,"heatmap changed before atomic swap");
  release dut.h;release dut.v;
  put(16'h1018,1);repeat(10)@(posedge pixel_clk);blank();repeat(6)@(posedge cpu_clk);
  force dut.h=1360;force dut.v=192;repeat(6)@(posedge pixel_clk);#1;
  if(dut.rgb!==24'hff0300)$fatal(1,"second thermal bank not displayed");
  force dut.panel.ir_age=300;#1;
  if(dut.panel.ir_ok)$fatal(1,"stale thermal map still valid");
  if(dut.panel.rgb!==24'h142237)$fatal(1,"stale thermal map not blanked");
  release dut.panel.ir_age;release dut.h;release dut.v;
  // CPU SHT snapshot comes from the unchanged cross-clock handshake.
  force dut.sht_snapshot={3'd1,1'b0,20'h02500,20'h05000,16'h6666,16'h7777};
  force dut.sht_sample=1;
  @(posedge cpu_clk);#1;release dut.sht_sample;release dut.sht_snapshot;
  address=16'h2000;#1;if(read_data!==1)$fatal(1,"SHT status missing");
  address=16'h2008;#1;if(read_data!==32'h2500)$fatal(1,"SHT temperature packing");
  address=16'h2010;#1;if(read_data!==32'h5000)$fatal(1,"SHT humidity packing");
  force dut.ready=1;force dut.result=1;force dut.negative=0;
  force dut.t_bcd=20'h02500;force dut.h_bcd=20'h05000;
  @(posedge pixel_clk);#1;release dut.ready;release dut.result;release dut.negative;release dut.t_bcd;release dut.h_bcd;
  blank();#1;
  if(dut.panel.frame_status!==1||dut.panel.frame_t!==20'h02500||dut.panel.frame_h!==20'h05000)$fatal(1,"environment footer update");
  force dut.h=1360;force dut.v=800;#1;
  if(dut.panel.text_line[319-:11*8]!=="CONFIDENCE ")$fatal(1,"panel text left alignment");
  release dut.h;release dut.v;
'''
 tb=tb.replace('  $display("PASS YOLO HDMI:',extra+'\n  $display("PASS multimodal HDMI:')
 (OUT/'multimodal_hdmi_tb.v').write_text(tb)
 tb=(TESTS/'camera_line_bridge_tb.v').read_text()
 tb=tb.replace('camera_line_bridge_tb','multimodal_full_width_tb').replace('WIDTH(96)','WIDTH(1920)').replace("16'd120","16'd2400")
 tb=tb.replace('16+x+y*3','16+(x%120)+(y%40)').replace('n%48','n%960').replace('n/48','n/960').replace('23:24','479:480').replace('n!=288','n!=5760')
 tb=tb.replace('vs=0;repeat(100)','vs=0;repeat(1000)').replace('#1000000;','#5000000;')
 tb=tb.replace('run_clk=1;repeat(1000)','run_clk=1;repeat(5000)')
 (OUT/'full_width_tb.v').write_text(tb)
 sensor=[PROJECT/'src'/p for p in ('fusion/fusion_apb.v','fusion/fusion_sht_cdc.v','fusion/multimodal_panel.v',
  'sensors/sht30_reader.v','sensors/sht30_bus.v','sensors/sht30_values.v','sensors/mlx90640_bus.v','hdmi/sht30_font.v')]
 groups={
  'lease':('camera_live_lease_tb',[TESTS/'camera_live_lease_tb.v',PROJECT/'src/fusion/video_frame_lease.v']),
  'retry':('camera_live_retry_tb',[TESTS/'camera_live_retry_tb.v',PROJECT/'src/fusion/camera_setup_retry.v']),
  'hdmi':('camera_live_hdmi_tb',[OUT/'multimodal_hdmi_tb.v',PROJECT/'src/fusion/fusion_sensor_hdmi.v',PROJECT/'src/hdmi/dvi_encoder.v',PROJECT/'src/hdmi/encode.v',*sensor]),
  'ddr':('camera_live_ddr_tb',[OUT/'multimodal_ddr_tb.v',PROJECT/'src/fusion/video_ddr.v',PROJECT/'src/camera/frame_buffer_V4/DC_FIFO.v']),
  'ordering':('axi_read_after_write_guard_tb',[TESTS/'axi_read_after_write_guard_tb.v',PROJECT/'src/fusion/axi_read_after_write_guard.v']),
  'sensor_apb':('fusion_apb_tb',[TESTS/'fusion_apb_tb.v',PROJECT/'src/fusion/fusion_apb.v',PROJECT/'src/sensors/mlx90640_bus.v']),
  'ir_full_burst':('multimodal_ir_bus_tb',[TESTS/'multimodal_ir_bus_tb.v',PROJECT/'src/sensors/mlx90640_bus.v']),
  'sensor_cdc':('fusion_sht_cdc_tb',[TESTS/'fusion_sht_cdc_tb.v',PROJECT/'src/fusion/fusion_sht_cdc.v']),
  'sht_values':('multimodal_sht_values_tb',[TESTS/'multimodal_sht_values_tb.v',PROJECT/'src/sensors/sht30_values.v']),
  'line_bridge':('camera_line_bridge_tb',[TESTS/'camera_line_bridge_tb.v',PROJECT/'src/fusion/camera_line_bridge.v',PROJECT/'src/camera/frame_buffer_V4/DC_FIFO.v']),
  'full_width':('multimodal_full_width_tb',[OUT/'full_width_tb.v',PROJECT/'src/fusion/camera_line_bridge.v',PROJECT/'src/camera/frame_buffer_V4/DC_FIFO.v']),
 }
 for path in (TESTS/'fixtures/thermal').glob('*'):
  if path.is_file():report['inputs_sha256'][path.relative_to(ROOT).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
 if not (OUT/'work').exists():subprocess.run([str(SIM/'vlib.exe'),'work'],cwd=OUT,check=True,capture_output=True)
 for label,(top,files) in groups.items():
  for path in files:report['inputs_sha256'][path.relative_to(ROOT).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
  for stage,command in (
   ('compile',[str(SIM/'vlog.exe'),'-sv','+incdir+'+str(ROOT/'fusion/tests/yolo_auto/fixtures/thermal'),'-work','work',*map(str,files)]),
   ('sim',[str(SIM/'vsim.exe'),'-c','-quiet','-lib','work',top,'-do','run -all; quit -f'])):
   log=OUT/f'{label}_{stage}.log'
   with log.open('wb') as stream:r=subprocess.run(command,cwd=OUT,stdout=stream,stderr=subprocess.STDOUT,timeout=180)
   text=log.read_text(errors='replace')
   if r.returncode or '** Error:' in text or '** Fatal:' in text or re.search(r'Errors:\s*[1-9]',text) or (stage=='sim' and 'PASS ' not in text):
    raise RuntimeError(f'{label} {stage} failed: {log}\n{text[-2500:]}')
  report['tests'][label]=dict(passed=True,log=str(log.relative_to(ROOT)));save();print('PASS',label,flush=True)
 report.update(complete=True,passed=True);save();print(OUT/'rtl_result.json')

if __name__=='__main__':main()
