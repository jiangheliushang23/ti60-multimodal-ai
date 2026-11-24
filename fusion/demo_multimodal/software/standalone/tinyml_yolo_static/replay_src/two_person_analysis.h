#pragma once
#include "two_person_tracker.h"
#include "person_visual_track.h"
#include "fall_detection.h"

namespace two_person_analysis {
using person_roi::Detection;
inline Detection empty(){return {{0,0,0,0},0,false};}
struct Result {
  Detection detections[2];uint32_t ids[2];bool pixels[2],alarm[2];
  fall_detection::Result falls[2],lane_falls[2];
  person_visual_track::Result supports[2];bool rescued[2];unsigned visible,active;
  bool any_alarm;
};
class Manager {
 public:
  Manager(){reset();}
  void reset(){
    tracker_.reset();
    for(unsigned i=0;i<2;++i){owners_[i]=0;fall_[i]=fall_detection::Detector();visual_[i].reset();}
  }
  const two_person_tracker::Track& track(unsigned slot)const{return tracker_.track(slot);}
  Result update(uint32_t captured,uint32_t /*now*/,const Detection& first,const Detection& second,
                bool first_pixels,bool fresh,const uint16_t* image=nullptr){
    Result out={};out.detections[0]=fresh?first:empty();out.detections[1]=fresh?second:empty();
    // Keep an alarmed identity through detector dropout. Retention never draws
    // a stale rectangle, and a distinct new detection still receives a new ID.
    for(unsigned i=0;i<2;++i)tracker_.retain_alarm(i,fall_[i].alarmed());
    out.pixels[0]=first_pixels;const auto ids=tracker_.update(captured,first,second,fresh);
    out.ids[0]=ids.ids[0];out.ids[1]=ids.ids[1];
    for(unsigned j=0;j<2;++j)if(!out.ids[j])out.detections[j]=empty();
    for(unsigned slot=0;slot<2;++slot){
      const auto& t=tracker_.track(slot);
      if(t.active&&t.id!=owners_[slot]){
        owners_[slot]=t.id;fall_[slot]=fall_detection::Detector();visual_[slot].forget_identity();
      }
      int input=-1;
      for(unsigned j=0;j<2;++j)if(out.ids[j]&&out.ids[j]==t.id&&t.observed)input=int(j);
      // The original primary current-pixel box is retained byte for byte. Its
      // zero-score continuation is never used as model appearance training.
      const Detection model=input>=0&&!out.pixels[input]?out.detections[input]:empty();
      if(image){
        const auto supported=visual_[slot].update(captured,image,model);
        if(input<0&&fresh&&supported.fallback&&t.active){
          int free=-1;for(int j=1;j>=0;--j)if(!out.detections[j].valid){free=j;break;}
          bool duplicate=false;
          for(unsigned j=0;j<2;++j)if(out.detections[j].valid&&person_pair::duplicate(out.detections[j].box,supported.detection.box))duplicate=true;
          if(free>=0&&!duplicate&&tracker_.observe_pixels(slot,captured,supported.detection)){
            input=free;out.detections[free]=supported.detection;out.ids[free]=t.id;out.pixels[free]=true;
            out.supports[free]=supported;out.rescued[free]=true;
          }
        }
      }
      const Detection d=input>=0?out.detections[input]:empty();
      const fall_detection::Detection geometry={d.box.x1,d.box.y1,d.box.x2,d.box.y2,d.score,d.valid};
      // SAME production Detector for each identity, SAME captured timestamps.
      // Each identity keeps the original fall classifier and captured timestamp.
      const auto f=fall_[slot].update(captured,geometry,input>=0&&out.pixels[input]&&fresh);
      out.lane_falls[slot]=f;
      out.any_alarm|=f.alarm;
      if(input>=0){
        out.falls[input]=f;out.alarm[input]=f.alarm;
      }
    }
    for(unsigned i=0;i<2;++i){out.visible+=out.detections[i].valid;out.active+=tracker_.track(i).active;}
    return out;
  }
 private:
  two_person_tracker::Tracker tracker_;uint32_t owners_[2];
  fall_detection::Detector fall_[2];person_visual_track::Tracker visual_[2];
};
inline unsigned bcd_id(uint32_t id){
  unsigned bcd=0;for(unsigned i=0;i<4;++i){bcd|=(id%10)<<(i*4);id/=10;}return bcd;
}
inline unsigned flags(const Detection& d,uint32_t id,bool alarm){
  return d.valid?(3u|(alarm?4u:0u)|(id?16u:0u)|(bcd_id(id)<<5)):0;
}
}
