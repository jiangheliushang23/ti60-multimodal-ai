# SYN6658 GPIO UART 9600 baud, 8N1; original signal names/pins retained.
# Conservative core-register-to-pad budget: constrain each output within one
# 100MHz peripheral cycle. UART bit timing is checked by production driver tests.
# These constraints do not claim measured external board delays.
set_output_delay -clock i_peripheralClk -max 0.000 [get_ports {voice_spi_clk voice_spi_mosi voice_spi_cs_n}]
set_output_delay -clock i_peripheralClk -min 0.000 [get_ports {voice_spi_clk voice_spi_mosi voice_spi_cs_n}]
# External busy/MISO terminate ONLY in their corresponding first-stage D pin.
# Later synchronizer stages and every internal SPI path retain 100MHz timing.
# Recheck these two endpoint matches in map/pnr logs; zero matches is an error.
set_false_path -from [get_ports {voice_spi_miso}] -to [get_pins {u_voice_spi/miso_meta*|D}]
set_false_path -from [get_ports {voice_module_busy}] -to [get_pins {u_voice_spi/busy_meta*|D}]
