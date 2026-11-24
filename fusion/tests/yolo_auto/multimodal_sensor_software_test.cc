#include "multimodal_sensors.h"
#include "port.h"
extern "C" {
void test_initialize(){multimodal_sensors::initialize();}
unsigned test_wake_count=0,test_wake_sequence=0,test_thermal_healthy=0;
bool test_low_power=false;
void test_enable_low(){test_low_power=true;multimodal_sensors::set_low_power_monitor(true);}
void test_reject_heat(){
 multimodal_sensors::set_low_power_monitor(false);
 multimodal_sensors::reject_thermal_candidate(milliseconds());
 multimodal_sensors::set_low_power_monitor(true);test_wake_count=0;
}
void test_service(){
 multimodal_sensors::service();
 if(test_low_power){
  if(multimodal_sensors::thermal_wake(test_wake_sequence))++test_wake_count;
  test_thermal_healthy=multimodal_sensors::thermal_monitor_healthy(milliseconds());
 }
}
void test_metrics(){multimodal_sensors::write_metrics(50,175,31130);}
unsigned test_aligned[10];
void test_alignment(){
 const auto& a=multimodal_sensors::align_video(*reinterpret_cast<volatile uint32_t*>(0xf8103ff4u),123);
 test_aligned[0]=a.infrared_valid;test_aligned[1]=a.environment_valid;
 test_aligned[2]=a.ir_delta_ms[0];test_aligned[3]=a.ir_delta_ms[1];test_aligned[4]=a.env_delta_ms;
 test_aligned[5]=a.minimum;test_aligned[6]=a.maximum;test_aligned[7]=a.center;
 test_aligned[8]=a.video_sequence;test_aligned[9]=a.env_temperature;
}
}
uint32_t milliseconds(){return *reinterpret_cast<volatile uint32_t*>(0xf8103ff0u);}
void log_line(const char* format,...){*reinterpret_cast<volatile uint32_t*>(0xf8103fe0u)=reinterpret_cast<uint32_t>(format);}
