module sc431hai_setup #(
    parameter integer CLK_PER_MS=25000,
    parameter integer I2C_TICK=250,
    parameter integer TIMEOUT_TICKS=1000
)(
    input wire clk, reset, scl_in, sda_in,
    output wire scl_low, sda_low,
    output reg cam_enable, id_ok, config_ok, stream_set, finished,
    output reg [2:0] error_code,
    output reg [7:0] command_index,
    output wire [287:0] diagnostic_words,
    output reg diagnostic_valid,
    input wire rt_start, rt_read,
    input wire [15:0] rt_address,
    input wire [7:0] rt_data,
    output wire rt_busy,
    output reg rt_done,
    output reg [2:0] rt_result,
    output reg [7:0] rt_read_data
);
    `include "sc_sequence.vh"
    localparam BOOT=0, FETCH=1, WAIT_BUS=2, GAP=3, DELAY=4, HALT=5, RT_WAIT=6;
    reg [2:0] state;
    localparam CYCLE_BITS=CLK_PER_MS>1?$clog2(CLK_PER_MS):1;
    reg [CYCLE_BITS-1:0] cycles;
    reg [15:0] elapsed_ms;
    reg bus_start;
    wire [25:0] command = sequence_word(command_index);
    wire [1:0] op = command[25:24];
    wire [15:0] address = command[23:8];
    wire [7:0] expected = command[7:0];
    wire diagnostic_read = op==3 && command_index>=DIAG_FIRST_INDEX && command_index<=LAST_INDEX;
    wire busy, bus_done;
    wire [2:0] bus_result;
    wire [7:0] data_read;
    reg runtime_read;
    reg [15:0] runtime_address;
    reg [7:0] runtime_data;
    // The read sequence has fixed addresses. Store the nine real readback
    // bytes only; publish them with their addresses after the final ACK.
    reg [71:0] diagnostic_bytes;
    assign diagnostic_words=diagnostic_valid?{
        24'h003e00,diagnostic_bytes[71:64],24'h003e01,diagnostic_bytes[63:56],
        24'h003e02,diagnostic_bytes[55:48],24'h00320e,diagnostic_bytes[47:40],
        24'h00320f,diagnostic_bytes[39:32],24'h003e08,diagnostic_bytes[31:24],
        24'h003e09,diagnostic_bytes[23:16],24'h003e06,diagnostic_bytes[15:8],
        24'h003e07,diagnostic_bytes[7:0]}:288'd0;
    wire runtime_access=state==RT_WAIT;
    assign rt_busy=state!=HALT || busy || error_code!=0;
    i2c_reg16 #(.TICK_CYCLES(I2C_TICK),.TIMEOUT_TICKS(TIMEOUT_TICKS)) bus (
        .clk(clk),.reset(reset),.scl_in(scl_in),.sda_in(sda_in),
        .start(bus_start),.read_op(runtime_access?runtime_read:(op==1 || diagnostic_read)),
        .reg_addr(runtime_access?runtime_address:address),.write_data(runtime_access?runtime_data:expected),
        .scl_low(scl_low),.sda_low(sda_low),.busy(busy),.done(bus_done),
        .result(bus_result),.read_data(data_read)
    );
    task fail;
        input [2:0] code;
        begin error_code<=code; finished<=1; cam_enable<=0; state<=HALT; end
    endtask
    always @(posedge clk) begin
        if(reset) begin
            state<=BOOT; cycles<=0; elapsed_ms<=0; bus_start<=0;
            cam_enable<=0; id_ok<=0; config_ok<=0; stream_set<=0;
            finished<=0; error_code<=0; command_index<=0;
            diagnostic_bytes<=0; diagnostic_valid<=0;
            rt_done<=0;rt_result<=0;rt_read_data<=0;
            runtime_read<=0;runtime_address<=0;runtime_data<=0;
        end else begin
            bus_start<=0;rt_done<=0;
            case(state)
                BOOT: begin
                    if(cycles==CLK_PER_MS-1) begin
                        cycles<=0; elapsed_ms<=elapsed_ms+16'd1;
                        if(elapsed_ms==9) cam_enable<=1;
                        if(elapsed_ms==109) begin state<=FETCH; elapsed_ms<=0; end
                    end else cycles<=cycles+32'd1;
                end
                FETCH: begin
                    if(op==2) begin cycles<=0; elapsed_ms<=0; state<=DELAY; end
                    else if(op==3 && !diagnostic_read) fail(3'd4);
                    else if(!busy) begin bus_start<=1; state<=WAIT_BUS; end
                end
                WAIT_BUS: if(bus_done) begin
                    if(bus_result!=1) fail(bus_result);
                    else if(op==1 && data_read!=expected) fail(3'd3);
                    else begin
                        if(diagnostic_read)
                            diagnostic_bytes<={diagnostic_bytes[63:0],data_read};
                        if(command_index==1) id_ok<=1;
                        if(command_index==CONFIG_DONE_INDEX) config_ok<=1;
                        if(command_index==STREAM_INDEX) stream_set<=1;
                        if(command_index==LAST_INDEX) begin
                             diagnostic_valid<=1; finished<=1; state<=HALT;
                        end else begin cycles<=0; state<=GAP; end
                    end
                end
                GAP: begin
                    // 1 ms STOP-to-START gap also covers small sensor settling delays.
                    if(cycles==CLK_PER_MS-1) begin
                        cycles<=0; command_index<=command_index+8'd1; state<=FETCH;
                    end else cycles<=cycles+32'd1;
                end
                DELAY: begin
                    if(cycles==CLK_PER_MS-1) begin
                        cycles<=0;
                        if(elapsed_ms==address-16'd1) begin
                            elapsed_ms<=0; command_index<=command_index+8'd1; state<=FETCH;
                        end else elapsed_ms<=elapsed_ms+16'd1;
                    end else cycles<=cycles+32'd1;
                end
                HALT: if(rt_start && error_code==0 && diagnostic_valid && !busy) begin
                    runtime_read<=rt_read;runtime_address<=rt_address;runtime_data<=rt_data;
                    bus_start<=1;state<=RT_WAIT;
                end
                RT_WAIT: if(bus_done) begin
                    rt_result<=bus_result;rt_read_data<=data_read;rt_done<=1;state<=HALT;
                end
                default: fail(3'd4);
            endcase
        end
    end
endmodule
