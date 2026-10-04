"""Import only the verified SC431HAI receiver/ISP; never touches the source baseline."""
from pathlib import Path
import shutil, copy, json, hashlib
import xml.etree.ElementTree as E
root=Path(__file__).resolve().parents[2]
cam=root/'camera/sc431hai_hdmi'; dst=root/'fusion/ti60_multimodal'
origin={}
def cp(a,b):
    b.parent.mkdir(parents=True,exist_ok=True)
    if b.exists():
        assert b.read_bytes()==a.read_bytes(),b
    else:shutil.copy2(a,b)
    origin[str(b.relative_to(root))]={'source':str(a.relative_to(root)),'sha256':hashlib.sha256(a.read_bytes()).hexdigest()}
files=['debayer/debayer_top_2to1.v','debayer/line_buffer.v','debayer/raw_to_rgb.v','debayer/rgb_gain_v1.v','debayer/true_dual_port_ram.v',
       'sc431hai/sc431hai_setup.v','sc431hai/i2c_reg16.v','sc431hai/sc_sequence.vh',
       'gamma_conrrection/gamma_correction.v','gamma_conrrection/linear_to_display_2p2.mem','frame_buffer_V4/DC_FIFO.v','csi_rx_controller.sv']
for f in files:cp(cam/'rtl'/f,dst/'src/camera'/f)
for a in (cam/'ip/csi_rx_controller').rglob('*'):
    if a.is_file():cp(a,dst/'ip/csi_rx_controller'/a.relative_to(cam/'ip/csi_rx_controller'))
ns='http://www.efinixinc.com/enf_proj';E.register_namespace('efx',ns);q=lambda n:'{'+ns+'}'+n
tree=E.parse(dst/'Ti60_Multimodal.xml');r=tree.getroot();di=r.find(q('design_info'))
for f in files:
    if not f.endswith(('.v','.vh')):continue
    name='src/camera/'+f
    if not any(x.get('name')==name for x in di):di.insert(len(di)-1,E.Element(q('design_file'),name=name,version='default',library='default'))
source=E.parse(cam/'ti60f225_oob.xml').getroot()
for ip in source.find(q('ip_info')):
    if ip.get('instance_name')=='csi_rx_controller' and not any(x.get('instance_name')=='csi_rx_controller' for x in r.find(q('ip_info'))):
        r.find(q('ip_info')).append(copy.deepcopy(ip))
# Efinity resolves include dirs relative to the project.
inc=r.find(q('synthesis')).find(q('param')+"[@name='include']")
inc.set('value','ip/sapphire_soc src/camera/sc431hai')
tree.write(dst/'Ti60_Multimodal.xml',encoding='utf-8',xml_declaration=True)
ns='http://www.efinixinc.com/peri_design_db';E.register_namespace('efxpt',ns);q=lambda n:'{'+ns+'}'+n
tree=E.parse(dst/'Ti60_Multimodal.peri.xml');r=tree.getroot();cr=E.parse(cam/'ti60f225_oob.peri.xml').getroot()
gi=r.find(q('gpio_info'))
for x in cr.find(q('gpio_info')):
    if x.tag==q('comp_gpio') and x.get('name') in ['io_cam_scl','io_cam_sda','o_cam_rst_p']:
        if not any(c.get('name')==x.get('name') for c in gi):
            i=next(i for i,c in enumerate(gi) if c.tag!=q('comp_gpio'));gi.insert(i,copy.deepcopy(x))
mi=r.find(q('mipi_dphy_info'))
for x in cr.find(q('mipi_dphy_info')):
    if not any(c.get('name')==x.get('name') for c in mi):mi.append(copy.deepcopy(x))
pi=r.find(q('pll_info'))
if not any(x.get('name')=='pll_camera' for x in pi):
    pll=copy.deepcopy(cr.find(q('pll_info')).find(q('pll')+"[@name='pll_inst4']"))
    pll.set('name','pll_camera');pll.set('pll_def','PLL_BL0');pll.set('ref_clock_name','clk_25m');pll.set('locked_name','camera_pll_locked')
    for x in list(pll):
        if x.tag==q('comp_output_clock') and x.get('name')!='i_mipi_rx_pclk':pll.remove(x)
    pi.append(pll)
tree.write(dst/'Ti60_Multimodal.peri.xml',encoding='utf-8',xml_declaration=True)
(dst/'validation/camera_sources.json').write_text(json.dumps(origin,indent=2),encoding='utf-8')
print('Imported',len(origin),'source/IP files; original baselines unchanged.')
