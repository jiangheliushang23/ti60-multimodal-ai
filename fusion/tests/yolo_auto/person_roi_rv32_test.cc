#include "person_roi.h"
#include "fall_detection.h"
extern "C" {
uint32_t roi_args[4];
person_roi::Box roi_boxes[8];
int32_t roi_output[32];
}
person_roi::Planner planner;
fall_detection::Detector fall;
person_roi::View active,secondary;
person_roi::Detection selected;
void export_view(){
  const int v[]={active.roi.x1,active.roi.y1,active.roi.x2,active.roi.y2,
                 active.nw,active.nh,active.px,active.py,active.zoom,int(active.turns)};
  for(unsigned i=0;i<10;++i)roi_output[i]=v[i];
}
extern "C" void roi_reset(){planner.reset();fall.reset();}
extern "C" void roi_plan(){
  active=planner.next(roi_args[0]);secondary=planner.alternate(active,roi_args[0]);planner.acquired();export_view();
}
extern "C" void roi_alternate(){active=secondary;export_view();}
extern "C" void roi_pick(){
  selected=planner.select(active,roi_boxes,roi_args[1],roi_args[0]);
  const int v[]={selected.box.x1,selected.box.y1,selected.box.x2,selected.box.y2,int(selected.score),selected.valid};
  for(unsigned i=0;i<6;++i)roi_output[i]=v[i];
}
extern "C" void roi_commit(){
  planner.commit(roi_args[0],selected,active.turns);
  const auto& r=selected.box;
  const auto f=fall.update(roi_args[0],{r.x1,r.y1,r.x2,r.y2,selected.score,selected.valid});
  const int v[]={f.state,f.alarm,f.event,f.recovered,f.armed,f.tracked,int(f.events),int(f.track),
                 f.width,f.height,f.ratio_milli,f.cx,f.cy,f.dy,f.drop_milli};
  for(unsigned i=0;i<15;++i)roi_output[i]=v[i];
}
