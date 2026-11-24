`timescale 1ns/1ps
module thermal_bilinear_tb;
 reg clk=0,cpu_clk=0,reset=1,request=0,we=0;
 always #5 clk=~clk;
 always #7 cpu_clk=~cpu_clk;
 reg [11:0] h=0,v=0;
 reg [10:0] address=0;reg [7:0] data=0;
 wire ack;wire [23:0] rgb;
 reg [447:0] record=448'd1;
 multimodal_panel dut(.clk(clk),.reset(reset),.h(h),.v(v),.ready(1'b0),.result(3'd0),.negative(1'b0),
  .t_bcd(20'd0),.h_bcd(20'd0),.cpu_clk(cpu_clk),.cpu_request(request),.cpu_record(record),.display_ack(ack),
  .image_we(we),.image_address(address),.image_data(data),.person_live(1'b0),.person_present(1'b0),.metrics(96'd0),.power_mode(3'd0),.rgb(rgb));
 integer pattern,x,y,i,xx,yy,a,b,c,d,n,checked=0;
 reg [7:0] reference[0:767];reg [23:0] expected;
 localparam [95:0] THERMAL_HEADER="THERMAL UPD ";
 function [23:0] color;input integer q;integer f;
 begin f=(q%64)*4;case(q/64)
  0:color={8'd0,8'(f),8'd255};1:color={8'd0,8'd255,8'(255-f)};
  2:color={8'(f),8'd255,8'd0};3:color={8'd255,8'(255-f),8'd0};
 endcase end endfunction
 task blank;
 begin
  repeat(5)@(posedge clk);
  @(negedge clk);h=0;v=1080;
  @(posedge clk);#1;
  if(ack!==request)$fatal(1,"thermal bank ACK missing");
 end endtask
 initial begin
  repeat(6)@(posedge clk);@(negedge clk);reset=0;
  for(pattern=0;pattern<3;pattern=pattern+1)begin
   for(i=0;i<768;i=i+1)begin
    case(pattern)
     0:reference[i]=(i%32)*5+(i/32)*3;
     1:reference[i]=(i==12*32+16)?255:0;
     2:reference[i]=((i%32+i/32)%2)?255:0;
    endcase
    @(negedge cpu_clk);we=1;address={!ack,10'(i)};data=reference[i];
   end
   @(negedge cpu_clk);we=0;request=~request;blank();
   for(y=0;y<384;y=y+1)begin
    for(x=-16;x<=512;x=x+1)begin
     @(negedge clk);h=1360+x;v=192+y;
     @(posedge clk);#1;
     // Panel output is delayed by one pixel from the input scan coordinate.
     if(x>=1)begin
      xx=(x-1)/16;yy=y/16;
      a=reference[yy*32+xx];b=reference[yy*32+(xx==31?xx:xx+1)];
      c=reference[(yy==23?yy:yy+1)*32+xx];d=reference[(yy==23?yy:yy+1)*32+(xx==31?xx:xx+1)];
      n=((a*(16-y%16)+c*(y%16))*(16-(x-1)%16)+(b*(16-y%16)+d*(y%16))*((x-1)%16)+128)/256;
      expected=color(n);
      if(rgb!==expected)$fatal(1,"bilinear pattern=%0d x=%0d y=%0d got=%h expected=%h",pattern,x-1,y,rgb,expected);
      checked=checked+1;
     end
    end
   end
  end
  @(negedge clk);h=1360;v=736;#1;
  for(i=0;i<12;i=i+1)begin
   h=1360+i*16;#1;
   if(dut.next_character!==THERMAL_HEADER[95-i*8-:8])$fatal(1,"thermal rate text alignment");
  end
  $display("PASS thermal bilinear: %0d pixels, gradient/hotspot/checker, edge clamps, bank swaps, pipeline alignment",checked);$finish;
 end
 initial begin #10000000;$fatal(1,"bilinear timeout");end
endmodule
