#pragma once
#include <stdint.h>
#include "multimodal_alignment.h"
#include "../replay_src/two_person_analysis.h"
namespace network_monitor {
void initialize();
void service(unsigned power_mode=~0u);
// Bounded IRQ work: camera + packet I/O only, no logging/sensors/AI.
void preview_tick();
unsigned sent_images();
// Copy only; these functions never modify camera tensors, detections or alarms.
void camera_input(const int8_t* rgb,unsigned width,unsigned height,unsigned xpad,unsigned ypad,
                  unsigned active_width,unsigned active_height,unsigned sequence,unsigned capture_ms);
void low_camera(const uint8_t* gray,unsigned width,unsigned height,unsigned sequence,unsigned capture_ms);
void observe(const two_person_analysis::Result&,const multimodal_alignment::Result&,
             unsigned source_count,unsigned captured_ms,unsigned inference_ms,unsigned fps_tenths);
}
