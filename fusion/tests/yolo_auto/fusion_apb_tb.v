`timescale 1ns/1ps
module fusion_apb_tb;
 reg clk=0,reset=1;always #5 clk=~clk;
 reg [15:0] paddr=0;reg psel=0,penable=0,pwrite=0;reg [31:0] pwdata=0;
 wire [31:0] prdata;wire pready,pslverror;
 reg slave_sda=0,slave_scl=0;wire scl_low,sda_low;
 wire scl=!(scl_low||slave_scl),sda=!(sda_low||slave_sda);
 reg sht_sample=0;reg [75:0] sht_snapshot=0;
 reg display_ack=0,display_ready=0;wire display_request;
 wire [447:0] display_record;wire image_we;wire [10:0] image_address;wire [7:0] image_data;
 fusion_apb #(.CLOCK_HZ(100000),.I2C_TICK_CYCLES(8),.I2C_TIMEOUT_TICKS(100)) dut(
 .clk(clk),.reset(reset),.paddr(paddr),.psel(psel),.penable(penable),.pwrite(pwrite),.pwdata(pwdata),
 .prdata(prdata),.pready(pready),.pslverror(pslverror),.scl_in(scl),.sda_in(sda),
 .scl_low(scl_low),.sda_low(sda_low),.sht_sample(sht_sample),.sht_snapshot(sht_snapshot),
 .display_ack(display_ack),.display_ready(display_ready),.display_request(display_request),
 .display_record(display_record),.ai_ack(1'b0),.ai_request(),.ai_record(),.image_we(image_we),.image_address(image_address),.image_data(image_data));
 `include "i2c_slave_tasks.vh"
 task access(input wr,input [15:0] a,input [31:0] d,input expected_error,output [31:0] q);
 begin
  @(negedge clk);psel=1;penable=0;paddr=a;pwrite=wr;pwdata=d;
  @(negedge clk);penable=1;#1;
  if(!pready||pslverror!==expected_error)$fatal(1,"APB handshake a=%h error=%b expected=%b",a,pslverror,expected_error);
  q=prdata;@(negedge clk);psel=0;penable=0;pwrite=0;
 end endtask
 reg [31:0] q,t0;reg [447:0] frozen;integer i,writes=0,n;
 always @(negedge clk)if(image_we)begin
  writes=writes+1;
  if(writes==1&&(image_address!=1024||image_data!=8'h35))$fatal(1,"First inactive bank");
  if(writes==2&&(image_address!=767||image_data!=8'hca))$fatal(1,"Second inactive bank");
 end
 initial begin
  repeat(10)@(negedge clk);reset=0;display_ready=1;
  access(0,0,0,0,q);if(q!=32'h4d4d4631)$fatal(1,"ID");
  access(0,16'h1000,0,0,q);if(q!=32'h46555331)$fatal(1,"Display ID");
  access(0,16'h1004,0,0,q);if(q!=4)$fatal(1,"ready");
  access(0,8,0,0,t0);repeat(200)@(negedge clk);
  access(0,8,0,0,q);if(q-t0<2)$fatal(1,"ms timer");
  access(1,0,1,1,q);access(0,16'h5000,0,1,q);access(0,16'h4001,0,1,q);
  access(0,16'h6000,0,1,q);access(1,16'h4000,1,1,q);
  @(negedge clk);sht_snapshot={3'd1,1'b1,20'h01234,20'h05678,16'h1234,16'habcd};sht_sample=1;
  @(negedge clk);sht_sample=0;
  access(0,16'h2000,0,0,q);if(q!=1)$fatal(1,"SHT result");
  access(0,16'h2004,0,0,q);if(q!=32'h1234abcd)$fatal(1,"SHT raw");
  access(0,16'h2008,0,0,q);if(q!=32'h80001234)$fatal(1,"SHT signed BCD");
  access(0,16'h2010,0,0,q);if(q!=32'h5678)$fatal(1,"SHT RH");
  access(0,16'h2014,0,0,q);if(q!=1)$fatal(1,"SHT seq");
  for(i=0;i<14;i=i+1)access(1,16'h1020+4*i,32'h12340000+i,0,q);
  access(0,16'h1020,0,0,q);if(q!=0)$fatal(1,"staging leaked");
  access(1,16'h6000,8'h35,0,q);access(1,16'h1018,1,0,q);
  if(!display_request)$fatal(1,"commit request");frozen=display_record;
  for(i=0;i<14;i=i+1)if(display_record[i*32+:32]!==32'h12340000+i)$fatal(1,"torn record");
  access(1,16'h1020,99,1,q);access(1,16'h6000,99,1,q);access(1,16'h1018,1,1,q);
  if(display_record!==frozen||writes!=1)$fatal(1,"busy writes changed data");
  display_ack=1;repeat(5)@(negedge clk);
  access(1,16'h6bfc,8'hca,0,q);
  access(1,16'h300c,0,0,q);access(1,16'h3000,3,1,q);
  access(1,16'h300c,833,0,q);access(1,16'h3000,3,1,q);
  access(1,16'h3004,16'h0400,0,q);access(1,16'h300c,8,0,q);
  access(1,16'h3000,3,0,q);access(1,16'h3004,16'h800d,1,q);
  access(1,16'h3000,3,1,q);
  q=1;while(q[0])access(0,16'h3000,0,0,q);
  access(0,16'h3010,0,0,q);if(q!=1)$fatal(1,"I2C result");
  for(i=0;i<8;i=i+1)begin
   access(0,16'h4000+4*i,0,0,q);if(q!=(16'h5a5a^i))$fatal(1,"buffer index %d q=%h",i,q);
  end
  access(0,16'h3018,0,0,q);if(q!=1)$fatal(1,"completion not single pulse");
  access(0,16'h301c,0,0,q);if(q==0)$fatal(1,"completion timestamp");
  $display("PASS fusion APB: IDs, timer, address rejection, SHT snapshot, atomic display, busy rejection, bank ownership, I2C burst buffer and timestamp");$finish;
 end
 reg [15:0] value;
 initial begin
  wait_start;receive(8'h66,0);receive(8'h04,0);receive(8'h00,0);wait_start;receive(8'h67,0);
  for(n=0;n<8;n=n+1)begin value=16'h5a5a^n;transmit(value[15:8],0);transmit(value[7:0],n==7);end
  wait_stop;
 end
 initial begin #2000000;$fatal(1,"APB timeout");end
endmodule
