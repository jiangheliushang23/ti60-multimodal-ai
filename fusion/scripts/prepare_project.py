"""Create isolated fusion sources once; never build or access hardware."""
from pathlib import Path
import copy, hashlib, json, shutil, xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]
FUSION=ROOT/'fusion'
HW=FUSION/'ti60_multimodal'
SW=FUSION/'demo_multimodal'
NAME='Ti60_Multimodal'
assert not HW.exists() and not SW.exists(), 'Refuse to replace an existing fusion project'
skip={'outflow','work_syn','work_pnr','build','.git','__pycache__','validation'}
photos={'images.hex','pdti8_hdmi.v','pdti8_page.v','pdti8_regs.v',
        'person_image_data.cc','person_image_data.h','no_person_image_data.cc','no_person_image_data.h',
        'people1_data.h','people2_data.h','no_people1_data.h','no_people2_data.h','ref_pdti8_detection_scores.txt'}
manifest=[]
def clone_tree(source,target):
    for src in source.rglob('*'):
        rel=src.relative_to(source)
        if not src.is_file() or any(p in skip for p in rel.parts) or src.name in photos: continue
        if src.suffix in {'.log','.asm'}: continue
        dst=target/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
        manifest.append({'source':src.relative_to(ROOT).as_posix(),'destination':dst.relative_to(FUSION).as_posix(),
                         'sha256':hashlib.sha256(src.read_bytes()).hexdigest()})
base=ROOT/'task2_ai/soc_hdmi'
for directory in ['src','ip','sdc']:clone_tree(base/directory,HW/directory)
shutil.copy2(base/'debug_top.v',HW/'debug_top.v')
clone_tree(ROOT/'task2_ai/demo_pdti8_hdmi/bsp',SW/'bsp')
clone_tree(ROOT/'task2_ai/demo_pdti8_hdmi/software',SW/'software')
sensor=ROOT/'sensors/ir_thermal_hdmi_v3_20260930'
for filename in ['sht30_reader.v','sht30_bus.v','sht30_values.v','mlx90640_bus.v','thermal_page.v']:
    dst=HW/'src/sensors'/filename;dst.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(sensor/'rtl'/filename,dst)
    manifest.append({'source':(sensor/'rtl'/filename).relative_to(ROOT).as_posix(),
                     'destination':dst.relative_to(FUSION).as_posix(),'sha256':hashlib.sha256(dst.read_bytes()).hexdigest()})
page=HW/'src/sensors/thermal_page.v'
page.write_text(page.read_text().replace('FPGA THERMAL IMAGER                     ',
                                      'MULTIMODAL - SENSOR BRINGUP             '),encoding='utf-8')
firmware=SW/'software/standalone/tinyml_pdti8/src'
for filename in ['MLX90640_API.cpp','MLX90640_API.h','MLX90640_I2C_Driver.h','thermal_display.h']:
    shutil.copy2(sensor/'firmware'/filename,firmware/filename)
link=SW/'bsp/efinix/EfxSapphireSoc/linker/default.ld'
link.write_text(link.read_text().replace('LENGTH = 128M','LENGTH = 0x03FFF000'),encoding='utf-8')
ns='http://www.efinixinc.com/enf_proj';ET.register_namespace('efx',ns)
project=ET.parse(base/'Ti60F225_tinyml_helloworld.xml');pr=project.getroot();pr.set('name',NAME)
design=pr.find('{'+ns+'}design_info')
for item in list(design):
    if item.tag.endswith('design_file') and Path(item.get('name','')).name in photos:design.remove(item)
for rel in ['src/sensors/sht30_reader.v','src/sensors/sht30_bus.v','src/sensors/sht30_values.v',
            'src/sensors/mlx90640_bus.v','src/sensors/thermal_page.v','src/fusion/fusion_apb.v',
            'src/fusion/fusion_sht_cdc.v','src/fusion/fusion_sensor_hdmi.v']:
    node=ET.Element('{'+ns+'}design_file',name=rel,version='default',library='default')
    design.insert(list(design).index(design.find('{'+ns+'}top_vhdl_arch')),node)
