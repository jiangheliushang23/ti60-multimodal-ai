#include "two_person_analysis.h"
using namespace two_person_analysis;
extern "C" {
uint32_t dual_args[16],dual_out[64],risk_args[13],risk_out[12];
uint16_t dual_image[person_visual_track::Pixels];
uint32_t dual_image_enabled;
Manager manager;
fall_detection::Detector reference[2];
uint32_t reference_id[2];
void dual_reset(){manager.reset();for(unsigned i=0;i<2;++i){reference[i]=fall_detection::Detector();reference_id[i]=0;}}
bool same(const fall_detection::Result&a,const fall_detection::Result&b){
 return a.state==b.state&&a.alarm==b.alarm&&a.event==b.event&&a.recovered==b.recovered&&a.armed==b.armed&&a.tracked==b.tracked&&a.events==b.events&&a.track==b.track&&a.width==b.width&&a.height==b.height&&a.ratio_milli==b.ratio_milli&&a.cx==b.cx&&a.cy==b.cy&&a.dy==b.dy&&a.drop_milli==b.drop_milli&&a.evidence==b.evidence&&a.candidate_ms==b.candidate_ms&&a.reference_height==b.reference_height&&a.reference_age_ms==b.reference_age_ms&&a.drop_age_ms==b.drop_age_ms;
}
void dual_step(){
 auto* a=dual_args;
 Detection first={{int(a[3]),int(a[4]),int(a[5]),int(a[6])},a[7],bool(a[2])};
 Detection second={{int(a[9]),int(a[10]),int(a[11]),int(a[12])},a[13],bool(a[8])};
 auto r=manager.update(a[0],a[1],first,second,a[15],a[14],dual_image_enabled?dual_image:nullptr);
 dual_out[0]=r.visible;dual_out[1]=r.active;dual_out[2]=r.any_alarm;dual_out[3]=1;
 for(unsigned i=0;i<2;++i){
  const auto&t=manager.track(i);
  if(t.active&&reference_id[i]!=t.id){reference_id[i]=t.id;reference[i]=fall_detection::Detector();}
  int input=-1;for(unsigned j=0;j<2;++j)if(r.ids[j]&&r.ids[j]==t.id)input=j;
  Detection d=input>=0?r.detections[input]:empty();
  auto expected=reference[i].update(a[0],{d.box.x1,d.box.y1,d.box.x2,d.box.y2,d.score,d.valid},input>=0&&r.pixels[input]&&bool(a[14]));
  dual_out[3]&=same(expected,r.lane_falls[i]);
 }
 for(unsigned i=0;i<2;++i){
  auto*o=dual_out+4+i*20;const auto&f=r.falls[i];
  o[0]=r.ids[i];o[1]=r.detections[i].valid;o[2]=f.state;o[3]=f.alarm;o[4]=f.event;o[5]=f.armed;
  for(unsigned k=6;k<12;++k)o[k]=0;
  o[12]=flags(r.detections[i],r.ids[i],f.alarm);o[13]=f.events;
  o[14]=r.pixels[i];o[15]=r.rescued[i];
 }
}
void risk_step(){
 auto*a=risk_args;
 Detection d={{0,0,100,200},25000,bool(a[0])};
 risk_out[0]=flags(d,a[1],bool(a[2]));
 risk_out[1]=bcd_id(a[1]);
}
}
