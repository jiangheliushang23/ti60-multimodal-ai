// Executed as RV32 code with independently modelled MMIO. No speed claims.
#include "camera_live_source.h"
extern "C" {
int8_t test_image[kInputBytes];
int8_t test_alternate[kInputBytes];
camera_live_source::Frame test_frame;
camera_live_source::Rectangle test_rectangle;
camera_live_source::Rectangle test_second;
uint32_t test_result;
uint32_t test_alarm;
int32_t test_args[5];
int32_t test_map_args[9],test_map_result[4];
void run_map_view(){
  auto v=person_roi::view({test_map_args[0],test_map_args[1],test_map_args[2],test_map_args[3]},192,96,test_map_args[4]);
  auto r=person_roi::map(v,{test_map_args[5],test_map_args[6],test_map_args[7],test_map_args[8],20000});
  test_map_result[0]=r.x1;test_map_result[1]=r.y1;test_map_result[2]=r.x2;test_map_result[3]=r.y2;
}
void run_prepare(){camera_live_source::prepare_input(reinterpret_cast<const volatile uint16_t*>(0x06000000),test_image);}
void run_prepare_view(){auto v=person_roi::view({test_args[0],test_args[1],test_args[2],test_args[3]},192,96,test_args[4]);
  camera_live_source::prepare_view(reinterpret_cast<const volatile uint16_t*>(0x06000000),test_image,v);}
void run_capture_views(){test_result=camera_live_source::capture_views(test_image,test_alternate,&test_frame,
  person_roi::view({320,180,960,540}),person_roi::full());}
void run_capture(){test_result=camera_live_source::capture(test_image,&test_frame);}
void run_monitor(){test_result=camera_live_source::capture_monitor(&test_frame);}
void run_overlay(){test_result=camera_live_source::overlay(test_args[0],test_rectangle,test_alarm!=0);}
void run_overlay_pair(){test_result=camera_live_source::overlay_pair(test_args[0],test_rectangle,test_second,test_alarm!=0);}
void run_rectangle(){test_rectangle=camera_live_source::rectangle(test_args[0],test_args[1],test_args[2],test_args[3],test_args[4]);}
}
uint32_t milliseconds(){return *reinterpret_cast<volatile uint32_t*>(0xf8103ff0);}
void cache_sync(){} // Cache/DMA hardware ordering is tested separately in RTL.
