// Exact rounded hundredths, followed by sequential binary-to-BCD conversion.
// All logic runs on the HDMI pixel clock. The sensor publishes only once/second.
module sht30_values(input wire clk,reset,sample,
 input wire [2:0] status, input wire [15:0] raw_t,raw_h,
 output reg ready, output reg [2:0] result,
 output reg negative, output reg [19:0] t_bcd,h_bcd);
 reg [3:0] state;
 reg [31:0] dividend,quotient,t_product,h_product;
 reg [15:0] remainder,binary;
 reg [19:0] bcd,t_saved;
 reg [5:0] count;
 reg humidity,sign_saved;
 wire [16:0] trial={remainder,dividend[31]};
 wire subtract=trial>=17'd65535;
 wire [31:0] next_q={quotient[30:0],subtract};
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
   dividend<=0; quotient<=0; t_product<=0; h_product<=0; remainder<=0;
   binary<=0; bcd<=0; t_saved<=0; count<=0; humidity<=0; sign_saved<=0;
  end else begin
   ready<=0;
   case(state)
    0: if(sample) begin
     if(status!=1) begin result<=status; ready<=1; end
     else begin
      t_product<=raw_t*32'd17500;
      h_product<=raw_h*32'd10000;
      humidity<=0; state<=1;
     end
    end
    1: begin
     dividend<=t_product+32'd32767; quotient<=0; remainder<=0; count<=0; state<=2;
    end
    2: begin
     dividend<={dividend[30:0],1'b0}; quotient<=next_q;
     remainder<=subtract ? trial-17'd65535 : trial;
     if(count==31) state<=3; else count<=count+1'b1;
    end
    3: begin
     bcd<=0; count<=0;
     if(humidity) binary<=quotient[15:0];
     else begin
      sign_saved<=quotient<4500;
      binary<=quotient<4500 ? 16'd4500-quotient[15:0] : quotient[15:0]-16'd4500;
     end
     state<=4;
    end
    4: begin
     bcd<={adjusted[18:0],binary[15]}; binary<={binary[14:0],1'b0};
     if(count==15) state<=5; else count<=count+1'b1;
    end
    5: if(!humidity) begin
     t_saved<=bcd; humidity<=1; dividend<=h_product+32'd32767;
     quotient<=0; remainder<=0; count<=0; state<=2;
    end else begin
     t_bcd<=t_saved; h_bcd<=bcd; negative<=sign_saved;
     result<=1; ready<=1; state<=0;
    end
    default: state<=0;
   endcase
  end
 end
endmodule
