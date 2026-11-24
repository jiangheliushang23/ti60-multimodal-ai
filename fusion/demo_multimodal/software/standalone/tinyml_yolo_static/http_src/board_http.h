#pragma once
#include <stdint.h>
namespace board_http {
void initialize();
void service(bool link,unsigned power_mode);
void publish_status(const uint8_t* bmon,unsigned bytes);
bool snapshot_requested();
void publish_rgb565(const uint16_t* pixels,unsigned sequence,unsigned capture_ms);
}
