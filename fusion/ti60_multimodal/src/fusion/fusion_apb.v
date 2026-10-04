// Fusion APB window 0xF8100000. Clock 100 MHz; no second CPU or program RAM.
module fusion_apb #(
 parameter integer CLOCK_HZ=100000000,I2C_TICK_CYCLES=100,I2C_TIMEOUT_TICKS=10000
)(
 input wire clk,reset,input wire [15:0] paddr,
 input wire psel,penable,pwrite,input wire [31:0] pwdata,
 output reg [31:0] prdata,output wire pready,pslverror,
 input wire scl_in,sda_in,output wire scl_low,sda_low,
 input wire sht_sample,input wire [75:0] sht_snapshot,
 input wire display_ack,display_ready,output reg display_request,
 output reg [447:0] display_record,
 output reg image_we,output reg [10:0] image_address,output reg [7:0] image_data);
 reg [31:0] milliseconds,ms_divider;
 reg [31:0] record[0:13];
 reg [75:0] sht_record;
 reg [31:0] sht_sequence,sht_time,display_sequence;
 (* async_reg="true",syn_preserve=1 *) reg [2:0] ack_sync,ready_sync;
 wire display_busy=display_request!=ack_sync[2];
 reg bus_start,bus_read;
 reg [15:0] bus_address,bus_write;
 reg [9:0] bus_words;
 wire bus_busy,bus_done,bus_word;
 wire [2:0] bus_result;
 wire [15:0] bus_data;
 wire [9:0] bus_index;
 reg [15:0] buffer[0:1023],buffer_q;
 reg [31:0] bus_sequence,bus_finished_ms;
 mlx90640_bus #(.TICK_CYCLES(I2C_TICK_CYCLES),.TIMEOUT_TICKS(I2C_TIMEOUT_TICKS)) bus(
  .clk(clk),.reset(reset),.scl_in(scl_in),.sda_in(sda_in),.scl_low(scl_low),.sda_low(sda_low),
  .start(bus_start),.read_op(bus_read),.reg_addr(bus_address),.write_data(bus_write),.read_words(bus_words),
  .busy(bus_busy),.done(bus_done),.result(bus_result),.read_data(bus_data),.word_valid(bus_word),.word_index(bus_index));
 always @(posedge clk)begin
  buffer_q<=buffer[paddr[11:2]];
  if(bus_word)buffer[bus_index]<=bus_data;
 end
 wire record_sel=paddr>=16'h1020 && paddr<16'h1058;
 wire image_sel=paddr>=16'h6000 && paddr<16'h6c00;
 wire buffer_sel=paddr>=16'h4000 && paddr<16'h4d00;
 wire command_sel=paddr==16'h3000;
 wire config_sel=paddr==16'h3004 || paddr==16'h3008 || paddr==16'h300c;
 wire commit_sel=paddr==16'h1018;
 wire writable=record_sel||image_sel||config_sel||command_sel||commit_sel;
 wire scalar_sel=paddr==0||paddr==4||paddr==8||paddr==16'h1000||paddr==16'h1004||
  paddr==16'h1010||commit_sel||paddr==16'h2000||paddr==16'h2004||paddr==16'h2008||
  paddr==16'h200c||paddr==16'h2010||paddr==16'h2014||command_sel||config_sel||
  paddr==16'h3010||paddr==16'h3014||paddr==16'h3018||paddr==16'h301c;
 wire invalid=paddr[1:0]!=0||!(scalar_sel||record_sel||image_sel||buffer_sel)||
  (pwrite && (!writable || ((record_sel||image_sel||commit_sel)&&display_busy) ||
    ((config_sel||command_sel)&&(bus_busy||bus_start)) ||
    (command_sel&&pwdata[0]&&(bus_words==0||bus_words>832)))) ||
  (!pwrite && image_sel);
 assign pready=1'b1;
 assign pslverror=psel&&penable&&invalid;
 wire write_access=psel&&penable&&pwrite&&!invalid;
 always @*begin
  prdata=0;
  if(buffer_sel)prdata={16'd0,buffer_q};
  else if(record_sel)prdata=display_record[((paddr-16'h1020)>>2)*32+:32];
  else case(paddr)
   16'h0000:prdata=32'h4d4d4631; // MMF1
   16'h0004:prdata=32'h00010000;
   16'h0008:prdata=milliseconds;
   16'h1000:prdata=32'h46555331; // FUS1
   16'h1004:prdata={29'd0,ready_sync[2],ack_sync[2],display_busy};
   16'h1010:prdata=display_sequence;
   16'h2000:prdata={29'd0,sht_record[75:73]};
   16'h2004:prdata=sht_record[31:0];
   16'h2008:prdata={sht_record[72],11'd0,sht_record[71:52]};
   16'h200c:prdata=sht_time;
   16'h2010:prdata={12'd0,sht_record[51:32]};
   16'h2014:prdata=sht_sequence;
   16'h3000:prdata={31'd0,bus_busy|bus_start};
   16'h3004:prdata={16'd0,bus_address};
   16'h3008:prdata={16'd0,bus_write};
   16'h300c:prdata={22'd0,bus_words};
   16'h3010:prdata={29'd0,bus_result};
   16'h3014:prdata=milliseconds;
   16'h3018:prdata=bus_sequence;
   16'h301c:prdata=bus_finished_ms;
   default:begin end
  endcase
 end
 integer i;
 always @(posedge clk)begin
  if(reset)begin
   milliseconds<=0;ms_divider<=0;sht_record<=0;sht_sequence<=0;sht_time<=0;
   ack_sync<=0;ready_sync<=0;display_request<=0;display_record<=0;display_sequence<=0;
   bus_start<=0;bus_read<=1;bus_address<=0;bus_write<=0;bus_words<=1;
   bus_sequence<=0;bus_finished_ms<=0;image_we<=0;image_address<=0;image_data<=0;
   for(i=0;i<14;i=i+1)record[i]<=0;
  end else begin
   if(ms_divider==CLOCK_HZ/1000-1)begin ms_divider<=0;milliseconds<=milliseconds+1'b1;end
   else ms_divider<=ms_divider+1'b1;
   ack_sync<={ack_sync[1:0],display_ack};ready_sync<={ready_sync[1:0],display_ready};
   bus_start<=0;image_we<=0;
   if(sht_sample)begin sht_record<=sht_snapshot;sht_sequence<=sht_sequence+1'b1;sht_time<=milliseconds;end
   // done is a pulse in mlx90640_bus FINISH, followed by IDLE clearing it.
   if(bus_done)begin bus_sequence<=bus_sequence+1'b1;bus_finished_ms<=milliseconds;end
   if(write_access)begin
    if(record_sel)record[(paddr-16'h1020)>>2]<=pwdata;
    if(image_sel)begin image_we<=1;image_address<={!display_request,paddr[11:2]};image_data<=pwdata[7:0];end
    if(commit_sel)begin
     for(i=0;i<14;i=i+1)display_record[i*32+:32]<=record[i];
     display_request<=!display_request;display_sequence<=display_sequence+1'b1;
    end
    case(paddr)
     16'h3000:begin bus_start<=pwdata[0];bus_read<=pwdata[1];end
     16'h3004:bus_address<=pwdata[15:0];
     16'h3008:bus_write<=pwdata[15:0];
     16'h300c:bus_words<=pwdata[9:0];
     default:begin end
    endcase
   end
  end
 end
endmodule
