#pragma once
#include <stdint.h>
#include "multimodal_alignment.h"
namespace multimodal_sensors {
void initialize();
void network_sample(unsigned now,multimodal_alignment::Result& out);
void service();
void write_metrics(unsigned fps_tenths,unsigned inference_ms,unsigned score_q15);
const multimodal_alignment::Result& align_video(unsigned capture_ms,unsigned video_sequence);
bool thermal_wake(unsigned& last_sequence);
void observe_visual_presence(unsigned capture_ms,bool present);
void reject_thermal_candidate(unsigned now);
void set_low_power_monitor(bool enabled);
bool thermal_monitor_healthy(unsigned now);
}
