"""Refresh physical delays from the generated interface report; no hardware I/O."""
from pathlib import Path
import json
import re

root = Path(__file__).resolve().parents[1]
project = root / 'ti60_multimodal'
name = 'Ti60_Multimodal'
generated = project / 'outflow' / (name + '.pt.sdc')
text = generated.read_text(encoding='utf-8')
text = text.replace('<USER_PERIOD> -name CLK_27M','37.037 -name CLK_27M')
text = text.replace('create_clock -period <USER_PERIOD> -name clk_25m',
                    'create_clock -period 40.000 -name clk_25m')
text = text.replace('# create_clock -period <USER_PERIOD> -name i_cam_ck_CLKOUT',
                    'create_clock -period 14.286 -name i_cam_ck_CLKOUT')
for n in (1,):
    old = f'# create_clock -period <USER_PERIOD> -name jtag_inst{n}_TCK'
    assert old in text
    text = text.replace(old, f'create_clock -period 125.000 -name jtag_inst{n}_TCK')
header = '# V4 adaptation: regenerated interface timing values, 25MHz board reference.\n'
header += '# JTAG constrained at 8MHz (125ns); use an adapter speed at or below 8000kHz.\n'
header += '# 8MHz is the non-legacy IDE setting in debug_ti.cfg; its other branch uses 800kHz.\n'
header += '# Source generated template is retained in outflow/*.pt.sdc.\n'
header += '# JTAG1 RESET/UPDATE/DRCK are absent from the optimized netlist in this configuration.\n'
text = ''.join(line for line in text.splitlines(True)
               if not re.search(r'jtag_inst1_(?:RESET|UPDATE|DRCK)\b', line))
groups = '\n# Preserve the original DDR demo clock-domain partition for this baseline.\n'
for clk in ('core_clk', 'sdram_clk', 'rx_cal_clk', 'tx_cal_clk', 'i_sysclk'):
    groups += 'set_clock_groups -group { ' + clk + ' }\n'
groups += 'set_clock_groups -asynchronous -group { jtag_inst1_TCK }\n'
groups += '# UART has no board-level clock shared with the FT4232 receiver/transmitter.\n'
groups += '# RX is internally synchronized by the supplied SoC; TX is externally sampled.\n'
groups += 'set_false_path -from [get_ports {system_uart_0_io_rxd}]\n'
groups += 'set_false_path -to [get_ports {system_uart_0_io_txd}]\n'
groups += 'set_clock_groups -asynchronous -group {hdmi_tx_slow_clk}\n'
groups += 'set_false_path -from [get_ports {hdmi_tx_locked}]\n'
groups += '# CSI byte/pixel clocks cross only through receiver FIFOs and held line/status handshakes.\n'
groups += 'set_clock_groups -asynchronous -group {i_mipi_rx_pclk}\n'
groups += 'set_clock_groups -asynchronous -group {i_cam_ck_CLKOUT}\n'
groups += 'set_false_path -from [get_ports {camera_pll_locked}]\n'
active = [line for line in text.splitlines() if line.strip() and not line.lstrip().startswith('#')]
assert not any(re.search(r'<(?:USER_PERIOD|CLOCK|MAX|MIN)', line) for line in active)
assert 'ddr_addr[14]' not in text and 'ddr_addr[15]' not in text
(project / 'sdc/ddr3.sdc').write_text(header + text + groups, encoding='utf-8')
print(json.dumps({'generated_source': str(generated), 'active_constraints': len(active),
                  'board_reference_MHz': 25, 'jtag_max_MHz': 8, 'hardware_access': False}, indent=2))

with (project / "sdc/ddr3.sdc").open("a",encoding="utf-8") as f:
    for signal in ("sht_scl_IN","sht_sda_IN","ir_scl_IN","ir_sda_IN","io_cam_scl_IN","io_cam_sda_IN"):
        f.write("set_false_path -from [get_ports {"+signal+"}]\n")
