"""Wire the minimal receiver to the shared core. Run once on the stage-1 source."""
from pathlib import Path
import re,xml.etree.ElementTree as E
root=Path(__file__).resolve().parents[2];dst=root/'fusion/ti60_multimodal';src=dst/'src'
old=(root/'camera/sc431hai_hdmi/rtl/ti60f225_oob_top.v').read_text()
ports=old[old.index('    input\t wire\t\tio_cam_sda_IN'):old.index('\n\t\r',old.index('    input\t wire\t\tio_cam_sda_IN'))] if False else old[old.index('    input\t wire\t\tio_cam_sda_IN'):old.index('\n\tinput \t\t\t\t\ttx_cal_clk_90edge')]
ports=ports.strip().rstrip(',')
names=re.findall(r'(?:input|output)\s+(?:wire\s+)?(?:\[[^\]]+\]\s*)?(\w+)',ports)
receiver=old[old.index('\t\tcsi_rx_controller inst_efx_csi2_rx'):old.index('//     wire',old.index('\t\tcsi_rx_controller inst_efx_csi2_rx'))]
receiver=receiver.replace('i_arstn','!reset').replace('i_mipi_clk','clk').replace('w_mipi_rx_pclk_arstn','!reset')
wrapper='''// Only the verified CSI receiver and ISP; no second DDR, CPU, HDMI or UART.
module fusion_camera(
 input wire clk,cam_clk,reset,
 output wire sof,output wire [15:0] frame_seq,
 output wire packed_valid,output wire [127:0] packed_data,output wire packed_complete,packed_bad,
 output wire end_valid,output wire [16:0] end_data,
 output wire [127:0] capture_stats,output wire [31:0] setup_status,
 output wire [287:0] diagnostic_words,
'''+ports+''');
 wire i_mipi_rx_pclk=cam_clk;
 wire [63:0] w_mipi_rx_data;
 wire w_mipi_rx_hs,w_mipi_rx_vs,w_mipi_rx_de;
 wire [1:0] csi_vc;wire [5:0] csi_dt;wire [15:0] csi_wc;wire [3:0] csi_ppc;wire csi_irq;
 assign {cam_d0_RST,cam_d1_RST,cam_d2_RST,cam_d3_RST}={4{reset}};
 assign io_cam_scl_OUT=0;assign io_cam_sda_OUT=0;
 wire cam_enable,id_ok,config_ok,stream_set,finished,diagnostic_valid;
 // J4 module reset is active HIGH (same inversion as the verified camera top).
 assign o_cam_rst_p=~cam_enable;
 wire [2:0] error_code;wire [7:0] command_index;
 sc431hai_setup #(.CLK_PER_MS(100000),.I2C_TICK(1000)) setup(
  .clk(clk),.reset(reset),.scl_in(io_cam_scl_IN),.sda_in(io_cam_sda_IN),
  .scl_low(io_cam_scl_OE),.sda_low(io_cam_sda_OE),.cam_enable(cam_enable),
  .id_ok(id_ok),.config_ok(config_ok),.stream_set(stream_set),.finished(finished),
  .error_code(error_code),.command_index(command_index),.diagnostic_words(diagnostic_words),.diagnostic_valid(diagnostic_valid));
 assign setup_status={16'd0,command_index,error_code,finished,stream_set,config_ok,id_ok,cam_enable};
'''+receiver+'''
 wire raw_vs,raw_de;wire [15:0] raw_pair;
 camera_line_bridge line_bridge(.reset(reset),.cam_clk(cam_clk),.clk(clk),.vs(w_mipi_rx_vs),.de(w_mipi_rx_de),
  .raw({w_mipi_rx_data[39:32],w_mipi_rx_data[29:22],w_mipi_rx_data[19:12],w_mipi_rx_data[9:2]}),
  .vc(csi_vc),.dt(csi_dt),.ppc(csi_ppc),.wc(csi_wc),
  .raw_vs(raw_vs),.raw_de(raw_de),.raw_pair(raw_pair),.sof(sof),.sequence_out(frame_seq),
  .end_valid(end_valid),.end_data(end_data),.good_frames(capture_stats[31:0]),.bad_frames(capture_stats[63:32]),
  .period_ticks(capture_stats[95:64]),.overflow_lines(capture_stats[127:96]));
 wire rgb_vs,rgb_de;wire [47:0] rgb_pair,gamma_pair;wire gamma_vs,gamma_de;
 debayer_top_2to1 isp(.in_pclk(clk),.in_rstn(!reset),.raw_vs_i(raw_vs),.raw_hs_i(1'b0),
  .raw_de_i(raw_de),.raw_valid_i(raw_de),.raw_datax4_i(raw_pair),.r_gain(16'd255),.g_gain(16'd255),.b_gain(16'd255),
  .rgb_vs_o(rgb_vs),.rgb_hs_o(),.rgb_de_o(rgb_de),.rgb_valid_o(),.rgb_bout(),.rgb_gout(),.rgb_rout(),.rgb_datax2_o(rgb_pair));
 genvar p;generate for(p=0;p<2;p=p+1)begin:g
  wire gv,gd;
  gamma_correction #(.DATA_WIDTH(8),.GAMMA_CURVE("./src/camera/gamma_conrrection/linear_to_display_2p2.mem")) gamma(
   .i_pclk(clk),.i_rstn(!reset),.i_valid(rgb_de),.i_hs(1'b0),.i_vs(rgb_vs),
   .i_red(rgb_pair[p*24+:8]),.i_green(rgb_pair[p*24+8+:8]),.i_blue(rgb_pair[p*24+16+:8]),
   .o_red(gamma_pair[p*24+:8]),.o_green(gamma_pair[p*24+8+:8]),.o_blue(gamma_pair[p*24+16+:8]),
   .o_valid(gd),.o_hs(),.o_vs(gv));
  if(p==0)begin assign gamma_vs=gv;assign gamma_de=gd;end
 end endgenerate
 camera_rgb_pack pack(.clk(clk),.reset(reset),.vs(gamma_vs),.de(gamma_de),.rgb(gamma_pair),
  .valid(packed_valid),.data(packed_data),.complete(packed_complete),.malformed(packed_bad));
endmodule
'''
(src/'fusion/fusion_camera.v').write_text(wrapper)
# Held-data handshake reused without the old UART/ROI/frame monitor.
mon=(root/'camera/sc431hai_hdmi/rtl/sc431hai/video_monitor.v').read_text()
snap=mon[mon.index('// Source data is captured'):mon.index('module sc_frame_stats')]
(src/'fusion/snapshot_cdc.v').write_text(snap)
top=src/'tinyml_soc_top.v';t=top.read_text();assert 'fusion_camera u_camera' not in t
t=t.replace('   input hdmi_tx_slow_clk',ports+',\n   input i_mipi_rx_pclk,camera_pll_locked,\n   input hdmi_tx_slow_clk',1)
start=t.index('// Reserved video master:');stop=t.index('tinyml_top#(',start)
block='''wire camera_reset=io_systemReset||!camera_pll_locked;
wire video_sof,packed_valid,packed_complete,packed_bad,camera_end;
wire [15:0] video_seq,published_seq;wire [16:0] camera_end_data;
wire [127:0] packed_data,capture_stats;wire [31:0] setup_status;
wire [287:0] diagnostic_words;
wire [31:0] video_published,video_dropped,video_write_errors,video_read_errors,video_underflows;
wire frame_request,video_take,video_valid;wire [2:0] pixel_index;wire [23:0] video_rgb;
fusion_camera u_camera(.clk(io_memoryClk),.cam_clk(i_mipi_rx_pclk),.reset(camera_reset),
 .sof(video_sof),.frame_seq(video_seq),.packed_valid(packed_valid),.packed_data(packed_data),
 .packed_complete(packed_complete),.packed_bad(packed_bad),.end_valid(camera_end),.end_data(camera_end_data),
 .capture_stats(capture_stats),.setup_status(setup_status),.diagnostic_words(diagnostic_words),
'''+',\n'.join(' .'+n+'('+n+')' for n in names)+''');
video_ddr u_video_ddr(.clk(io_memoryClk),.reset(camera_reset),.sof(video_sof),.frame_seq(video_seq),
 .in_valid(packed_valid),.in_data(packed_data),.complete(packed_complete),.malformed(packed_bad),
 .end_valid(camera_end),.end_data(camera_end_data),.pixel_clk(hdmi_tx_slow_clk),.frame_request(frame_request),
 .video_take(video_take),.pixel_index(pixel_index),.video_rgb(video_rgb),.video_valid(video_valid),
 .published(video_published),.published_seq(published_seq),.dropped(video_dropped),
 .write_errors(video_write_errors),.read_errors(video_read_errors),.underflows(video_underflows),
'''
for n in ['awaddr','awlen','awvalid','awready','wdata','wstrb','wlast','wvalid','wready','bresp','bvalid','bready','araddr','arlen','arvalid','arready','rdata','rresp','rlast','rvalid','rready']:
 block+=' .'+n+'(axi_inter_s1_'+n+'),\n'
