// One CRC-checked receive slot. The CPU owns the slot until POP; unpublished
// bytes are never visible. Existing UDP/video transmitter and address map stay.
module ethernet_http_rx(
 input wire clk,reset,rxc,input wire [3:0] rxd_hi_i,rxd_lo_i,
 input wire rx_dv_HI,rx_dv_LO,input wire [11:0] paddr,
 input wire psel,penable,pwrite,input wire [31:0] pwdata,
 output reg [31:0] prdata);
 function [31:0] crc_byte;
  input [31:0] c;input [7:0] d;integer k;reg [31:0] v;
  begin v=c^{24'b0,d};for(k=0;k<8;k=k+1)v=v[0]?(v>>1)^32'hedb88320:v>>1;crc_byte=v;end
 endfunction
 (* async_reg="true" *) reg [1:0] net_reset;
 always @(posedge rxc or posedge reset)
  if(reset)net_reset<=0;else net_reset<={net_reset[0],1'b1};
 // Efinity resync DDIO: align the previous rising nibble with the current
 // falling nibble, exactly as in the source project's board-tested adapter.
 reg [3:0] rising;reg rising_dv;reg [7:0] data;reg dv,er;
 always @(posedge rxc)begin
  rising<=rxd_hi_i;rising_dv<=rx_dv_HI;
  data<={rxd_lo_i,rising};dv<=rx_dv_LO;er<=rx_dv_LO^rising_dv;
 end
 (* syn_ramstyle="block_ram" *) reg [31:0] packet[0:511];
 reg written,consumed;
 (* async_reg="true" *) reg wm,ws,rm,rs;
 reg [10:0] frame_length,length;
 wire ready=ws!=consumed;
 wire full=written!=rs;
 wire [8:0] address=paddr[10:2]-9'h080;
 reg [31:0] q;
 always @(posedge clk)begin
  if(psel&&!pwrite&&paddr>=12'h200&&paddr<12'h800)q<=packet[address];
  length<=frame_length;
 end
 always @(posedge clk or posedge reset)begin
  if(reset)begin wm<=0;ws<=0;consumed<=0;end
  else begin
   wm<=written;ws<=wm;
   if(psel&&penable&&pwrite&&paddr==12'h01c&&pwdata[0]&&ready)consumed<=!consumed;
  end
 end
 always @*begin
  prdata=0;
  if(paddr>=12'h200&&paddr<12'h800)prdata=q;
  else case(paddr)
   12'h010:prdata=32'h48545031; // HTP1: bounded RX + existing shared TX
   12'h014:prdata={31'd0,ready};
   12'h018:prdata={21'd0,length};
  endcase
 end
 reg [1:0] state;reg [3:0] pre;reg [10:0] count;
 reg [31:0] crc;reg bad;
 reg [23:0] packed_bytes;
 always @(posedge rxc)if(net_reset[1]&&state==2&&dv&&count<1518)begin
  packed_bytes<={data,packed_bytes[23:8]};
  if(count[1:0]==3)packet[count[10:2]]<={data,packed_bytes};
 end
 always @(posedge rxc or negedge net_reset[1])begin
  if(!net_reset[1])begin rm<=0;rs<=0;written<=0;state<=0;pre<=0;count<=0;crc<=~32'd0;bad<=0;end
  else begin
   rm<=consumed;rs<=rm;
   case(state)
    0:if(dv)begin
     if(!full&&data==8'h55&&!er)begin state<=1;pre<=1;end else state<=3;
    end
    1:if(!dv)state<=0;
      else if(data==8'h55&&!er&&pre<15)pre<=pre+1'b1;
      else if(data==8'hd5&&!er&&pre>=7)begin state<=2;count<=0;crc<=~32'd0;bad<=0;end
      else state<=3;
    2:if(dv)begin
     if(count<2047)count<=count+1'b1;
     if(count>=1518||er)bad<=1;
     crc<=crc_byte(crc,data);
    end else begin
     if(!bad&&count>=64&&count<=1518&&crc==32'hdebb20e3)begin
      frame_length<=count-4;written<=!written;
     end
     state<=0;
    end
    3:if(!dv)state<=0;
   endcase
  end
 end
endmodule
