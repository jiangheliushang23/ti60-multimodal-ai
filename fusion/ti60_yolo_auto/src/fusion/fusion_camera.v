// Only the verified CSI receiver and ISP; no second DDR, CPU, HDMI or UART.
module fusion_camera(
 input wire clk,cam_clk,reset,
 input wire cpu_clk,auto_psel,auto_penable,auto_pwrite,
 input wire [7:0] auto_paddr,input wire [31:0] auto_pwdata,
 output wire [31:0] auto_prdata,output wire auto_error,
 output wire stream_vs,stream_de,output wire [47:0] stream_rgb,
 output wire sof,output wire packed_sof,output wire [15:0] frame_seq,
 output wire packed_valid,output wire [127:0] packed_data,output wire packed_complete,packed_bad,
 output wire end_valid,output wire [16:0] end_data,
 output wire [255:0] capture_stats,output wire [31:0] setup_status,
 output wire [287:0] diagnostic_words,
input	 wire		io_cam_sda_IN,
    output wire   io_cam_sda_OUT,
    output wire		io_cam_sda_OE,

    output io_cam_scl_OUT,
    input io_cam_scl_IN,
    output io_cam_scl_OE,

    output	wire		o_cam_rst_p,
    
    input	wire		i_cam_ck_LP_P_IN,
    input	wire		i_cam_ck_LP_N_IN,
    output	wire		o_cam_ck_HS_TERM,
    output	wire		o_cam_ck_HS_ENA,
    input	wire		i_cam_ck_CLKOUT,
    
    input	wire	[7:0]			cam_d0_HS_IN,
    input	  wire		      cam_d0_LP_P_IN,
    input	  wire		      cam_d0_LP_N_IN,
    output	wire		      cam_d0_HS_TERM,
    output	wire		      cam_d0_HS_ENA,
    output	wire		      cam_d0_RST,
    output	wire		      cam_d0_FIFO_RD,
    input	  wire		      cam_d0_FIFO_EMPTY,
    
    input 	wire	[7:0]			cam_d1_HS_IN,
    input	  wire		        cam_d1_LP_P_IN,
    input	  wire		        cam_d1_LP_N_IN,
    output	wire		        cam_d1_HS_TERM,
    output	wire		        cam_d1_HS_ENA,
    output	wire		        cam_d1_RST,
    output	wire		        cam_d1_FIFO_RD,
    input	  wire		        cam_d1_FIFO_EMPTY,
    
    input 	wire	[7:0]			cam_d2_HS_IN,
    input	  wire		        cam_d2_LP_P_IN,
    input	  wire		        cam_d2_LP_N_IN,
    output	wire		        cam_d2_HS_TERM,
    output	wire		        cam_d2_HS_ENA,
    output	wire		        cam_d2_RST,
    output	wire		        cam_d2_FIFO_RD,
    input	  wire		        cam_d2_FIFO_EMPTY,  
   
    input 	wire	[7:0]			cam_d3_HS_IN,
    input	  wire		        cam_d3_LP_P_IN,
    input	  wire		        cam_d3_LP_N_IN,
    output	wire		        cam_d3_HS_TERM,
    output	wire		        cam_d3_HS_ENA,
    output	wire		        cam_d3_RST,
    output	wire		        cam_d3_FIFO_RD,
    input	  wire		        cam_d3_FIFO_EMPTY);
 wire i_mipi_rx_pclk=cam_clk;
 wire [63:0] w_mipi_rx_data;
 wire w_mipi_rx_hs,w_mipi_rx_vs,w_mipi_rx_de;
 wire [1:0] csi_vc;wire [5:0] csi_dt;wire [15:0] csi_wc;wire [3:0] csi_ppc;wire csi_irq;
 assign {cam_d0_RST,cam_d1_RST,cam_d2_RST,cam_d3_RST}={4{reset}};
 assign io_cam_scl_OUT=0;assign io_cam_sda_OUT=0;
 wire stats_request,stats_ack;wire [156:0] stats_held;
 wire rt_start,rt_read,rt_busy,rt_done;wire [15:0] rt_address;wire [7:0] rt_data,rt_read_data;wire [2:0] rt_result;
 wire [9:0] gain_r,gain_b;
 camera_auto_apb auto_apb(.reset(reset),.cpu_clk(cpu_clk),.isp_clk(clk),.sof(sof),
  .psel(auto_psel),.penable(auto_penable),.pwrite(auto_pwrite),.paddr(auto_paddr),.pwdata(auto_pwdata),
  .prdata(auto_prdata),.pslverror(auto_error),.stats_request(stats_request),.stats_ack(stats_ack),.stats_held(stats_held),
  .rt_start(rt_start),.rt_read(rt_read),.rt_address(rt_address),.rt_data(rt_data),.rt_busy(rt_busy),.rt_done(rt_done),
  .rt_result(rt_result),.rt_read_data(rt_read_data),.gain_r(gain_r),.gain_b(gain_b));
 wire cam_enable,id_ok,config_ok,stream_set,finished,diagnostic_valid;
 // J4 module reset is active HIGH (same inversion as the verified camera top).
 assign o_cam_rst_p=~cam_enable;
 wire [2:0] error_code;wire [7:0] command_index;
 sc431hai_setup #(.CLK_PER_MS(100000),.I2C_TICK(1000)) setup(
  .clk(clk),.reset(reset),.scl_in(io_cam_scl_IN),.sda_in(io_cam_sda_IN),
  .scl_low(io_cam_scl_OE),.sda_low(io_cam_sda_OE),.cam_enable(cam_enable),
  .id_ok(id_ok),.config_ok(config_ok),.stream_set(stream_set),.finished(finished),
  .error_code(error_code),.command_index(command_index),.diagnostic_words(diagnostic_words),.diagnostic_valid(diagnostic_valid),
  .rt_start(rt_start),.rt_read(rt_read),.rt_address(rt_address),.rt_data(rt_data),
  .rt_busy(rt_busy),.rt_done(rt_done),.rt_result(rt_result),.rt_read_data(rt_read_data));
 assign setup_status={16'd0,command_index,error_code,finished,stream_set,config_ok,id_ok,cam_enable};
		csi_rx_controller inst_efx_csi2_rx
		(
              .reset_n			(!reset),
              .clk				(clk),
              .reset_byte_HS_n	(!reset),
              .clk_byte_HS		  (i_cam_ck_CLKOUT),
              .reset_pixel_n		(!reset),
              .clk_pixel			  (i_mipi_rx_pclk),
              
              .Rx_LP_CLK_P		  (i_cam_ck_LP_P_IN),
              .Rx_LP_CLK_N		  (i_cam_ck_LP_N_IN),
              .Rx_HS_enable_C		(o_cam_ck_HS_ENA),
              .LVDS_termen_C		(o_cam_ck_HS_TERM),
              
              .Rx_LP_D_P			({cam_d3_LP_P_IN, cam_d2_LP_P_IN, cam_d1_LP_P_IN, cam_d0_LP_P_IN}),//(r_mipi_rx_data_LP_P_IN_2P),
              .Rx_LP_D_N			({cam_d3_LP_N_IN, cam_d2_LP_N_IN, cam_d1_LP_N_IN, cam_d0_LP_N_IN}),//(r_mipi_rx_data_LP_N_IN_2P),
              .Rx_HS_D_0			(cam_d0_HS_IN),//(r_mipi_rx_data_HS_IN_2P[0*8+:8]),
              .Rx_HS_D_1			(cam_d1_HS_IN),//(r_mipi_rx_data_HS_IN_2P[1*8+:8]),
              .Rx_HS_D_2			(cam_d2_HS_IN),
              .Rx_HS_D_3			(cam_d3_HS_IN),
              .Rx_HS_D_4			(),
              .Rx_HS_D_5			(),
              .Rx_HS_D_6			(),
              .Rx_HS_D_7			(),
              .Rx_HS_enable_D		({cam_d3_HS_ENA    ,cam_d2_HS_ENA    ,cam_d1_HS_ENA    ,cam_d0_HS_ENA    }),//( w_cam_d_HS_ENA),
              .LVDS_termen_D		({cam_d3_HS_TERM   ,cam_d2_HS_TERM   ,cam_d1_HS_TERM   ,cam_d0_HS_TERM   }),
              .fifo_rd_enable		({cam_d3_FIFO_RD   ,cam_d2_FIFO_RD   ,cam_d1_FIFO_RD   ,cam_d0_FIFO_RD   }),
              .fifo_rd_empty		({cam_d3_FIFO_EMPTY,cam_d2_FIFO_EMPTY,cam_d1_FIFO_EMPTY,cam_d0_FIFO_EMPTY}),
              .DLY_enable_D		       (),
              .DLY_inc_D			(),
              .u_dly_enable_D		(),
              .u_dly_inc_D		       (),
              
              .axi_clk			(1'b0),
              .axi_reset_n		       (1'b0),
              .axi_awaddr			(6'b0),
              .axi_awvalid		       (1'b0),
              .axi_awready		       (),
              .axi_wdata			(32'b0),
              .axi_wvalid			(1'b0),
              .axi_wready			(),
              
              .axi_bvalid			(),
              .axi_bready			(1'b0),
              .axi_araddr			(6'b0),
              .axi_arvalid		       (1'b0),
              .axi_arready		       (),
              .axi_rdata			(),
              .axi_rvalid			(),
              .axi_rready			(1'b1),
              
              .hsync_vc0			(w_mipi_rx_hs),
              .hsync_vc1			(),
              .hsync_vc2			(),
              .hsync_vc3			(),
              .vsync_vc0			(w_mipi_rx_vs),
              .vsync_vc1			(),
              .vsync_vc2			(),
              .vsync_vc3			(),
              .vc (csi_vc),
              .word_count (csi_wc),
              .shortpkt_data_field        (),
              .datatype (csi_dt),
              .pixel_per_clk (csi_ppc),
              .pixel_data			(w_mipi_rx_data),
              .pixel_data_valid	       (w_mipi_rx_de),
              .irq (csi_irq)//,
              // .mipi_debug_out(mipi_debug_out)
		);


 wire raw_vs,raw_de;wire [15:0] raw_pair;
 camera_line_bridge line_bridge(.reset(reset),.cam_clk(cam_clk),.clk(clk),.vs(w_mipi_rx_vs),.de(w_mipi_rx_de),
  .raw({w_mipi_rx_data[39:32],w_mipi_rx_data[29:22],w_mipi_rx_data[19:12],w_mipi_rx_data[9:2]}),
  .vc(csi_vc),.dt(csi_dt),.ppc(csi_ppc),.wc(csi_wc),
  .raw_vs(raw_vs),.raw_de(raw_de),.raw_pair(raw_pair),.sof(sof),.sequence_out(frame_seq),
  .end_valid(end_valid),.end_data(end_data),.good_frames(capture_stats[31:0]),.bad_frames(capture_stats[63:32]),
  .period_ticks(capture_stats[95:64]),.overflow_lines(capture_stats[127:96]),
  .stats_request(stats_request),.stats_ack(stats_ack),.stats_held(stats_held),
  .last_pixels(capture_stats[159:128]),.last_format(capture_stats[191:160]),
  .last_de_runs(capture_stats[223:192]),.last_packing(capture_stats[255:224]));
 wire rgb_vs,rgb_de;wire [47:0] rgb_pair,gamma_pair;wire gamma_vs,gamma_de;
 debayer_top_2to1 isp(.in_pclk(clk),.in_rstn(!reset),.raw_vs_i(raw_vs),.raw_hs_i(1'b0),
  .raw_de_i(raw_de),.raw_valid_i(raw_de),.raw_datax4_i(raw_pair),.r_gain({6'd0,gain_r}),.g_gain(16'd256),.b_gain({6'd0,gain_b}),
  .rgb_vs_o(rgb_vs),.rgb_hs_o(),.rgb_de_o(rgb_de),.rgb_valid_o(),.rgb_bout(),.rgb_gout(),.rgb_rout(),.rgb_datax2_o(rgb_pair));
 camera_gamma_pair_u8 gamma(.clk(clk),.reset(reset),.valid(rgb_de),.vs(rgb_vs),
  .rgb_pair(rgb_pair),.corrected_pair(gamma_pair),
  .corrected_valid(gamma_de),.corrected_vs(gamma_vs));
 assign stream_vs=gamma_vs;assign stream_de=gamma_de;assign stream_rgb=gamma_pair;
 assign packed_sof=gamma_vs;
 camera_rgb_pack pack(.clk(clk),.reset(reset),.vs(gamma_vs),.de(gamma_de),.rgb(gamma_pair),
  .valid(packed_valid),.data(packed_data),.complete(packed_complete),.malformed(packed_bad));
endmodule