block=block.rstrip(',\n')+''');
wire [127:0] capture_cpu;wire [511:0] camera_cpu;wire [31:0] underflow_cpu;
reg [16:0] snapshot_divider=0;
always @(posedge i_peripheralClk)if(io_peripheralReset)snapshot_divider<=0;
 else snapshot_divider<=snapshot_divider==99999?0:snapshot_divider+1'b1;
snapshot_cdc #(.WIDTH(128)) cap_status(.src_clk(i_mipi_rx_pclk),.dst_clk(i_peripheralClk),.reset(camera_reset),
 .request(snapshot_divider==0),.src_data(capture_stats),.dst_data(capture_cpu),.done());
snapshot_cdc #(.WIDTH(512)) dma_status(.src_clk(io_memoryClk),.dst_clk(i_peripheralClk),.reset(camera_reset),
 .request(snapshot_divider==0),.src_data({32'd0,diagnostic_words,16'd0,published_seq,video_read_errors,video_write_errors,video_dropped,video_published,setup_status}),
 .dst_data(camera_cpu),.done());
snapshot_cdc #(.WIDTH(32)) pixel_status(.src_clk(hdmi_tx_slow_clk),.dst_clk(i_peripheralClk),.reset(camera_reset),
 .request(snapshot_divider==0),.src_data(video_underflows),.dst_data(underflow_cpu),.done());
wire camera_sel=apb_paddr[15:8]==8'h50;
wire [31:0] sensor_prdata;wire sensor_ready,sensor_error;
reg [31:0] camera_prdata;
always @*begin
 camera_prdata=0;
 case(apb_paddr[7:2])
  0:camera_prdata=32'h43414d32;
  1:camera_prdata=camera_cpu[31:0];
  2:camera_prdata=capture_cpu[31:0];
  3:camera_prdata=capture_cpu[63:32];
  4:camera_prdata=capture_cpu[95:64];
  5:camera_prdata=capture_cpu[127:96];
  6:camera_prdata=camera_cpu[63:32];
  7:camera_prdata=camera_cpu[95:64];
  8:camera_prdata=camera_cpu[127:96];
  9:camera_prdata=camera_cpu[159:128];
  10:camera_prdata=underflow_cpu;
  11:camera_prdata=camera_cpu[191:160];
  default:if(apb_paddr[7:2]>=16&&apb_paddr[7:2]<25)camera_prdata=camera_cpu[192+(apb_paddr[7:2]-16)*32+:32];
 endcase
end
assign apb_prdata=camera_sel?camera_prdata:sensor_prdata;
assign apb_pready=camera_sel?1'b1:sensor_ready;
assign apb_pslverror=camera_sel?(apb_psel&&apb_penable&&(apb_pwrite||apb_paddr[1:0]!=0||
 !((apb_paddr[7:2]<=11)||(apb_paddr[7:2]>=16&&apb_paddr[7:2]<25)))):sensor_error;
'''
t=t[:start]+block+t[stop:]
old='.paddr(apb_paddr),.psel(apb_psel),.penable(apb_penable),.pwrite(apb_pwrite),\n .pwdata(apb_pwdata),.prdata(apb_prdata),.pready(apb_pready),.pslverror(apb_pslverror),'
new='.paddr(apb_paddr),.psel(apb_psel&&!camera_sel),.penable(apb_penable),.pwrite(apb_pwrite),\n .pwdata(apb_pwdata),.prdata(sensor_prdata),.pready(sensor_ready),.pslverror(sensor_error),\n .frame_request(frame_request),.video_take(video_take),.pixel_index(pixel_index),.video_rgb(video_rgb),.video_valid(video_valid),'
assert old in t;t=t.replace(old,new);top.write_text(t)
p=src/'fusion/fusion_sensor_hdmi.v';t=p.read_text().replace('// Stage 1: real sensor display on the shared Sapphire/DDR SoC. No image ROM.','// Shared scanner for real camera and sensor inputs. No test image ROM.')
t=t.replace(' input wire cpu_clk',' output wire frame_request,video_take,output wire [2:0] pixel_index,\n input wire [23:0] video_rgb,input wire video_valid,\n input wire cpu_clk',1)
t=t.replace('thermal_page page','fusion_page page').replace('.cpu_trap(1\'b0),','')
t=t.replace('.cpu_record(record),','.video_rgb(video_rgb),.video_valid(video_valid),.frame_request(frame_request),.video_take(video_take),.pixel_index(pixel_index),\n  .cpu_record(record),')
p.write_text(t)
ns='http://www.efinixinc.com/enf_proj';E.register_namespace('efx',ns);q=lambda n:'{'+ns+'}'+n
tree=E.parse(dst/'Ti60_Multimodal.xml');r=tree.getroot();di=r.find(q('design_info'))
for p in (src/'fusion').glob('*.v'):
 name=p.relative_to(dst).as_posix()
 if not any(x.get('name')==name for x in di):di.insert(len(di)-1,E.Element(q('design_file'),name=name,version='default',library='default'))
sy=r.find(q('synthesis'))
for x in list(sy):
 if x.get('name')=='include':sy.remove(x)
for path in ['ip/sapphire_soc','ip/csi_rx_controller','src/camera/sc431hai']:
 E.SubElement(sy,q('param'),name='include',value=path,value_type='e_string')
tree.write(dst/'Ti60_Multimodal.xml',encoding='utf-8',xml_declaration=True)
print('Connected camera pins:',names)
