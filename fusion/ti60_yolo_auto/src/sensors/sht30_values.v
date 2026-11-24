// Exact rounded hundredths and sequential binary-to-BCD conversion.
// N=raw*k+32767=H*65535+(H+L), H=N[31:16], L=N[15:0], k<=17500.
// H+L<2*65535, so floor(N/65535)=H+(H+L>=65535), without a divider.
module sht30_values(input wire clk,reset,sample,
 input wire [2:0] status, input wire [15:0] raw_t,raw_h,
 output reg ready, output reg [2:0] result,
 output reg negative, output reg [19:0] t_bcd,h_bcd);
 reg [1:0] state;
 reg [31:0] t_product,h_product;
 reg [15:0] binary;
 reg [19:0] bcd,t_saved;
 reg [3:0] count;
 reg humidity,sign_saved;
 wire [16:0] t_fold={1'b0,t_product[31:16]}+{1'b0,t_product[15:0]};
 wire [16:0] h_fold={1'b0,h_product[31:16]}+{1'b0,h_product[15:0]};
 wire [15:0] t_q=t_product[31:16]+(t_fold>=17'd65535);
 wire [15:0] h_q=h_product[31:16]+(h_fold>=17'd65535);
 reg [19:0] adjusted;
 integer k;
 always @* begin
  adjusted=bcd;
  for(k=0;k<5;k=k+1)
   if(bcd[k*4+:4]>=5) adjusted[k*4+:4]=bcd[k*4+:4]+4'd3;
 end
 always @(posedge clk) begin
  if(reset) begin
   state<=0; ready<=0; result<=0; negative<=0; t_bcd<=0; h_bcd<=0;
   t_product<=0; h_product<=0;
   binary<=0; bcd<=0; t_saved<=0; count<=0; humidity<=0; sign_saved<=0;
  end else begin
   ready<=0;
   case(state)
    0: if(sample) begin
     if(status!=1) begin result<=status; ready<=1; end
     else begin
      t_product<=raw_t*32'd17500+32'd32767;
      h_product<=raw_h*32'd10000+32'd32767;
      humidity<=0; state<=1;
     end
    end
    1: begin
     bcd<=0; count<=0;
     sign_saved<=t_q<4500;
     binary<=t_q<4500 ? 16'd4500-t_q : t_q-16'd4500;
     state<=2;
    end
    2: begin
     bcd<={adjusted[18:0],binary[15]}; binary<={binary[14:0],1'b0};
     if(count==15) state<=3; else count<=count+1'b1;
    end
    3: if(!humidity) begin
     t_saved<=bcd; humidity<=1; binary<=h_q; bcd<=0; count<=0; state<=2;
    end else begin
     t_bcd<=t_saved; h_bcd<=bcd; negative<=sign_saved;
     result<=1; ready<=1; state<=0;
    end
    default: state<=0;
   endcase
  end
 end
endmodule
