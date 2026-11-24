#include "two_person_tracker.h"
#include "fall_detection.h"
#include <cstring>
extern "C" {
uint32_t tracking_args[15],tracking_output[32],tracking_reset_mode;
two_person_tracker::Tracker tracker;
fall_detection::Detector control_fall,observed_fall;
uint32_t fall_comparison[3];
void tracking_reset(){tracker.reset();control_fall.reset();observed_fall.reset();}
void tracking_step(){
  const uint32_t ms=tracking_args[0];
  const person_roi::Detection a={{int(tracking_args[2]),int(tracking_args[3]),int(tracking_args[4]),int(tracking_args[5])},tracking_args[6],bool(tracking_args[1])};
  const person_roi::Detection b={{int(tracking_args[8]),int(tracking_args[9]),int(tracking_args[10]),int(tracking_args[11])},tracking_args[12],bool(tracking_args[7])};
  const auto before_a=a,before_b=b;
  const fall_detection::Detection f={a.box.x1,a.box.y1,a.box.x2,a.box.y2,a.score,a.valid};
  const auto expected=control_fall.update(ms,f,tracking_args[14]);
  const auto result=tracker.update(ms,a,b,tracking_args[13]);
  const auto actual=observed_fall.update(ms,f,tracking_args[14]);
  tracking_output[0]=result.ids[0];tracking_output[1]=result.ids[1];
  tracking_output[2]=result.active;tracking_output[3]=result.visible;
  for(unsigned i=0;i<2;++i){
    const auto& t=tracker.track(i);auto* o=tracking_output+4+i*14;
    o[0]=t.id;o[1]=t.active;o[2]=t.observed;o[3]=t.last_ms;o[4]=t.hits;o[5]=t.misses;
    o[6]=t.history_count;o[7]=t.history_head;o[8]=t.vx;o[9]=t.vy;
    o[10]=t.box.x1;o[11]=t.box.y1;o[12]=t.box.x2;o[13]=t.box.y2;
  }
  fall_comparison[0]=!memcmp(&a,&before_a,sizeof(a))&&!memcmp(&b,&before_b,sizeof(b));
  // Compare initialized fields, avoiding struct padding in memcmp.
  fall_comparison[1]=expected.state==actual.state&&expected.alarm==actual.alarm&&
    expected.event==actual.event&&expected.armed==actual.armed&&expected.track==actual.track&&
    expected.events==actual.events&&expected.candidate_ms==actual.candidate_ms&&
    expected.reference_height==actual.reference_height&&expected.evidence==actual.evidence;
  fall_comparison[2]=actual.alarm;
}
}
