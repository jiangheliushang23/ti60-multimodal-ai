"""Run all linked-firmware ISA cases; never access a board."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import subprocess,sys
CASES = ['normal','cold','hot','timer_wrap','steady','nack','transient_nack','overrun',
 'bus_timeout','no_new_data','bad_eeprom','bad_math','wrong_id','delayed_bus',
 'delayed_display','display_timeout','recover_nack','recover_timeout','recover_no_data']
def run(case):
 r=subprocess.run([sys.executable,'-B',str(Path(__file__).with_name('firmware_emulator.py')),case],
                  capture_output=True,text=True,encoding='utf-8',timeout=120)
 return case,r
if __name__=='__main__':
 failed=[]
 with ThreadPoolExecutor(max_workers=4) as pool:
  for case,r in pool.map(run,CASES):
   print(('PASS ' if r.returncode==0 else 'FAIL ')+case,flush=True)
   if r.returncode:
    failed.append(case);print(r.stdout+r.stderr,flush=True)
 raise SystemExit(1 if failed else 0)
