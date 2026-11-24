`timescale 1ns/1ps
module voice_gpio_tb;
reg clk=0;always #5 clk=~clk;
reg reset=1,sel=0,en=0,wr=0,miso=1,busy=1;
reg [7:0] addr=0;reg [31:0] data=0;
wire [31:0] out;wire error,sck,mosi,cs;
voice_gpio_apb dut(.clk(clk),.reset(reset),.paddr(addr),.psel(sel),.penable(en),
 .pwrite(wr),.pwdata(data),.prdata(out),.pslverror(error),
 .spi_clk(sck),.spi_mosi(mosi),.spi_cs_n(cs),.spi_miso(miso),.module_busy(busy));
task write;
 input [7:0] a;input [31:0] d;input bad;
 begin
  @(negedge clk);sel=1;en=1;wr=1;addr=a;data=d;#1;
  if(error!==bad)$fatal(1,"APB write error mismatch");
  @(negedge clk);sel=0;en=0;wr=0;
 end
endtask
initial begin
 repeat(3)@(negedge clk);reset=0;
 #1;if({cs,mosi,sck}!==3'b100)$fatal(1,"reset output");
 addr=0;#1;if(out!==32'h56475031)$fatal(1,"VGP1 identity");
 write(4,6,0);#1;if({cs,mosi,sck}!==3'b110)$fatal(1,"UART idle");
 write(4,4,0);#1;if({cs,mosi,sck}!==3'b100)$fatal(1,"UART start/zero");
 write(4,6,0);write(4,32'h100,1);write(0,0,1);write(5,0,1);
 #1;if({cs,mosi,sck}!==3'b110)$fatal(1,"invalid writes changed output");
 @(negedge clk);miso=0;busy=0;repeat(3)@(negedge clk);
 addr=8;#1;if(out!==0)$fatal(1,"synchronized low inputs");
 @(negedge clk);miso=1;busy=1;repeat(3)@(negedge clk);
 #1;if(out!==3)$fatal(1,"synchronized high inputs");
 sel=1;en=1;addr=12;#1;if(error!==1)$fatal(1,"invalid read");
 sel=0;#1;if(error!==0)$fatal(1,"unselected error");
 $display("VOICE_GPIO_PASS identity=VGP1 uart_pins=A12_B12 cases=12");$finish;
end
initial begin #10000;$fatal(1,"timeout");end
endmodule
