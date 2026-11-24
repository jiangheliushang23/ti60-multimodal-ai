#include "person_roi_rv32_test.cc"
#include "person_visual_track.h"
person_visual_track::Tracker visual;
person_visual_track::Result visual_result;
extern "C" {
uint16_t visual_pixels[person_visual_track::Pixels];
int32_t visual_info[16];
int32_t visual_model[6];
void visual_reset(){visual.reset();roi_reset();}
void visual_export(){
  const auto& v=visual_result;const auto& r=v.detection.box;
  const int t[]={r.x1,r.y1,r.x2,r.y2,int(v.detection.score),v.detection.valid,v.fallback,v.ready,
    int(v.foreground),int(v.support),int(v.known),int(v.scene_change),int(v.appearance)};
  for(unsigned i=0;i<13;++i)visual_info[i]=t[i];
}
void visual_observe(){visual_result=visual.update(roi_args[0],visual_pixels,selected);visual_export();}
void visual_finish(){
  if(roi_args[2]&&selected.valid){
    visual.confirm(roi_args[0],visual_pixels,selected);
    visual_result.detection=selected;visual_result.fallback=false;
  }
  const auto& v=visual_result;
  selected=v.detection;
  planner.commit(roi_args[0],selected,v.fallback?0:active.turns);
  const auto& r=selected.box;
  const auto f=fall.update(roi_args[0],{r.x1,r.y1,r.x2,r.y2,selected.score,selected.valid},v.fallback);
  const int values[]={f.state,f.alarm,f.event,f.recovered,f.armed,f.tracked,int(f.events),int(f.track),f.width,f.height,f.ratio_milli,f.cx,f.cy,f.dy,f.drop_milli};
  for(unsigned i=0;i<15;++i)roi_output[i]=values[i];
  visual_export();
}
void visual_commit(){visual_observe();visual_finish();}
void visual_direct(){
  selected={{visual_model[0],visual_model[1],visual_model[2],visual_model[3]},unsigned(visual_model[4]),bool(visual_model[5])};
  visual_observe();visual_finish();
}
}
