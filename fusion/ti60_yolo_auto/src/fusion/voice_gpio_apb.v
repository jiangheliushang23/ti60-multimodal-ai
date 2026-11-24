// Minimal CPU-driven SYN6658 mode-0 pins. No SPI engine or frame storage.
module voice_gpio_apb(
    input wire clk,reset,
    input wire [7:0] paddr,
    input wire psel,penable,pwrite,
    input wire [31:0] pwdata,
    output reg [31:0] prdata,
    output wire pslverror,
    output wire spi_clk,spi_mosi,spi_cs_n,
    input wire spi_miso,module_busy
);
reg [2:0] pins;
(* async_reg="true",syn_preserve=1 *) reg miso_meta,miso_sync,busy_meta,busy_sync;
wire access=psel&&penable;
assign {spi_cs_n,spi_mosi,spi_clk}=pins;
assign pslverror=access&&(paddr[1:0]!=0 ||
    (pwrite ? (paddr!=8'h04 || pwdata[31:3]!=0) :
              (paddr!=8'h00 && paddr!=8'h04 && paddr!=8'h08)));
always @* begin
    prdata=0;
    case(paddr)
      8'h00: prdata=32'h56475031; // VGP1; incompatible with autonomous VSP2.
      8'h04: prdata={29'b0,pins};
      8'h08: prdata={30'b0,busy_sync,miso_sync};
      default: prdata=0;
    endcase
end
always @(posedge clk) begin
    if(reset) begin
        pins<=3'b100; // CLK=0, MOSI=0, CS_N=1.
        miso_meta<=1; miso_sync<=1; busy_meta<=1; busy_sync<=1;
    end else begin
        miso_meta<=spi_miso; miso_sync<=miso_meta;
        busy_meta<=module_busy; busy_sync<=busy_meta;
        if(access&&pwrite&&!pslverror) pins<=pwdata[2:0];
    end
end
endmodule
