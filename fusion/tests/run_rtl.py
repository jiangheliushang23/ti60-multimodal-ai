"""Test changed interfaces and reused sensor/display logic; never accesses hardware."""
from pathlib import Path
import subprocess,json,time,hashlib
root=Path(__file__).resolve().parents[2]
tests=root/'fusion/tests';project=root/'fusion/ti60_multimodal';out=project/'validation'
legacy=root/'sensors/ir_thermal_hdmi_v3_20260930/tests'
rtl=project/'src';iv=root/'tools/iverilog/bin/iverilog.exe';vvp=iv.with_name('vvp.exe')
rate=(legacy/'ir_bus_rate_tb.v').read_text().replace('always #3.367','always #5').replace('148.5 MHz, same clock as the new soft core.','100 MHz fusion APB domain.').replace('.TICK_CYCLES(100),.TIMEOUT_TICKS(15000)','.TICK_CYCLES(100),.TIMEOUT_TICKS(10000)').replace('45000000','65000000').replace('45ms','65ms').replace('#50000000','#70000000')
(tests/'ir_bus_rate_tb.v').write_text(rate)
cases={
 'fusion_sht_cdc_tb':[tests/'fusion_sht_cdc_tb.v',rtl/'fusion/fusion_sht_cdc.v'],
 'fusion_apb_tb':[tests/'fusion_apb_tb.v',rtl/'fusion/fusion_apb.v',rtl/'sensors/mlx90640_bus.v'],
 'ir_bus_rate_tb':[tests/'ir_bus_rate_tb.v',rtl/'sensors/mlx90640_bus.v'],
 'thermal_page_tb':[legacy/'thermal_page_tb.v',rtl/'sensors/thermal_page.v',rtl/'hdmi/sht30_font.v'],
}
results=[]
for name,files in cases.items():
 start=time.time();binary=tests/(name+'.vvp')
 compile_run=subprocess.run([str(iv),'-g2012','-I',str(legacy),'-s',name,'-o',str(binary),*map(str,files)],capture_output=True,text=True)
 log=compile_run.stdout+compile_run.stderr
 if compile_run.returncode==0:
  run=subprocess.run([str(vvp),str(binary)],cwd=project,capture_output=True,text=True,timeout=300)
  log+=run.stdout+run.stderr;code=run.returncode
 else:code=compile_run.returncode
 (out/(name+'.log')).write_text(log)
 results.append(dict(test=name,passed=code==0 and 'PASS ' in log,seconds=round(time.time()-start,2),sources={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}))
 print(log.strip(),flush=True)
 (out/'rtl_tests.json').write_text(json.dumps(results,indent=2))
 if not results[-1]['passed']:raise SystemExit(1)
