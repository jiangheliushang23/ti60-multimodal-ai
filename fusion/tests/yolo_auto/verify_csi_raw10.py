"""Verify the sole CSI change is unused-format pruning, and compare RAW10 paths."""
from pathlib import Path
import hashlib,json,re,subprocess
ROOT=Path(__file__).resolve().parents[3];HW=ROOT/'fusion/ti60_yolo_auto'
OUT=HW/'validation/dual_behavior/csi_raw10';SIM=Path('D:/modelsim/modelsim_ase/win32aloem')
IP=Path('D:/efinity_merged/2026.1/ipm/ip/efx_csi2_2p5g')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def main():
 OUT.mkdir(parents=True,exist_ok=True)
 wrapper=HW/'ip/csi_rx_controller/csi_rx_controller.sv';settings=wrapper.with_name('settings.json')
 baseline=json.loads((OUT.parent/'baseline.json').read_text(encoding='utf8'))
 saved=Path(baseline['backup'])/'before'
 release_path=saved/'fusion/ti60_yolo_auto/yolo_auto_release.json'
 release=json.loads(release_path.read_text(encoding='utf8'))
 old_wrapper=OUT/'csi_rx_controller_before.sv';old_settings=OUT/'settings_before.json'
 assert sha(old_wrapper)==release['inputs_sha256'][wrapper.relative_to(ROOT).as_posix()]
 assert sha(old_settings)==release['inputs_sha256'][settings.relative_to(ROOT).as_posix()]
 assert wrapper.read_text()==old_wrapper.read_text().replace('.PACK_TYPE (15)','.PACK_TYPE (1)',1),'Unexpected CSI source edit'
 original=json.loads(old_settings.read_text());expected=json.loads(old_settings.read_text())
 for key in ('Pack_48','Pack_56','Pack_64'):expected['conf'][key]="1'b0"
 assert original['conf']['Pack_40']=="1'b1" and json.loads(settings.read_text())==expected
 camera=HW/'src/fusion/fusion_camera.v'
 assert sha(camera)==baseline['sha256'][camera.relative_to(ROOT).as_posix()]
 assert '.raw({w_mipi_rx_data[39:32],w_mipi_rx_data[29:22],w_mipi_rx_data[19:12],w_mipi_rx_data[9:2]})' in re.sub(r'\s+','',camera.read_text())
 component=(IP/'efx_csi2_rx/ipm/ip_component.xml').read_text()
 assert '4’b0001: Pack 40' in component and 'Pack 40 RAW10' in component
 assert 'Only enable the pack type that you are using to save logic resources.' in component
 # Simulation uses the vendor's v5.15 receiver/depacker with the project's
 # compatible ModelSim FIFO/reset implementation, never stubbed pixel logic.
 common=HW/'ip/csi_rx_controller/Testbench/modelsim/csi_rx_controller.sv'
 text=common.read_text();text=text[text.index('module `IP_MODULE_NAME(efx_asyncreg)'):]
 (OUT/'common.v').write_text(text)
 (OUT/'names.vh').write_text('`define IP_MODULE_NAME(name) name\n')
 def run(args,label,passed=False):
  p=subprocess.run([str(SIM/args[0]),*map(str,args[1:])],cwd=OUT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120)
  t=p.stdout.decode(errors='replace');(OUT/(label+'.log')).write_text(t)
  assert p.returncode==0 and '** Error:' not in t and '** Fatal:' not in t and not re.search(r'Errors:\s*[1-9]',t),label+' '+t[-1800:]
  if passed:assert 'PASS RAW10 Pack15 vs Pack1 pixels=15360' in t,label
 sources=[IP/'source_modelsim'/n for n in ('efx_csi2_byte2pixel.sv','efx_csi2_depack40bit.sv','efx_csi2_depack48bit.sv','efx_csi2_depack56bit.sv','efx_csi2_depack64bit.sv')]
 tb=Path(__file__).with_name('csi_raw10_equivalence_tb.sv')
 if not (OUT/'work').exists():run(['vlib.exe','work'],'vlib')
 run(['vlog.exe','-sv','-mfcu','names.vh','common.v','names.vh',*sources,tb],'compile')
 run(['vsim.exe','-c','-quiet','csi_raw10_equivalence_tb','-do','run -all; quit -f'],'equivalence',True)
 paths=[Path(__file__),tb,wrapper,settings,camera,common,OUT.parent/'baseline.json',release_path,old_wrapper,old_settings]
 r=dict(complete=True,passed=True,board_accessed=False,raw10_equivalent=True,compared_pixels=15360,
        only_pack_type_changed=True,original_pack_type=15,pack_type=1,removed_formats=['Pack48','Pack56','Pack64'],
        raw10_camera_source_unchanged=True,accelerator_unchanged=True,
        vendor_source_sha256={str(p):sha(p) for p in [*sources,IP/'efx_csi2_rx/ipm/ip_component.xml']},
        inputs_sha256={p.relative_to(ROOT).as_posix():sha(p) for p in paths})
 (OUT/'result.json').write_text(json.dumps(r,indent=2),encoding='utf8');print(OUT/'result.json')
if __name__=='__main__':main()
