"""Offline tests bind the candidate hardware and tests to their exact hashes."""
from pathlib import Path
import subprocess,json,hashlib,time,sys,os,shutil
REPO=Path(__file__).resolve().parents[3];ROOT=REPO/'fusion'
P=ROOT/'ti60_multimodal';S=P/'src';T=Path(__file__).resolve().parent;V=P/'validation';V.mkdir(parents=True,exist_ok=True)
IV=Path(os.environ.get('IVERILOG') or shutil.which('iverilog') or str(REPO/'tools/iverilog/bin/iverilog.exe'));VVP=Path(os.environ.get('VVP') or shutil.which('vvp') or str(IV.with_name('vvp.exe')))
REF=T/'reference'
F=REPO/'fusion/tests';L=REPO/'sensors/ir_thermal_hdmi_v3_20260930/tests'
cases={
 'compact_stats_tb':([T/'compact_stats_tb.v',S/'fusion/camera_auto_stats.v',REF/'rtl/sc431hai/sc_auto_stats.v'],[[]]),
 'auto_apb_tb':([T/'auto_apb_tb.v',S/'fusion/camera_auto_apb.v'],[[]]),
 'camera_line_bridge_tb':([F/'camera_line_bridge_tb.v',S/'fusion/camera_line_bridge.v',S/'fusion/camera_auto_stats.v',S/'camera/frame_buffer_V4/DC_FIFO.v'],[[]]),
 'stream_check_tb':([REF/'sim/setup_tb.v',S/'camera/sc431hai/sc431hai_setup.v',S/'camera/sc431hai/i2c_reg16.v'],[[f'+CASE={i}'] for i in range(17)]),
 'debayer_tb':([F/'debayer_tb.v',*[S/'camera/debayer'/n for n in ('debayer_top_2to1.v','raw_to_rgb.v','line_buffer.v','rgb_gain_v1.v','true_dual_port_ram.v','camera_line_ram.v')]], [[],[]]),
 'camera_rgb_pack_tb':([F/'camera_rgb_pack_tb.v',S/'fusion/camera_rgb_pack.v'],[[]]),
 'video_ddr_tb':([F/'video_ddr_tb.v',S/'fusion/video_ddr.v',S/'camera/frame_buffer_V4/DC_FIFO.v'],[[]]),
 'fusion_page_tb':([F/'fusion_page_tb.v',S/'fusion/fusion_page.v',S/'hdmi/sht30_font.v'],[[]]),
 'fusion_sht_cdc_tb':([F/'fusion_sht_cdc_tb.v',S/'fusion/fusion_sht_cdc.v'],[[]]),
 'fusion_apb_tb':([F/'fusion_apb_tb.v',S/'fusion/fusion_apb.v',S/'sensors/mlx90640_bus.v'],[[]]),
 'thermal_page_tb':([L/'thermal_page_tb.v',S/'sensors/thermal_page.v',S/'hdmi/sht30_font.v'],[[]]),
}
report=V/'tests.json'
selected=set(sys.argv[1:])
results=[] if not selected else [r for r in json.loads(report.read_text()) if r['top'] not in selected]
for top,(files,runs) in cases.items():
 if selected and top not in selected:continue
 for number,args in enumerate(runs):
  start=time.monotonic();out=V/(top+'.vvp')
  command=[str(IV),'-g2012','-I',str(S/'camera/sc431hai'),'-I',str(L),'-s',top,'-o',str(out)]
  if top=='debayer_tb':command.append(f'-Pdebayer_tb.GAIN_CASE={number}')
  c=subprocess.run(command+list(map(str,files)),cwd=P,capture_output=True,text=True)
  log=c.stdout+c.stderr
  if c.returncode==0:
   c=subprocess.run([str(VVP),str(out),*args],cwd=P,capture_output=True,text=True,timeout=300);log+=c.stdout+c.stderr
  passed=c.returncode==0 and 'PASS' in log
  (V/f'{top}_{number}.log').write_text(log,encoding='utf-8')
  results.append(dict(top=top,args=args,passed=passed,seconds=time.monotonic()-start,sources={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in files}))
  (V/'tests.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
  print(log.strip(),flush=True)
  if not passed:raise SystemExit(1)
