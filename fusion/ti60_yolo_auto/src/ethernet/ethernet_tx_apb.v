// Compact raw Ethernet transmitter. CPU supplies destination MAC, IPv4/UDP,
// padding and FCS in a bounded 2 KiB packet RAM. No camera/HDMI backpressure.
// The TCAM1601 application protocol is retained from camera_web_monitor_hires.
module ethernet_tx_apb(
 input wire camera_clk,camera_reset,camera_vs,camera_de,input wire [47:0] camera_rgb,input wire [31:0] time_gray,
 input wire clk,reset,input wire [15:0] paddr,input wire psel,penable,pwrite,
 input wire [31:0] pwdata,output reg [31:0] prdata,output wire pslverror,
 input wire rxc,input wire [3:0] rxd_hi_i,rxd_lo_i,input wire rx_dv_HI,rx_dv_LO,
 output wire [3:0] txd_hi_o,txd_lo_o,
 output wire tx_en_o_HI,tx_en_o_LO,txc_hi_o,txc_lo_o,
 output wire mdc_o,mdio_o,mdio_oe,phy_rst_n,input wire mdio_i
);
 reg stream_enable;
 reg [31:0] packet[0:511];
 reg [10:0] length;
 reg request;
 reg ack;
 (* async_reg="true" *) reg [2:0] ack_sync,req_sync;
 wire busy=request!=ack_sync[2];
 wire buffer_sel=paddr[11];
 wire http_sel=(paddr[11:5]==0&&paddr[4])||(!paddr[11]&&(paddr[10]||paddr[9]));
 wire [31:0] http_prdata;
 ethernet_http_rx http_rx(.clk(clk),.reset(reset),.rxc(rxc),.rxd_hi_i(rxd_hi_i),.rxd_lo_i(rxd_lo_i),
  .rx_dv_HI(rx_dv_HI),.rx_dv_LO(rx_dv_LO),.paddr(paddr[11:0]),.psel(psel&&http_sel),
  .penable(penable),.pwrite(pwrite),.pwdata(pwdata),.prdata(http_prdata));
 wire valid_address=buffer_sel||paddr[11:0]==0||paddr[11:0]==4||paddr[11:0]==8||paddr[11:0]==12;
 assign pslverror=psel&&penable&&((!valid_address&&!http_sel)||paddr[1:0]!=0||
   (pwrite&&http_sel&&paddr[11:0]!=12'h01c)||
   (pwrite&&!http_sel&&paddr[11:0]!=12&&(busy||(!buffer_sel&&(paddr[11:0]!=8||pwdata<64||pwdata>1536)))));
 always @(posedge clk) begin
  if(reset)begin stream_enable<=0;request<=0;length<=0;ack_sync<=0;end
  else begin
   ack_sync<={ack_sync[1:0],ack};
   if(psel&&penable&&pwrite&&!pslverror&&!http_sel)begin
    if(paddr[11:0]==12)stream_enable<=pwdata[0];
    else if(buffer_sel)packet[paddr[10:2]]<=pwdata;
    else begin length<=pwdata[10:0];request<=!request;end
   end
  end
 end
 // Divided receive-clock counter: software measures rate without assuming link
 // is gigabit. At 100/10 Mbps it skips transmission, leaving all old tasks live.
 reg [27:0] rx_count;
 // Register Gray code in its source domain before synchronizing it. A
 // combinational binary-to-Gray bus can glitch during a counter carry.
 reg [15:0] rx_gray;
 (* async_reg="true" *) reg [15:0] rx_meta,rx_sync;
 always @(posedge rxc or posedge reset)
  if(reset)begin rx_count<=0;rx_gray<=0;end
  else begin rx_count<=rx_count+1'b1;rx_gray<=(rx_count[27:12]>>1)^rx_count[27:12];end
 always @(posedge clk)begin
  if(reset)begin rx_meta<=0;rx_sync<=0;end
  else begin rx_meta<=rx_gray;rx_sync<=rx_meta;end
 end
 always @*begin
  prdata=http_sel?http_prdata:0;
  case(paddr[11:0])
   0:prdata=32'h454e3031; // EN01, independent of the unchanged YAU9 feature ID.
   4:prdata={15'd0,rx_sync, busy};
   8:prdata={21'd0,length};
   12:prdata=32'h43533634; // CS64: autonomous 640x360 RGB565 stream.
  endcase
 end
 reg [1:0] state;
 reg [10:0] position;
 reg [3:0] count;
 reg [31:0] word_q;
 reg [7:0] tx_data;
 reg tx_enable;
 wire [10:0] next_position=position+1'b1;
 wire stream_ready;wire [7:0] stream_data;reg camera_packet;
 wire [10:0] stream_position=state==2?next_position:11'd0;
 ethernet_camera_stream camera_stream(.reset(camera_reset),.cam_clk(camera_clk),.vs(camera_vs),.de(camera_de),
  .rgb(camera_rgb),.time_gray(time_gray),.tx_clk(rxc),.enable(stream_enable),
  .tx_position(stream_position),.tx_active(state==2&&camera_packet),
  .tx_done(state==3&&count==11&&camera_packet),.ready(stream_ready),.data(stream_data),.sent_packets(),.dropped_frames());
 // First word is prefetched during preamble. Every later word is prefetched
 // on the last byte of its predecessor. No combinational RAM read is required.
 always @(posedge rxc)word_q<=packet[state==2?next_position[10:2]:9'd0];
 always @(posedge rxc or posedge reset)begin
  if(reset)begin camera_packet<=0;req_sync<=0;ack<=0;state<=0;position<=0;count<=0;tx_data<=0;tx_enable<=0;end
  else begin
   req_sync<={req_sync[1:0],request};
   case(state)
    0:begin
     tx_enable<=0;
     if(req_sync[2]!=ack)begin camera_packet<=0;state<=1;count<=0;position<=0;end
     else if(stream_ready)begin camera_packet<=1;state<=1;count<=0;position<=0;end
    end
    1:begin
     tx_enable<=1;tx_data<=count==7?8'hd5:8'h55;
     if(count==7)begin state<=2;position<=0;end else count<=count+1'b1;
    end
    2:begin
     tx_enable<=1;
     if(camera_packet)tx_data<=stream_data;else case(position[1:0])
      0:tx_data<=word_q[7:0];1:tx_data<=word_q[15:8];
      2:tx_data<=word_q[23:16];3:tx_data<=word_q[31:24];
     endcase
     if(position==(camera_packet?11'd1517:length-1'b1))begin state<=3;count<=0;end
     else position<=next_position;
    end
    3:begin
     tx_enable<=0;
     if(count==11)begin if(!camera_packet)ack<=req_sync[2];state<=0;end else count<=count+1'b1;
    end
   endcase
  end
 end
 assign txd_hi_o=tx_data[3:0];assign txd_lo_o=tx_data[7:4];
 assign tx_en_o_HI=tx_enable;assign tx_en_o_LO=tx_enable;
 assign txc_hi_o=1'b1;assign txc_lo_o=1'b0;
 // The accepted source design uses the PHY's power-on straps, without MDIO.
 assign phy_rst_n=1'b1;assign mdc_o=1'b0;assign mdio_o=1'b0;assign mdio_oe=1'b0;
endmodule
