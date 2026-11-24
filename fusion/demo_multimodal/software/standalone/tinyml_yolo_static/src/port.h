#pragma once
#include <stdint.h>
void log_line(const char* format, ...);
uint32_t milliseconds();
void platform_finish(bool success);
int read_command();
void uart_write_bytes(const uint8_t* data,unsigned bytes);
