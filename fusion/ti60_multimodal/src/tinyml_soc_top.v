//***************************************************************/
//
// Moudel Name    : ddr3_example_top.v
// Version        : 1.1
// Date Created   : 2023-02-23 10:37:59
// Last Modified  : 2023-02-24 15:27:41
// Abstract       : ---
//
//***************************************************************/
//Modification History
//1.initial
//***************************************************************/
`include "ddr3_controller/ddr3_parameter.vh"
`include "define.v"
`include "src/tinyml/defines.v"
module tinyml_soc_top #
(
parameter                       RANK_RATIO         = 1,       // # of unique CS outputs per rank
parameter                       CK_RATIO           = `CK_RATIO, 
parameter                       ASYN_AXI_CLK       = `ASYN_AXI_CLK, 
parameter                       RANKS              = `RANKS,
parameter                       CK_WIDTH           = `CK_WIDTH,       // # of CK/CK# outputs to memory   
parameter                       CKE_WIDTH          = `CKE_WIDTH,       // # of cke outputs
parameter                       CS_WIDTH           = `CS_WIDTH,       // # of unique CS outputs
parameter                       BANK_WIDTH         = `BANK_WIDTH,       // # of bank bits
parameter                       ROW_WIDTH          = `ROW_WIDTH,       // DRAM address bus width
parameter                       COL_WIDTH          = `COL_WIDTH,      // column address width
parameter                       DM_WIDTH           = `DM_WIDTH,       // # of DM (data mask)
parameter                       DQS_WIDTH          = `DQS_WIDTH,       // # of DQS (strobe)
parameter                       DQ_WIDTH           = `DQ_WIDTH,      // # of DQ (data)
parameter                       ODT_WIDTH          = `ODT_WIDTH,
parameter                       DQ_CNT_WIDTH       = `DQ_CNT_WIDTH,       // = ceil(log2(DQ_WIDTH))
parameter                       DQS_CNT_WIDTH      = `DQS_CNT_WIDTH,       // = ceil(log2(DQS_WIDTH))  
parameter                       DRAM_WIDTH         = `DRAM_WIDTH,       // # of DQ per DQS   
parameter                       DATA_WIDTH         = `DATA_WIDTH,
parameter                       ADDR_WIDTH         = `ADDR_WIDTH,    
parameter                       AXI_ID_WIDTH       = `AXI_ID_WIDTH,
parameter                       AXI_ADDR_WIDTH     = `AXI_ADDR_WIDTH,
parameter                       AXI_DATA_WIDTH     = `AXI_DATA_WIDTH
)
(

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
    input	  wire		        cam_d3_FIFO_EMPTY,
   input i_mipi_rx_pclk,camera_pll_locked,
   input hdmi_tx_slow_clk, hdmi_tx_locked,
   input sht_scl_IN,sht_sda_IN,ir_scl_IN,ir_sda_IN,
   output sht_scl_OUT,sht_scl_OE,sht_sda_OUT,sht_sda_OE,
   output ir_scl_OUT,ir_scl_OE,ir_sda_OUT,ir_sda_OE,
   output [9:0] tmds_clk_o,tmds_data0_o,tmds_data1_o,tmds_data2_o,
   output tmds_clk_TX_OE,tmds_data0_TX_OE,tmds_data1_TX_OE,tmds_data2_TX_OE,
   output tmds_clk_TX_RST,tmds_data0_TX_RST,tmds_data1_TX_RST,tmds_data2_TX_RST,
   // Clock and reset ports
   input                              axi_clk,      
   input                              core_clk,     // CORE CLK @ 100MHz
   input                              sdram_clk,    // SDRAM CK @ 400MHz
   input                              rx_cal_clk,   // SDRAM CK @ 400MHz
   input                              tx_cal_clk,   // SDRAM CK @ 400MHz
   input                              tx_cal_clk_90edge,   // SDRAM CK @ 400MHz
   input                              pll_locked,
   input                              user_pll_locked,
   input                              i_sysclk,
   input                              i_peripheralClk,
   input                              i_fb_clk,
   //&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&
   output  wire                       system_uart_0_io_txd,
   input                              system_uart_0_io_rxd,   
    // debug core ports
`ifdef  Efinity_Debug  //&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&& 
`ifdef RISCV_SOFT_JTAG
  input                               io_jtag_tms,
  input                               io_jtag_tdi,
  output  wire                        io_jtag_tdo,
  input                               io_jtag_tck,
`else
  // V4 baseline uses CPU USER JTAG1 only; unused JTAG2 ports removed.
`endif 
  input                               jtag_inst1_CAPTURE ,
  input                               jtag_inst1_DRCK    ,
  input                               jtag_inst1_RESET   ,
  input                               jtag_inst1_RUNTEST ,
  input                               jtag_inst1_SEL     ,
  input                               jtag_inst1_SHIFT   ,
  input                               jtag_inst1_TCK     ,
  input                               jtag_inst1_TDI     ,
  input                               jtag_inst1_TMS     ,
  input                               jtag_inst1_UPDATE  ,
  output                              jtag_inst1_TDO     ,
`endif  //&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&
   // PLL status flags  
   output [2:0]                       pll_shift,  
   output [4:0]                       pll_shift_sel,
   output                             pll_shift_ena,  
   // memory interface ports
   output                             ddr_ck_hi,
   output                             ddr_ck_lo,
   output                             ddr_reset_n,
   output [CKE_WIDTH-1:0]             ddr_cke,     
   output [ROW_WIDTH-1:0]             ddr_addr,
   output [BANK_WIDTH-1:0]            ddr_ba,
   output                             ddr_cas_n,

   output [CS_WIDTH*RANK_RATIO-1:0]   ddr_cs_n,
   output                             ddr_ras_n,
   output                             ddr_we_n,
   
   input  [DQS_WIDTH-1:0]             ddr_dqs_in_hi,
   input  [DQS_WIDTH-1:0]             ddr_dqs_in_lo,
   input  [DQ_WIDTH-1:0]              ddr_dq_in_hi,
   input  [DQ_WIDTH-1:0]              ddr_dq_in_lo,
   
   output [DQS_WIDTH-1:0]             ddr_dqs_oe,
   output [DQS_WIDTH-1:0]             ddr_dqs_oe_n,
   output [DQ_WIDTH-1:0]              ddr_dq_oe,  
   output [DQS_WIDTH-1:0]             ddr_dqs_out_hi,
   output [DQS_WIDTH-1:0]             ddr_dqs_out_lo,
   output [DQ_WIDTH-1:0]              ddr_dq_out_hi,
   output [DQ_WIDTH-1:0]              ddr_dq_out_lo,
   output [DM_WIDTH-1:0]              ddr_dm_hi,
   output [DM_WIDTH-1:0]              ddr_dm_lo,
   output [ODT_WIDTH-1:0]             ddr_odt

   );


      
//Parameter Define
parameter FREQ = 200;			// default is 100 MHz.  Redefine as needed.
`ifndef SIM
    localparam CNT_INIT = 1.5*FREQ*1000;
`else
    localparam CNT_INIT = 10;
`endif    
  localparam   AIW               = AXI_ID_WIDTH      ;
  localparam   ADW               = AXI_DATA_WIDTH    ;
  localparam   ABN               = AXI_DATA_WIDTH/8   ;
  /////////////////////////////////////////////////////////
  // Wire declarations
  reg  [19:0]                       cnt;    
  wire                              clk;
  wire                              rst;
  wire                              mmcm_locked;
  reg                               aresetn;
  wire                              app_sr_active;
  wire                              app_ref_ack;
  wire                              app_zq_ack;

  wire                              cal_done;


//Custom instruction
wire                    cpu_customInstruction_cmd_valid;
wire                    cpu_customInstruction_cmd_ready;
wire  [9:0]             cpu_customInstruction_function_id;
wire  [31:0]            cpu_customInstruction_inputs_0;
wire  [31:0]            cpu_customInstruction_inputs_1;
wire                    cpu_customInstruction_rsp_valid;
wire                    cpu_customInstruction_rsp_ready;
wire  [31:0]            cpu_customInstruction_outputs_0;
wire                    cpu_customInstruction_cmd_int;
wire                    userInterruptA;

localparam AXI_TINYML_DATA_WIDTH = 128;

wire [7:0]              axi_inter_s0_awid;
wire [31:0]             axi_inter_s0_awaddr;
wire [7:0]              axi_inter_s0_awlen;
wire [2:0]              axi_inter_s0_awsize;
wire [1:0]              axi_inter_s0_awburst;
wire                    axi_inter_s0_awlock;
wire [3:0]              axi_inter_s0_awcache;
wire [2:0]              axi_inter_s0_awprot;
wire [3:0]              axi_inter_s0_awqos;
wire                    axi_inter_s0_awvalid;
wire                    axi_inter_s0_awready;
wire [127:0]            axi_inter_s0_wdata;
wire [15:0]             axi_inter_s0_wstrb;
wire                    axi_inter_s0_wlast;
wire                    axi_inter_s0_wvalid;
wire                    axi_inter_s0_wready;
wire [7:0]              axi_inter_s0_bid;
wire [1:0]              axi_inter_s0_bresp;
wire                    axi_inter_s0_bvalid;
wire                    axi_inter_s0_bready;
wire [7:0]              axi_inter_s0_arid;
wire [31:0]             axi_inter_s0_araddr;
wire [7:0]              axi_inter_s0_arlen;
wire [2:0]              axi_inter_s0_arsize;
wire [1:0]              axi_inter_s0_arburst;
wire                    axi_inter_s0_arlock;
wire [3:0]              axi_inter_s0_arcache;
wire [2:0]              axi_inter_s0_arprot;
wire [3:0]              axi_inter_s0_arqos;
wire                    axi_inter_s0_arvalid;
wire                    axi_inter_s0_arready;
wire [7:0]              axi_inter_s0_rid;
wire [127:0]            axi_inter_s0_rdata;
wire [1:0]              axi_inter_s0_rresp;
wire                    axi_inter_s0_rlast;
wire                    axi_inter_s0_rvalid;
wire                    axi_inter_s0_rready;

wire [7:0]              axi_inter_s1_awid;
wire [31:0]             axi_inter_s1_awaddr;
wire [7:0]              axi_inter_s1_awlen;
wire [2:0]              axi_inter_s1_awsize;
wire [1:0]              axi_inter_s1_awburst;
wire                    axi_inter_s1_awlock;
wire [3:0]              axi_inter_s1_awcache;
wire [2:0]              axi_inter_s1_awprot;
wire [3:0]              axi_inter_s1_awqos;
wire                    axi_inter_s1_awvalid;
wire                    axi_inter_s1_awready;
wire [127:0]            axi_inter_s1_wdata;
wire [15:0]             axi_inter_s1_wstrb;
wire                    axi_inter_s1_wlast;
wire                    axi_inter_s1_wvalid;
wire                    axi_inter_s1_wready;
wire [7:0]              axi_inter_s1_bid;
wire [1:0]              axi_inter_s1_bresp;
wire                    axi_inter_s1_bvalid;
wire                    axi_inter_s1_bready;
wire [7:0]              axi_inter_s1_arid;
wire [31:0]             axi_inter_s1_araddr;
wire [7:0]              axi_inter_s1_arlen;
wire [2:0]              axi_inter_s1_arsize;
wire [1:0]              axi_inter_s1_arburst;
wire                    axi_inter_s1_arlock;
wire [3:0]              axi_inter_s1_arcache;
wire [2:0]              axi_inter_s1_arprot;
wire [3:0]              axi_inter_s1_arqos;
wire                    axi_inter_s1_arvalid;
wire                    axi_inter_s1_arready;
wire [7:0]              axi_inter_s1_rid;
wire [127:0]            axi_inter_s1_rdata;
wire [1:0]              axi_inter_s1_rresp;
wire                    axi_inter_s1_rlast;
wire                    axi_inter_s1_rvalid;
wire                    axi_inter_s1_rready;

wire [7:0]              axi_inter_s2_awid;
wire [31:0]             axi_inter_s2_awaddr;
wire [7:0]              axi_inter_s2_awlen;
wire [2:0]              axi_inter_s2_awsize;
wire [1:0]              axi_inter_s2_awburst;
wire                    axi_inter_s2_awlock;
wire [3:0]              axi_inter_s2_awcache;
wire [2:0]              axi_inter_s2_awprot;
wire [3:0]              axi_inter_s2_awqos;
wire                    axi_inter_s2_awvalid;
wire                    axi_inter_s2_awready;
wire [AXI_TINYML_DATA_WIDTH-1:0]            axi_inter_s2_wdata;
wire [AXI_TINYML_DATA_WIDTH/8-1:0]             axi_inter_s2_wstrb;
wire                    axi_inter_s2_wlast;
wire                    axi_inter_s2_wvalid;
wire                    axi_inter_s2_wready;
wire [7:0]              axi_inter_s2_bid;
wire [1:0]              axi_inter_s2_bresp;
wire                    axi_inter_s2_bvalid;
wire                    axi_inter_s2_bready;
wire [7:0]              axi_inter_s2_arid;
wire [31:0]             axi_inter_s2_araddr;
wire [7:0]              axi_inter_s2_arlen;
wire [2:0]              axi_inter_s2_arsize;
wire [1:0]              axi_inter_s2_arburst;
wire                    axi_inter_s2_arlock;
wire [3:0]              axi_inter_s2_arcache;
wire [2:0]              axi_inter_s2_arprot;
wire [3:0]              axi_inter_s2_arqos;
wire                    axi_inter_s2_arvalid;
wire                    axi_inter_s2_arready;
wire [7:0]              axi_inter_s2_rid;
wire [AXI_TINYML_DATA_WIDTH-1:0]            axi_inter_s2_rdata;
wire [1:0]              axi_inter_s2_rresp;
wire                    axi_inter_s2_rlast;
wire                    axi_inter_s2_rvalid;
wire                    axi_inter_s2_rready;

wire [7:0]              axi_inter_m_awid;
wire [31:0]             axi_inter_m_awaddr;
wire [7:0]              axi_inter_m_awlen;
wire [2:0]              axi_inter_m_awsize;
wire [1:0]              axi_inter_m_awburst;
wire                    axi_inter_m_awlock;
wire [3:0]              axi_inter_m_awcache;
wire [2:0]              axi_inter_m_awprot;
wire [3:0]              axi_inter_m_awqos;
wire [3:0]              axi_inter_m_awregion;
wire                    axi_inter_m_awvalid;
wire                    axi_inter_m_awready;
wire [127:0]            axi_inter_m_wdata;
wire [15:0]             axi_inter_m_wstrb;
wire                    axi_inter_m_wlast;
wire                    axi_inter_m_wvalid;
wire                    axi_inter_m_wready;
wire [7:0]              axi_inter_m_bid;
wire [1:0]              axi_inter_m_bresp;
wire                    axi_inter_m_bvalid;
wire                    axi_inter_m_bready;
wire [7:0]              axi_inter_m_arid;
wire [31:0]             axi_inter_m_araddr;
wire [7:0]              axi_inter_m_arlen;
wire [2:0]              axi_inter_m_arsize;
wire [1:0]              axi_inter_m_arburst;
wire                    axi_inter_m_arlock;
wire [3:0]              axi_inter_m_arcache;
wire [2:0]              axi_inter_m_arprot;
wire [3:0]              axi_inter_m_arqos;
wire [3:0]              axi_inter_m_arregion;
wire                    axi_inter_m_arvalid;
wire                    axi_inter_m_arready;
wire [7:0]              axi_inter_m_rid;
wire [127:0]            axi_inter_m_rdata;
wire [1:0]              axi_inter_m_rresp;
wire                    axi_inter_m_rlast;
wire                    axi_inter_m_rvalid;
wire                    axi_inter_m_rready;

  wire                              ddr_reset; 
  wire                              sys_rst;
  wire  [2:0]                       phy_wr_pll_shift;
  wire                              idelay_ld       ;
  wire                              mpr_rdlvl_dly   ;
  wire  [7:0]                       wrlvl_dq_check  ;
  wire  [7:0]                       rd_level_dqs_check;  
  wire  [2:0]                       rdlvl_shift;  
  wire  [2:0]                       wrlvl_shift;  
  wire  [15:0]                      debug_fifo;  
  wire  [15:0]                      overflow_fifo;  
  wire  [6:0]                       init_cur_state;  
  wire  [35:0]                      ddr_debug_port;  
  wire                              app_rdy;  
  wire                              user_clk;  
  wire                              ddr_rstn;  

  
// Start of User Design top instance
//***************************************************************************
// The User design is instantiated below. The memory interface ports are
// connected to the top-level and the application interface ports are
// connected to the traffic generator module. This provides a reference
// for connecting the memory controller to system.
//***************************************************************************
always @(posedge user_clk or negedge sys_rst) begin
	if (!sys_rst)
		cnt <= 0;
    else if (cnt != CNT_INIT) 
        cnt <= cnt + 20'd1;
	else 
        cnt <= cnt;
end
assign ddr_rstn = (cnt == CNT_INIT);


generate
if (ASYN_AXI_CLK) begin
assign user_clk = axi_clk;

end else begin
assign user_clk = core_clk;
end
endgenerate
//***************************************************************************
// The traffic generation module instantiated below drives traffic (patterns)
// on the application interface of the memory controller
//***************************************************************************
//***************************************************************************

assign sys_rst       = pll_locked & user_pll_locked;

//***************************************************************************
ddr3_top                 u_ddr3_top
      (
      
    .axi_clk                (axi_clk             ),
    .core_clk               (core_clk            ),
    .sdram_clk              (sdram_clk           ),  
    .rx_cal_clk             (rx_cal_clk          ),
    .tx_cal_clk             (tx_cal_clk          ),
    .tx_cal_clk_90edge      (tx_cal_clk_90edge   ),
    .rstn                   (ddr_rstn            ),      
    .pll_shift              (pll_shift           ),
    .pll_shift_sel          (pll_shift_sel       ),
    .pll_shift_ena          (pll_shift_ena       ), 
///////////////DDR BUS
    .ddr_ck_hi              (ddr_ck_hi           ),
    .ddr_ck_lo              (ddr_ck_lo           ),
    .ddr_cke                (ddr_cke             ),    
    .ddr_reset_n            (ddr_reset_n         ),
    .ddr_cs_n               (ddr_cs_n            ),
    .ddr_ras_n              (ddr_ras_n           ),
    .ddr_cas_n              (ddr_cas_n           ),
    .ddr_we_n               (ddr_we_n            ),     
    .ddr_addr               (ddr_addr            ),
    .ddr_ba                 (ddr_ba              ),

    .ddr_dqs_oe             (ddr_dqs_oe          ),
    .ddr_dqs_oe_n           (ddr_dqs_oe_n        ),
    .ddr_dq_oe              (ddr_dq_oe           ),
    .ddr_dqs_in_hi          (ddr_dqs_in_hi       ),
    .ddr_dqs_in_lo          (ddr_dqs_in_lo       ),
    .ddr_dq_in_hi           (ddr_dq_in_hi        ),
    .ddr_dq_in_lo           (ddr_dq_in_lo        ),

    .ddr_dqs_out_hi         (ddr_dqs_out_hi      ),
    .ddr_dqs_out_lo         (ddr_dqs_out_lo      ),
    .ddr_dq_out_hi          (ddr_dq_out_hi       ),
    .ddr_dq_out_lo          (ddr_dq_out_lo       ),
    
    .ddr_dm_hi              (ddr_dm_hi           ),
    .ddr_dm_lo              (ddr_dm_lo           ),
    .ddr_odt                (ddr_odt             ),

// Application interface ports
       .app_sr_req                     (1'b0),
       .app_ref_req                    (1'b0),
       .app_zq_req                     (1'b0),
       .app_sr_active                  (app_sr_active),
       .app_ref_ack                    (app_ref_ack),
       .app_zq_ack                     (app_zq_ack),

// Slave Interface Write Address Ports
       .s_axi_awid                     (axi_inter_m_awid        ),
       .s_axi_awaddr                   (axi_inter_m_awaddr      ),
       .s_axi_awlen                    (axi_inter_m_awlen       ),
       .s_axi_awsize                   (axi_inter_m_awsize      ),
       .s_axi_awburst                  (axi_inter_m_awburst     ),
       .s_axi_awlock                   (axi_inter_m_awlock      ),
       .s_axi_awcache                  (axi_inter_m_awcache     ),
       .s_axi_awprot                   (axi_inter_m_awprot      ),
       .s_axi_awqos                    (axi_inter_m_awqos       ),
       .s_axi_awvalid                  (axi_inter_m_awvalid     ),
       .s_axi_awready                  (axi_inter_m_awready     ),
// Slave Interface Write Data Ports
       .s_axi_wdata                    (axi_inter_m_wdata       ),
       .s_axi_wstrb                    (axi_inter_m_wstrb       ),
       .s_axi_wlast                    (axi_inter_m_wlast       ),
       .s_axi_wvalid                   (axi_inter_m_wvalid      ),
       .s_axi_wready                   (axi_inter_m_wready      ),
// Slave Interface Write Response Ports
       .s_axi_bid                      (axi_inter_m_bid         ),
       .s_axi_bresp                    (axi_inter_m_bresp       ),
       .s_axi_bvalid                   (axi_inter_m_bvalid      ),
       .s_axi_bready                   (axi_inter_m_bready      ),
// Slave Interface Read Address Ports
       .s_axi_arid                     (axi_inter_m_arid        ),
       .s_axi_araddr                   (axi_inter_m_araddr      ),
       .s_axi_arlen                    (axi_inter_m_arlen       ),
       .s_axi_arsize                   (axi_inter_m_arsize      ),
       .s_axi_arburst                  (axi_inter_m_arburst     ),
       .s_axi_arlock                   (axi_inter_m_arlock      ),
       .s_axi_arcache                  (axi_inter_m_arcache     ),
       .s_axi_arprot                   (axi_inter_m_arprot      ),
       .s_axi_arqos                    (axi_inter_m_arqos              ),
       .s_axi_arvalid                  (axi_inter_m_arvalid     ),
       .s_axi_arready                  (axi_inter_m_arready     ),
// Slave Interface Read Data Ports
       .s_axi_rid                      (axi_inter_m_rid         ),
       .s_axi_rdata                    (axi_inter_m_rdata       ),
       .s_axi_rresp                    (axi_inter_m_rresp       ),
       .s_axi_rlast                    (axi_inter_m_rlast       ),
       .s_axi_rvalid                   (axi_inter_m_rvalid      ),
       .s_axi_rready                   (axi_inter_m_rready      ),
//DEBUG       
       .wrlvl_dq_check                 (wrlvl_dq_check    ) ,
       .rd_level_dqs_check             (rd_level_dqs_check) ,
       .rdlvl_shift                    (rdlvl_shift) ,
       .wrlvl_shift                    (wrlvl_shift) ,
       .init_cur_state                 (init_cur_state    ) ,
       .idelay_ld                      (idelay_ld         ) ,
       .mpr_rdlvl_dly                  (mpr_rdlvl_dly     ) ,
       .ddr_debug_port                 (ddr_debug_port    ) ,
       .cal_done                       (cal_done          ) 
       );
// End of User Design top instance

//***************************************************************************

//***************************************************************************
wire io_systemReset;
wire io_peripheralReset;
wire [15:0] apb_paddr;
wire [31:0] apb_pwdata,apb_prdata;
wire apb_psel,apb_penable,apb_pwrite,apb_pready,apb_pslverror;
wire io_memoryClk;
assign io_memoryClk = user_clk;
assign userInterruptA = cpu_customInstruction_cmd_int;

//wire io_memoryReset;
sapphire_soc u_sapphire_soc(
    .io_asyncReset                      (!cal_done                        ),
    .io_systemClk                       (i_sysclk                           ),

    //UART 0
    .system_uart_0_io_txd               (system_uart_0_io_txd               ),
    .system_uart_0_io_rxd               (system_uart_0_io_rxd               ),
    .io_memoryClk                       (user_clk                           ),
    .io_memoryReset                     (                                   ),
    .io_systemReset                     (io_systemReset                                   ),
    .io_peripheralClk                   (i_peripheralClk                      ),
    .io_peripheralReset                 (io_peripheralReset),    
    //External Memory AXI4 Interface
    .io_ddrA_aw_payload_prot            (                                  ),
    .io_ddrA_aw_payload_qos             (                                  ),
    .io_ddrA_aw_payload_cache           (                                  ),
    .io_ddrA_aw_payload_lock            (axi_inter_s0_awlock                     ),
    .io_ddrA_aw_payload_burst           (axi_inter_s0_awburst                    ),
    .io_ddrA_aw_payload_size            (axi_inter_s0_awsize                     ),
    .io_ddrA_aw_payload_len             (axi_inter_s0_awlen                      ),
    .io_ddrA_aw_payload_region          (                                  ),
    .io_ddrA_aw_payload_id              (axi_inter_s0_awid                       ),
    .io_ddrA_aw_payload_addr            (axi_inter_s0_awaddr                     ),
    .io_ddrA_aw_ready                   (axi_inter_s0_awready                    ),
    .io_ddrA_aw_valid                   (axi_inter_s0_awvalid                    ),

    .io_ddrA_w_payload_last             (axi_inter_s0_wlast                      ),
    .io_ddrA_w_ready                    (axi_inter_s0_wready                     ),
    .io_ddrA_w_valid                    (axi_inter_s0_wvalid                     ),    
    .io_ddrA_w_payload_strb             (axi_inter_s0_wstrb                      ),
    .io_ddrA_w_payload_data             (axi_inter_s0_wdata                      ),

    .io_ddrA_b_payload_resp             (                                  ),
    .io_ddrA_b_payload_id               (axi_inter_s0_bid                        ),
    .io_ddrA_b_ready                    (axi_inter_s0_bready                     ),
    .io_ddrA_b_valid                    (axi_inter_s0_bvalid                     ),

    .io_ddrA_ar_payload_prot            (                                  ),
    .io_ddrA_ar_payload_qos             (                                  ),
    .io_ddrA_ar_payload_cache           (                                  ),
    .io_ddrA_ar_payload_region          (                                  ),
    .io_ddrA_ar_payload_lock            (axi_inter_s0_arlock                     ),
    .io_ddrA_ar_payload_burst           (axi_inter_s0_arburst                    ),
    .io_ddrA_ar_payload_size            (axi_inter_s0_arsize                     ),
    .io_ddrA_ar_payload_len             (axi_inter_s0_arlen                      ),
    .io_ddrA_ar_payload_id              (axi_inter_s0_arid                       ),
    .io_ddrA_ar_payload_addr            (axi_inter_s0_araddr                     ),
    .io_ddrA_ar_ready                   (axi_inter_s0_arready                    ),
    .io_ddrA_ar_valid                   (axi_inter_s0_arvalid                    ),

    .io_ddrA_r_payload_last             (axi_inter_s0_rlast                      ),
    .io_ddrA_r_payload_resp             (axi_inter_s0_rresp                      ),
    .io_ddrA_r_payload_id               (axi_inter_s0_rid                        ),
    .io_ddrA_r_payload_data             (axi_inter_s0_rdata                      ),
    .io_ddrA_r_ready                    (axi_inter_s0_rready                     ),
    .io_ddrA_r_valid                    (axi_inter_s0_rvalid                     ),
    
    //custom instruction
    .cpu0_customInstruction_cmd_valid   (cpu_customInstruction_cmd_valid),
    .cpu0_customInstruction_cmd_ready   (cpu_customInstruction_cmd_ready),
    .cpu0_customInstruction_function_id (cpu_customInstruction_function_id),
    .cpu0_customInstruction_inputs_0    (cpu_customInstruction_inputs_0),
    .cpu0_customInstruction_inputs_1    (cpu_customInstruction_inputs_1),
    .cpu0_customInstruction_rsp_valid   (cpu_customInstruction_rsp_valid),
    .cpu0_customInstruction_rsp_ready   (cpu_customInstruction_rsp_ready),
    .cpu0_customInstruction_outputs_0   (cpu_customInstruction_outputs_0),
     //SPI 0
    .system_spi_0_io_sclk_write         (system_spi_0_io_sclk_write         ),
    .system_spi_0_io_data_0_writeEnable (system_spi_0_io_data_0_writeEnable ),
    .system_spi_0_io_data_0_read        (system_spi_0_io_data_0_read        ),
    .system_spi_0_io_data_0_write       (system_spi_0_io_data_0_write       ),
    .system_spi_0_io_data_1_writeEnable (system_spi_0_io_data_1_writeEnable ),
    .system_spi_0_io_data_1_read        (system_spi_0_io_data_1_read        ),
    .system_spi_0_io_data_1_write       (system_spi_0_io_data_1_write       ),
    .system_spi_0_io_data_2_writeEnable (                                   ),
    .system_spi_0_io_data_2_read        (                                   ),
    .system_spi_0_io_data_2_write       (                                   ),
    .system_spi_0_io_data_3_writeEnable (                                   ),
    .system_spi_0_io_data_3_read        (                                   ),
    .system_spi_0_io_data_3_write       (                                   ),
    .system_spi_0_io_ss                 (system_spi_0_io_ss                 ),
    //APB 0
    .io_apbSlave_0_PADDR                (apb_paddr                          ),
    .io_apbSlave_0_PSEL                 (apb_psel                           ),
    .io_apbSlave_0_PENABLE              (apb_penable                        ),
    .io_apbSlave_0_PREADY               (apb_pready                         ),
    .io_apbSlave_0_PWRITE               (apb_pwrite                         ),
    .io_apbSlave_0_PWDATA               (apb_pwdata                         ),
    .io_apbSlave_0_PRDATA               (apb_prdata                         ),
    .io_apbSlave_0_PSLVERROR            (apb_pslverror                      ),
    .userInterruptA                     (userInterruptA),
    .userInterruptB                     (userInterruptB),

`ifdef RISCV_SOFT_JTAG
    //Soft Jtag Tap
    .io_jtag_tms                        (io_jtag_tms                        ),
    .io_jtag_tdi                        (io_jtag_tdi                        ),
    .io_jtag_tdo                        (io_jtag_tdo                        ),
    .io_jtag_tck                        (io_jtag_tck                        )
`else
    //Hard Jtag Tap
    .jtagCtrl_tck                       (jtag_inst1_TCK                     ),
    .jtagCtrl_tdi                       (jtag_inst1_TDI                     ),
    .jtagCtrl_tdo                       (jtag_inst1_TDO                     ),
    .jtagCtrl_enable                    (jtag_inst1_SEL                     ),
    .jtagCtrl_capture                   (jtag_inst1_CAPTURE                 ),
    .jtagCtrl_shift                     (jtag_inst1_SHIFT                   ),
    .jtagCtrl_update                    (jtag_inst1_UPDATE                  ),
    .jtagCtrl_reset                     (jtag_inst1_RESET                   )
`endif
);


// ---------------------------------------------------------------------------
// Multimodal fusion subsystem. Stage-2 structure only: the three blocks below
// were extracted verbatim from this file so the top level wires subsystems
// instead of individual leaf modules. Register map, pinout and timing are
// unchanged. See src/fusion/ for each subsystem.
// ---------------------------------------------------------------------------
wire camera_reset=io_systemReset||!camera_pll_locked;

// --- Camera capture subsystem (CSI + ISP), cam_clk domain ------------------
wire video_sof,packed_valid,packed_complete,packed_bad,camera_end;
wire [15:0] video_seq;wire [16:0] camera_end_data;
wire [127:0] packed_data;wire [255:0] capture_stats;wire [31:0] setup_status;
wire [287:0] diagnostic_words;
fusion_camera_subsys u_camera_subsys(.clk(io_memoryClk),.cam_clk(i_mipi_rx_pclk),.reset(camera_reset),
 .capture_stats(capture_stats),.setup_status(setup_status),.diagnostic_words(diagnostic_words),
 .sof(video_sof),.frame_seq(video_seq),.packed_valid(packed_valid),.packed_data(packed_data),
 .packed_complete(packed_complete),.packed_bad(packed_bad),.end_valid(camera_end),.end_data(camera_end_data),
 .io_cam_sda_IN(io_cam_sda_IN),
 .io_cam_sda_OUT(io_cam_sda_OUT),
 .io_cam_sda_OE(io_cam_sda_OE),
 .io_cam_scl_OUT(io_cam_scl_OUT),
 .io_cam_scl_IN(io_cam_scl_IN),
 .io_cam_scl_OE(io_cam_scl_OE),
 .o_cam_rst_p(o_cam_rst_p),
 .i_cam_ck_LP_P_IN(i_cam_ck_LP_P_IN),
 .i_cam_ck_LP_N_IN(i_cam_ck_LP_N_IN),
 .o_cam_ck_HS_TERM(o_cam_ck_HS_TERM),
 .o_cam_ck_HS_ENA(o_cam_ck_HS_ENA),
 .i_cam_ck_CLKOUT(i_cam_ck_CLKOUT),
 .cam_d0_HS_IN(cam_d0_HS_IN),
 .cam_d0_LP_P_IN(cam_d0_LP_P_IN),
 .cam_d0_LP_N_IN(cam_d0_LP_N_IN),
 .cam_d0_HS_TERM(cam_d0_HS_TERM),
 .cam_d0_HS_ENA(cam_d0_HS_ENA),
 .cam_d0_RST(cam_d0_RST),
 .cam_d0_FIFO_RD(cam_d0_FIFO_RD),
 .cam_d0_FIFO_EMPTY(cam_d0_FIFO_EMPTY),
 .cam_d1_HS_IN(cam_d1_HS_IN),
 .cam_d1_LP_P_IN(cam_d1_LP_P_IN),
 .cam_d1_LP_N_IN(cam_d1_LP_N_IN),
 .cam_d1_HS_TERM(cam_d1_HS_TERM),
 .cam_d1_HS_ENA(cam_d1_HS_ENA),
 .cam_d1_RST(cam_d1_RST),
 .cam_d1_FIFO_RD(cam_d1_FIFO_RD),
 .cam_d1_FIFO_EMPTY(cam_d1_FIFO_EMPTY),
 .cam_d2_HS_IN(cam_d2_HS_IN),
 .cam_d2_LP_P_IN(cam_d2_LP_P_IN),
 .cam_d2_LP_N_IN(cam_d2_LP_N_IN),
 .cam_d2_HS_TERM(cam_d2_HS_TERM),
 .cam_d2_HS_ENA(cam_d2_HS_ENA),
 .cam_d2_RST(cam_d2_RST),
 .cam_d2_FIFO_RD(cam_d2_FIFO_RD),
 .cam_d2_FIFO_EMPTY(cam_d2_FIFO_EMPTY),
 .cam_d3_HS_IN(cam_d3_HS_IN),
 .cam_d3_LP_P_IN(cam_d3_LP_P_IN),
 .cam_d3_LP_N_IN(cam_d3_LP_N_IN),
 .cam_d3_HS_TERM(cam_d3_HS_TERM),
 .cam_d3_HS_ENA(cam_d3_HS_ENA),
 .cam_d3_RST(cam_d3_RST),
 .cam_d3_FIFO_RD(cam_d3_FIFO_RD),
 .cam_d3_FIFO_EMPTY(cam_d3_FIFO_EMPTY));

// --- Video DDR path (RGB565 triple buffer), clk + pixel_clk domains ---------
wire [15:0] published_seq;
wire [31:0] video_published,video_dropped,video_write_errors,video_read_errors,video_underflows;
wire frame_request,video_take,video_valid;wire [2:0] pixel_index;wire [23:0] video_rgb;
fusion_video_path u_video_path(.clk(io_memoryClk),.reset(camera_reset),.sof(video_sof),.frame_seq(video_seq),
 .in_valid(packed_valid),.in_data(packed_data),.complete(packed_complete),.malformed(packed_bad),
 .end_valid(camera_end),.end_data(camera_end_data),.pixel_clk(hdmi_tx_slow_clk),.frame_request(frame_request),
 .video_take(video_take),.pixel_index(pixel_index),.video_rgb(video_rgb),.video_valid(video_valid),
 .published(video_published),.published_seq(published_seq),.dropped(video_dropped),
 .write_errors(video_write_errors),.read_errors(video_read_errors),.underflows(video_underflows),
 .awaddr(axi_inter_s1_awaddr),
 .awlen(axi_inter_s1_awlen),
 .awvalid(axi_inter_s1_awvalid),
 .awready(axi_inter_s1_awready),
 .wdata(axi_inter_s1_wdata),
 .wstrb(axi_inter_s1_wstrb),
 .wlast(axi_inter_s1_wlast),
 .wvalid(axi_inter_s1_wvalid),
 .wready(axi_inter_s1_wready),
 .bresp(axi_inter_s1_bresp),
 .bvalid(axi_inter_s1_bvalid),
 .bready(axi_inter_s1_bready),
 .araddr(axi_inter_s1_araddr),
 .arlen(axi_inter_s1_arlen),
 .arvalid(axi_inter_s1_arvalid),
 .arready(axi_inter_s1_arready),
 .rdata(axi_inter_s1_rdata),
 .rresp(axi_inter_s1_rresp),
 .rlast(axi_inter_s1_rlast),
 .rvalid(axi_inter_s1_rvalid),
 .rready(axi_inter_s1_rready));

// --- Cross-domain status snapshots (frozen, ~1 kHz request) -----------------
wire [255:0] capture_cpu;wire [511:0] camera_cpu;wire [31:0] underflow_cpu;
reg [16:0] snapshot_divider=0;
always @(posedge i_peripheralClk)if(io_peripheralReset)snapshot_divider<=0;
 else snapshot_divider<=snapshot_divider==99999?0:snapshot_divider+1'b1;
snapshot_cdc #(.WIDTH(256)) cap_status(.src_clk(i_mipi_rx_pclk),.dst_clk(i_peripheralClk),.reset(camera_reset),
 .request(snapshot_divider==0),.src_data(capture_stats),.dst_data(capture_cpu),.done());
snapshot_cdc #(.WIDTH(512)) dma_status(.src_clk(io_memoryClk),.dst_clk(i_peripheralClk),.reset(camera_reset),
 .request(snapshot_divider==0),.src_data({32'd0,diagnostic_words,16'd0,published_seq,video_read_errors,video_write_errors,video_dropped,video_published,setup_status}),
 .dst_data(camera_cpu),.done());
snapshot_cdc #(.WIDTH(32)) pixel_status(.src_clk(hdmi_tx_slow_clk),.dst_clk(i_peripheralClk),.reset(camera_reset),
 .request(snapshot_divider==0),.src_data(video_underflows),.dst_data(underflow_cpu),.done());

// --- Camera status APB window (0xF8105000), CPU domain ----------------------
wire camera_sel=apb_paddr[15:8]==8'h50;
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
  12:camera_prdata=capture_cpu[159:128];
  13:camera_prdata=capture_cpu[191:160];
  14:camera_prdata=capture_cpu[223:192];
  15:camera_prdata=capture_cpu[255:224];
  default:if(apb_paddr[7:2]>=16&&apb_paddr[7:2]<25)camera_prdata=camera_cpu[192+(apb_paddr[7:2]-16)*32+:32];
 endcase
end
// APB mux: camera window (0xF8105000) wins, otherwise the sensor window.
wire [31:0] sensor_prdata;wire sensor_ready,sensor_error;
assign apb_prdata=camera_sel?camera_prdata:sensor_prdata;
assign apb_pready=camera_sel?1'b1:sensor_ready;
assign apb_pslverror=camera_sel?(apb_psel&&apb_penable&&(apb_pwrite||apb_paddr[1:0]!=0||
 !(apb_paddr[7:2]<25))):sensor_error;
tinyml_top#(
  .AXI_DW             (AXI_TINYML_DATA_WIDTH)
) u_tinyml_top(
   .clk              (i_sysclk),
   .reset            (io_systemReset),
   .cmd_valid        (cpu_customInstruction_cmd_valid),
   .cmd_ready        (cpu_customInstruction_cmd_ready),
   .cmd_function_id  (cpu_customInstruction_function_id),
   .cmd_inputs_0     (cpu_customInstruction_inputs_0),
   .cmd_inputs_1     (cpu_customInstruction_inputs_1),
   .cmd_int          (cpu_customInstruction_cmd_int),
   .rsp_valid        (cpu_customInstruction_rsp_valid),
   .rsp_ready        (cpu_customInstruction_rsp_ready),
   .rsp_outputs_0    (cpu_customInstruction_outputs_0),
   .m_axi_clk        (io_memoryClk),
   .m_axi_rstn       (!io_systemReset),
   .m_axi_awvalid    (axi_inter_s2_awvalid),
   .m_axi_awaddr     (axi_inter_s2_awaddr),
   .m_axi_awlen      (axi_inter_s2_awlen),
   .m_axi_awsize     (axi_inter_s2_awsize),
   .m_axi_awburst    (axi_inter_s2_awburst),
   .m_axi_awprot     (axi_inter_s2_awprot),
   .m_axi_awlock     (axi_inter_s2_awlock),
   .m_axi_awcache    (axi_inter_s2_awcache),
   .m_axi_awready    (axi_inter_s2_awready),
   .m_axi_wdata      (axi_inter_s2_wdata),
   .m_axi_wstrb      (axi_inter_s2_wstrb),
   .m_axi_wlast      (axi_inter_s2_wlast),
   .m_axi_wvalid     (axi_inter_s2_wvalid),
   .m_axi_wready     (axi_inter_s2_wready),
   .m_axi_bresp      (axi_inter_s2_bresp),
   .m_axi_bvalid     (axi_inter_s2_bvalid),
   .m_axi_bready     (axi_inter_s2_bready),
   .m_axi_arvalid    (axi_inter_s2_arvalid),
   .m_axi_araddr     (axi_inter_s2_araddr),
   .m_axi_arlen      (axi_inter_s2_arlen),
   .m_axi_arsize     (axi_inter_s2_arsize),
   .m_axi_arburst    (axi_inter_s2_arburst),
   .m_axi_arprot     (axi_inter_s2_arprot),
   .m_axi_arlock     (axi_inter_s2_arlock),
   .m_axi_arcache    (axi_inter_s2_arcache),
   .m_axi_arready    (axi_inter_s2_arready),
   .m_axi_rvalid     (axi_inter_s2_rvalid),
   .m_axi_rdata      (axi_inter_s2_rdata),
   .m_axi_rlast      (axi_inter_s2_rlast),
   .m_axi_rresp      (axi_inter_s2_rresp),
   .m_axi_rready     (axi_inter_s2_rready)
);

axi_interconnect_beta #(
    .S_COUNT                            (3                                                 ),
    .SLAVE_ASYN_ARRAY                   ({1'b0,1'b0,1'b0}                                  ),
    .S_AXI_DW_ARRAY                     ({AXI_TINYML_DATA_WIDTH,AXI_DATA_WIDTH,AXI_DATA_WIDTH}    ),
    .CB_DW                              (AXI_DATA_WIDTH                                    ),
    .M_AXI_DW                           (AXI_DATA_WIDTH                                    ),
    .ARB_MODE                           (1                                                 ),
    .FAMILY                             ("TITANIUM"                                        ),
    .RD_QUEUE_FIFO_RAM_STYLE            ("block_ram"                                       ),
    .RD_QUEUE_FIFO_DEPTH                (256                                               )
) u_axi_interconnect (
   //AXI slave interfaces - S0: Connected to RISC-V SoC; S1: Connected to DMA controller; S2: Connected to TinyML accelerator
   .s_axi_clk       ({io_memoryClk         , io_memoryClk        , io_memoryClk        }),
   .s_axi_rstn      ({!io_systemReset      , !io_systemReset     , !io_systemReset     }),
   .s_axi_awaddr     ({axi_inter_s2_awaddr , axi_inter_s1_awaddr , axi_inter_s0_awaddr }),
   .s_axi_awlen      ({axi_inter_s2_awlen  , axi_inter_s1_awlen  , axi_inter_s0_awlen  }),
   .s_axi_awvalid    ({axi_inter_s2_awvalid, axi_inter_s1_awvalid, axi_inter_s0_awvalid}),
   .s_axi_awready    ({axi_inter_s2_awready, axi_inter_s1_awready, axi_inter_s0_awready}),
   .s_axi_wdata      ({axi_inter_s2_wdata  , axi_inter_s1_wdata  , axi_inter_s0_wdata  }),
   .s_axi_wstrb      ({axi_inter_s2_wstrb  , axi_inter_s1_wstrb  , axi_inter_s0_wstrb  }),
   .s_axi_wlast      ({axi_inter_s2_wlast  , axi_inter_s1_wlast  , axi_inter_s0_wlast  }),
   .s_axi_wvalid     ({axi_inter_s2_wvalid , axi_inter_s1_wvalid , axi_inter_s0_wvalid }),
   .s_axi_wready     ({axi_inter_s2_wready , axi_inter_s1_wready , axi_inter_s0_wready }),
   .s_axi_bresp      ({axi_inter_s2_bresp  , axi_inter_s1_bresp  , axi_inter_s0_bresp  }),
   .s_axi_bvalid     ({axi_inter_s2_bvalid , axi_inter_s1_bvalid , axi_inter_s0_bvalid }),
   .s_axi_bready     ({axi_inter_s2_bready , axi_inter_s1_bready , axi_inter_s0_bready }),
   .s_axi_araddr     ({axi_inter_s2_araddr , axi_inter_s1_araddr , axi_inter_s0_araddr }),
   .s_axi_arlen      ({axi_inter_s2_arlen  , axi_inter_s1_arlen  , axi_inter_s0_arlen  }),
   .s_axi_arvalid    ({axi_inter_s2_arvalid, axi_inter_s1_arvalid, axi_inter_s0_arvalid}),
   .s_axi_arready    ({axi_inter_s2_arready, axi_inter_s1_arready, axi_inter_s0_arready}),
   .s_axi_rdata      ({axi_inter_s2_rdata  , axi_inter_s1_rdata  , axi_inter_s0_rdata  }),
   .s_axi_rresp      ({axi_inter_s2_rresp  , axi_inter_s1_rresp  , axi_inter_s0_rresp  }),
   .s_axi_rlast      ({axi_inter_s2_rlast  , axi_inter_s1_rlast  , axi_inter_s0_rlast  }),
   .s_axi_rvalid     ({axi_inter_s2_rvalid , axi_inter_s1_rvalid , axi_inter_s0_rvalid }),
   .s_axi_rready     ({axi_inter_s2_rready , axi_inter_s1_rready , axi_inter_s0_rready }),
   //AXI master interface - Connect to HyperRAM controller
   .m_axi_clk        (io_memoryClk),
   .m_axi_rstn       (!io_systemReset),

   .m_axi_awid       (axi_inter_m_awid),
   .m_axi_awaddr     (axi_inter_m_awaddr),
   .m_axi_awlen      (axi_inter_m_awlen),
   .m_axi_awsize     (axi_inter_m_awsize),
   .m_axi_awburst    (axi_inter_m_awburst),
   .m_axi_awlock     (axi_inter_m_awlock),
   .m_axi_awcache    (axi_inter_m_awcache),
   .m_axi_awprot     (axi_inter_m_awprot),
   .m_axi_awvalid    (axi_inter_m_awvalid),
   .m_axi_awready    (axi_inter_m_awready),
   .m_axi_wdata      (axi_inter_m_wdata),
   .m_axi_wstrb      (axi_inter_m_wstrb),
   .m_axi_wlast      (axi_inter_m_wlast),
   .m_axi_wvalid     (axi_inter_m_wvalid),
   .m_axi_wready     (axi_inter_m_wready),
   .m_axi_bresp      (axi_inter_m_bresp),
   .m_axi_bvalid     (axi_inter_m_bvalid),
   .m_axi_bready     (axi_inter_m_bready),
   .m_axi_arid       (axi_inter_m_arid),
   .m_axi_araddr     (axi_inter_m_araddr),
   .m_axi_arlen      (axi_inter_m_arlen),
   .m_axi_arsize     (axi_inter_m_arsize),
   .m_axi_arburst    (axi_inter_m_arburst),
   .m_axi_arlock     (axi_inter_m_arlock),
   .m_axi_arcache    (axi_inter_m_arcache),
   .m_axi_arprot     (axi_inter_m_arprot),
   .m_axi_arvalid    (axi_inter_m_arvalid),
   .m_axi_arready    (axi_inter_m_arready),
   .m_axi_rdata      (axi_inter_m_rdata),
   .m_axi_rresp      (axi_inter_m_rresp),
   .m_axi_rlast      (axi_inter_m_rlast),
   .m_axi_rvalid     (axi_inter_m_rvalid),
   .m_axi_rready     (axi_inter_m_rready)
);
// --- Sensor + display front end (APB 0xF8100000 window, HDMI page, TMDS) ----
fusion_sensor_front u_sensor_front(
 .sht_scl_IN(sht_scl_IN),.sht_sda_IN(sht_sda_IN),
 .sht_scl_OUT(sht_scl_OUT),.sht_scl_OE(sht_scl_OE),.sht_sda_OUT(sht_sda_OUT),.sht_sda_OE(sht_sda_OE),
 .ir_scl_IN(ir_scl_IN),.ir_sda_IN(ir_sda_IN),
 .ir_scl_OUT(ir_scl_OUT),.ir_scl_OE(ir_scl_OE),.ir_sda_OUT(ir_sda_OUT),.ir_sda_OE(ir_sda_OE),
 .cpu_clk(i_peripheralClk),.cpu_reset(io_peripheralReset),
 .pixel_clk(hdmi_tx_slow_clk),.pll_locked(hdmi_tx_locked),
 .paddr(apb_paddr),.psel(apb_psel&&!camera_sel),.penable(apb_penable),.pwrite(apb_pwrite),
 .pwdata(apb_pwdata),.prdata(sensor_prdata),.pready(sensor_ready),.pslverror(sensor_error),
 .frame_request(frame_request),.video_take(video_take),.pixel_index(pixel_index),.video_rgb(video_rgb),.video_valid(video_valid),
 .tmds_clk_o(tmds_clk_o),.tmds_data0_o(tmds_data0_o),.tmds_data1_o(tmds_data1_o),.tmds_data2_o(tmds_data2_o),
 .tmds_clk_TX_OE(tmds_clk_TX_OE),.tmds_data0_TX_OE(tmds_data0_TX_OE),.tmds_data1_TX_OE(tmds_data1_TX_OE),.tmds_data2_TX_OE(tmds_data2_TX_OE),
 .tmds_clk_TX_RST(tmds_clk_TX_RST),.tmds_data0_TX_RST(tmds_data0_TX_RST),.tmds_data1_TX_RST(tmds_data1_TX_RST),.tmds_data2_TX_RST(tmds_data2_TX_RST));
endmodule