project.write(HW/(NAME+'.xml'),encoding='utf-8',xml_declaration=True)
pn='http://www.efinixinc.com/peri_design_db';ET.register_namespace('efxpt',pn)
peri=ET.parse(base/'Ti60F225_tinyml_helloworld.peri.xml');peri.getroot().set('name',NAME)
old=ET.parse(sensor/'IR_Thermal_HDMI.peri.xml')
gpio_info=peri.getroot().find('.//{'+pn+'}gpio_info')
copied_gpio=0
for e in old.getroot().iter('{'+pn+'}comp_gpio'):
    if e.get('name') in {'sht_scl','sht_sda','ir_scl','ir_sda'}:
        marker=next(i for i,n in enumerate(gpio_info) if n.tag.endswith('global_unused_config'))
        gpio_info.insert(marker,copy.deepcopy(e));copied_gpio+=1
assert copied_gpio==4
peri.write(HW/(NAME+'.peri.xml'),encoding='utf-8',xml_declaration=True)
top=HW/'src/tinyml_soc_top.v';text=top.read_text()
text=text.replace('   input hdmi_tx_slow_clk, hdmi_tx_locked,','''   input hdmi_tx_slow_clk, hdmi_tx_locked,
   input sht_scl_IN,sht_sda_IN,ir_scl_IN,ir_sda_IN,
   output sht_scl_OUT,sht_scl_OE,sht_sda_OUT,sht_sda_OE,
   output ir_scl_OUT,ir_scl_OE,ir_sda_OUT,ir_sda_OE,''')
text=text.replace('pdti8_hdmi u_pdti8_hdmi(','''fusion_sensor_hdmi u_fusion_sensor_hdmi(
 .sht_scl_IN(sht_scl_IN),.sht_sda_IN(sht_sda_IN),
 .sht_scl_OUT(sht_scl_OUT),.sht_scl_OE(sht_scl_OE),.sht_sda_OUT(sht_sda_OUT),.sht_sda_OE(sht_sda_OE),
 .ir_scl_IN(ir_scl_IN),.ir_sda_IN(ir_sda_IN),
 .ir_scl_OUT(ir_scl_OUT),.ir_scl_OE(ir_scl_OE),.ir_sda_OUT(ir_sda_OUT),.ir_sda_OE(ir_sda_OE),''')
text=text.replace('tinyml_top#(','''// Reserved video master: deterministic idle until the camera AXI adapter is integrated.
assign axi_inter_s1_awaddr=0;assign axi_inter_s1_awlen=0;assign axi_inter_s1_awvalid=0;
assign axi_inter_s1_wdata=0;assign axi_inter_s1_wstrb=0;assign axi_inter_s1_wlast=0;assign axi_inter_s1_wvalid=0;
assign axi_inter_s1_bready=1;assign axi_inter_s1_araddr=0;assign axi_inter_s1_arlen=0;assign axi_inter_s1_arvalid=0;
assign axi_inter_s1_rready=1;
tinyml_top#(''')
assert 'pdti8_hdmi' not in text and 'sht_scl_IN' in text
top.write_text(text,encoding='utf-8')
(HW/'validation').mkdir();(HW/'src/fusion').mkdir();(FUSION/'tests').mkdir()
runner=(ROOT/'task2_ai/scripts/run_soc_hdmi.ps1').read_text().replace("'soc_hdmi'","'ti60_multimodal'").replace("'hdmi_20261002'","'ti60_multimodal/validation'").replace("'Ti60F225_tinyml_helloworld'",repr(NAME))
(FUSION/'scripts/build_hardware.ps1').write_text(runner,encoding='utf-8')
constraints=(ROOT/'task2_ai/scripts/refresh_soc_hdmi_constraints.py').read_text().replace("'soc_hdmi'","'ti60_multimodal'").replace("'Ti60F225_tinyml_helloworld'",repr(NAME))
constraints += '\nwith (project / "sdc/ddr3.sdc").open("a",encoding="utf-8") as f:\n    for signal in ("sht_scl_IN","sht_sda_IN","ir_scl_IN","ir_sda_IN"):\n        f.write("set_false_path -from [get_ports {"+signal+"}]\\n")\n'
(FUSION/'scripts/refresh_constraints.py').write_text(constraints,encoding='utf-8')
buildsw=(ROOT/'task2_ai/scripts/build_demo_pdti8_hdmi.py').read_text().replace("'demo_pdti8_hdmi'","'demo_multimodal'")
(FUSION/'scripts/build_firmware.py').write_text(buildsw,encoding='utf-8')
(HW/'validation/source_origins.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print(json.dumps({'hardware':str(HW),'software':str(SW),'copied_files':len(manifest),'hardware_access':False}))
