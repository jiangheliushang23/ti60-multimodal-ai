// The same production algorithm is executed as RV32 code by the host test.
#include "fall_detection.h"
namespace {fall_detection::Detector detector;fall_detection::MotionGrid motion;}
extern "C" {
uint32_t fall_args[8],fall_output[20];
int8_t motion_input[192*96*3];
int32_t motion_args[4],motion_output[5];
void fall_reset(){detector.reset();motion.reset();}
void fall_step(){
  const fall_detection::Detection d={int(fall_args[2]),int(fall_args[3]),int(fall_args[4]),int(fall_args[5]),fall_args[6],fall_args[1]!=0};
  const auto r=detector.update(fall_args[0],d,fall_args[7]!=0);
  const uint32_t values[]={unsigned(r.state),r.alarm,r.event,r.recovered,r.armed,r.tracked,r.events,r.track,
    unsigned(r.width),unsigned(r.height),unsigned(r.ratio_milli),unsigned(r.cx),unsigned(r.cy),unsigned(r.dy),unsigned(r.drop_milli),
    r.evidence,r.candidate_ms,unsigned(r.reference_height),unsigned(r.reference_age_ms),unsigned(r.drop_age_ms)};
  for(unsigned i=0;i<20;++i)fall_output[i]=values[i];
}
void motion_capture(){motion.capture(motion_input,192,96,10,171);}
void motion_region(){
  const auto r=motion.region(motion_args[0],motion_args[1],motion_args[2],motion_args[3]);
  motion_output[0]=r.changed_pixels;motion_output[1]=r.energy;motion_output[2]=r.cx;
  motion_output[3]=r.cy;motion_output[4]=r.ready;
}
}
