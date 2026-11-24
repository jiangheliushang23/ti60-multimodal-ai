#pragma once
#include <stdint.h>

// Visual event detector for ONE person and a FIXED camera. No temperature gate,
// trained pose classifier, or assumption that a wide box alone means a fall.
namespace fall_detection {
enum State { Empty=0, Normal=1, Suspected=2, Fallen=3 };
inline int minimum(int a,int b){return a<b?a:b;}
inline int maximum(int a,int b){return a>b?a:b;}
inline int absolute(int a){return a<0?-a:a;}
struct Detection {
  int x1,y1,x2,y2;
  unsigned score;
  bool present;
};
struct Result {
  State state;
  bool alarm,event,recovered,armed,tracked;
  unsigned events,track;
  int width,height,ratio_milli,cx,cy,dy,drop_milli;
  unsigned evidence,candidate_ms;
  int reference_height,reference_age_ms,drop_age_ms;
};

class Detector {
 public:
  static const unsigned kArmMs=500,kReferenceMs=1800,kConfirmMs=120;
  static const unsigned kDropWindowMs=1200,kDropEvidenceMs=1600,kEvidenceGapMs=600,kTransitionMs=1200;
  static const unsigned kCandidateGraceMs=400;
  static const unsigned kTrackGapMs=1200,kLostAlarmMs=3000;
  static const unsigned kRecoverMs=1200,kMinimumAlarmMs=2000;
  Detector():events_(0),track_(0){reset();}
  bool alarmed()const{return alarm_;}
  void reset(){
    seen_=arming_=armed_=candidate_=alarm_=recovering_=rapid_drop_=missed_=false;
    last_={0,0,0,0,0,false};reference_=last_;
    seen_at_=arm_at_=reference_at_=candidate_at_=candidate_last_=alarm_at_=recover_at_=0;
    candidate_samples_=history_count_=0;history_next_=0;rapid_at_=transition_at_=0;
  }
  Result update(uint32_t now,const Detection& d,bool verified_pixels=false){
    Result out={Empty,false,false,false,false,false,events_,track_,0,0,0,0,0,0,0,0,0,0,-1,-1};
    const bool good=d.present&&(d.score>=8192||verified_pixels)&&d.x1>=0&&d.y1>=0&&d.x2<=1280&&d.y2<=720&&
                    d.x2-d.x1>=24&&d.y2-d.y1>=36;
    if(!good){
      missed_=true;
      recovering_=false;
      // A detector can miss one or two frames during the posture change. Keep
      // temporal evidence briefly, but never confirm an event on a missing box.
      if(!seen_||uint32_t(now-seen_at_)>kEvidenceGapMs){
        candidate_=rapid_drop_=false;candidate_samples_=history_count_=0;history_next_=0;
      }
      if(!armed_)arming_=false;
      // A missing box is not evidence that this identity has stood up. The
      // identity owner resets this detector when a genuinely new ID takes over.
      if(seen_&&!alarm_&&uint32_t(now-seen_at_)>kTrackGapMs)reset();
      out.alarm=alarm_;out.state=alarm_?Fallen:Empty;out.armed=armed_;return out;
    }
    const int w=d.x2-d.x1,h=d.y2-d.y1,cx=(d.x1+d.x2)/2,cy=(d.y1+d.y2)/2;
    bool discontinuity=false;
    if(seen_){
      const int old_h=last_.y2-last_.y1,old_w=last_.x2-last_.x1;
      const int span=maximum(old_h,maximum(old_w,maximum(h,w)));
      // Do not transfer a fall state to another distant detection. A change in
      // the highest-confidence person is still a limitation in crowded scenes.
      discontinuity=uint32_t(now-seen_at_)>(alarm_?kLostAlarmMs:kTrackGapMs)||
        absolute(cx-(last_.x1+last_.x2)/2)>maximum(160,span*3/4)||
        absolute(cy-(last_.y1+last_.y2)/2)>maximum(160,span*5/4);
    }
    if(discontinuity&&!alarm_)reset();
    if(seen_&&missed_&&uint32_t(now-seen_at_)>kEvidenceGapMs){
      candidate_=rapid_drop_=false;candidate_samples_=history_count_=0;history_next_=0;
    }
    missed_=false;
    if(!seen_){++track_;seen_=true;}
    const int dy=last_.present?cy-(last_.y1+last_.y2)/2:0;
    if(alarm_&&uint32_t(now-seen_at_)>kTrackGapMs)recovering_=false;
    seen_at_=now;last_=d;
    bool just_recovered=false,just_alarm=false;
    // A reliable upright identity may touch one image edge. Requiring every
    // edge to be clear prevented arming in otherwise usable live-camera views.
    const bool upright=!verified_pixels&&w*100<=h*90&&h>=100&&d.score>=8192&&
                       !(d.y1<=1&&d.y2>=719);
    unsigned evidence=0;int drop_age=-1;
    if(alarm_){
      // Recovery requires continuous model-confirmed upright geometry near
      // the pre-fall height. Sitting, low-confidence pixels, missing frames and
      // elapsed time alone cannot clear red. Keep red for at least two seconds.
      const bool stood_up=upright&&h*100>=(reference_.y2-reference_.y1)*85;
      if(stood_up){
        if(!recovering_){recovering_=true;recover_at_=now;}
        if(uint32_t(now-recover_at_)>=kRecoverMs&&uint32_t(now-alarm_at_)>=kMinimumAlarmMs){
          alarm_=false;just_recovered=true;arming_=armed_=candidate_=false;
          candidate_samples_=0;recovering_=false;
        }
      }else recovering_=false;
    }
    if(!alarm_){
      if(arming_&&uint32_t(now-reference_at_)>kReferenceMs){arming_=armed_=candidate_=false;candidate_samples_=0;}
      const int ref_h=reference_.y2-reference_.y1,ref_w=reference_.x2-reference_.x1;
      // Relative descent PLUS compression, with a rate floor. The longer
      // observation window admits oblique/slower collapses without treating a
      // multi-second gradual recline as a witnessed dynamic transition.
      if(armed_&&ref_h>0){
        for(unsigned i=0;i<history_count_;++i){
          const auto& old=history_[i];const uint32_t elapsed=now-old.ms;
          if(elapsed>=80&&elapsed<=kDropWindowMs&&
             (cy-old.cy)*100>=ref_h*12&&(old.height-h)*100>=ref_h*12&&
             int64_t(cy-old.cy)*100000>=int64_t(ref_h)*18*elapsed){
            if(!rapid_drop_)transition_at_=now;
            rapid_drop_=true;rapid_at_=now;break;
          }
        }
      }
      // Keep the first descent onset: repeated comparisons with old tall boxes
      // must not keep renewing an event while a person slowly crouches/crawls.
      const bool recent_drop=rapid_drop_&&uint32_t(now-rapid_at_)<=kDropEvidenceMs&&
        uint32_t(now-transition_at_)<=kTransitionMs;
      if(rapid_drop_)drop_age=int(uint32_t(now-rapid_at_));
      // Existing identity + current upright-shaped pixels can refresh an
      // already armed baseline during brief YOLO dropout. Do not learn a new
      // upright identity or change its geometry from the pixel fallback alone.
      const bool upright_continuity=verified_pixels&&armed_&&ref_h>0&&
        w*100<=h*90&&h*100>=ref_h*90&&h*100<=ref_h*115&&
        absolute(cy-(reference_.y1+reference_.y2)/2)*100<=ref_h*15;
      const bool stable_upright=(upright||upright_continuity)&&(!arming_||h*100>=ref_h*85);
      if(stable_upright){
        if(!arming_){reference_=d;arm_at_=now;arming_=true;}
        else if(!verified_pixels){
          reference_.x1=(reference_.x1*3+d.x1)/4;reference_.y1=(reference_.y1*3+d.y1)/4;
          reference_.x2=(reference_.x2*3+d.x2)/4;reference_.y2=(reference_.y2*3+d.y2)/4;
        }
        reference_at_=now;
        if(uint32_t(now-arm_at_)>=kArmMs)armed_=true;
        candidate_=rapid_drop_=false;candidate_samples_=0;
      }else if(armed_&&ref_h>0&&ref_w>0){
        const int descent=cy-(reference_.y1+reference_.y2)/2;
        // Two ways to reach a low posture: lateral/oblique, or a strongly
        // foreshortened collapse toward/away from the camera. Neither a wide
        // box alone nor an unobserved person already lying down can alarm.
        const bool near_bottom=d.y2>=reference_.y2-ref_h*20/100;
        // Pixel continuation can shrink to a torso/leg fragment when YOLO is
        // absent. Demand a clearer horizontal shape (or width expansion) for
        // that less certain localization source before interpreting posture.
        const bool lateral=w*100>=h*(verified_pixels?115:100)&&h*100<=ref_h*82&&descent*100>=ref_h*12&&
          int64_t(w)*ref_h*100>=int64_t(ref_w)*h*140;
        const bool compact=(!verified_pixels||w*100>=ref_w*135)&&
          w*100>=h*65&&h*100<=ref_h*52&&descent*100>=ref_h*22&&
          int64_t(w)*ref_h*100>=int64_t(ref_w)*h*150;
        evidence=1|(recent_drop?2:0)|(lateral?4:0)|(compact?8:0)|(near_bottom?16:0);
        const bool changed=recent_drop&&near_bottom&&(lateral||compact);
        if(changed){
          if(candidate_&&uint32_t(now-candidate_last_)>kEvidenceGapMs){candidate_=false;candidate_samples_=0;}
          if(!candidate_){candidate_=true;candidate_at_=now;candidate_samples_=1;}
          else ++candidate_samples_;
          candidate_last_=now;
          if(candidate_samples_>=2&&uint32_t(now-candidate_at_)>=kConfirmMs){
            alarm_=just_alarm=true;alarm_at_=now;++events_;candidate_=false;candidate_samples_=0;
          }
        }else if(!candidate_||verified_pixels||!recent_drop||!near_bottom||uint32_t(now-candidate_last_)>kCandidateGraceMs){
          candidate_=false;candidate_samples_=0;
        }
        // A brief ambiguous YOLO box can keep a pending candidate. Ambiguous
        // zero-score pixel fragments cannot. Only a second box satisfying the
        // full rule can confirm within the same descent deadline. Stable
        // upright above always cancels the candidate immediately.
      }else arming_=false;
    }
    const int ref_h=reference_.y2-reference_.y1;
    out.state=alarm_?Fallen:candidate_?Suspected:Normal;
    out.alarm=alarm_;out.event=just_alarm;out.recovered=just_recovered;out.armed=armed_;
    out.tracked=true;out.events=events_;out.track=track_;out.width=w;out.height=h;
    out.ratio_milli=w*1000/h;out.cx=cx;out.cy=cy;out.dy=dy;
    out.drop_milli=ref_h>0?(cy-(reference_.y1+reference_.y2)/2)*1000/ref_h:0;
    out.evidence=evidence|(armed_?1:0)|(candidate_?32:0);
    out.candidate_ms=candidate_?uint32_t(now-candidate_at_):0;
    out.reference_height=ref_h;out.reference_age_ms=arming_?int(uint32_t(now-reference_at_)):-1;
    out.drop_age_ms=drop_age;
    history_[history_next_]={now,cy,h};history_next_=(history_next_+1)%16;
    if(history_count_<16)++history_count_;
    return out;
  }
 private:
  struct Observation {uint32_t ms;int cy,height;};
  Observation history_[16];unsigned history_count_,history_next_;uint32_t rapid_at_,transition_at_;
  bool seen_,arming_,armed_,candidate_,alarm_,recovering_,rapid_drop_,missed_;
  Detection last_,reference_;
  uint32_t seen_at_,arm_at_,reference_at_,candidate_at_,candidate_last_,alarm_at_,recover_at_;
  unsigned candidate_samples_,events_,track_;
};

struct Motion {unsigned changed_pixels,energy;int cx,cy;bool ready;};
// Store only a 24x16 luminance sample, BEFORE Invoke() reuses input tensor RAM.
// Motion is diagnostic evidence, not a camera-motion-dependent alarm gate.
class MotionGrid {
 public:
  MotionGrid():ready_(false),pair_ready_(false){}
  void reset(){ready_=pair_ready_=false;}
  void capture_gray(const uint8_t* gray){
    pair_ready_=ready_;
    for(unsigned i=0;i<384;++i){difference_[i]=ready_?absolute(int(gray[i])-int(previous_[i])):0;previous_[i]=gray[i];}
    ready_=true;
  }
  void capture(const int8_t* rgb,unsigned width,unsigned height,unsigned pad_x,unsigned content_width){
    pair_ready_=ready_;
    for(unsigned y=0;y<16;++y)for(unsigned x=0;x<24;++x){
      const unsigned i=y*24+x;
      const auto* p=rgb+(((2*y+1)*height/32)*width+pad_x+(2*x+1)*content_width/48)*3;
      const unsigned gray=(77*(int(p[0])+128)+150*(int(p[1])+128)+29*(int(p[2])+128)+128)>>8;
      difference_[i]=ready_?absolute(int(gray)-int(previous_[i])):0;previous_[i]=gray;
    }
    ready_=true;
  }
  Motion region(int x1,int y1,int x2,int y2)const{
    Motion out={0,0,-1,-1,pair_ready_};unsigned n=0,changed=0,energy=0,sx=0,sy=0;
    if(!pair_ready_)return out;
    for(unsigned y=0;y<16;++y)for(unsigned x=0;x<24;++x){
      const int px=(2*x+1)*1280/48,py=(2*y+1)*720/32;
      if(px<x1||px>=x2||py<y1||py>=y2)continue;
      const unsigned d=difference_[y*24+x];++n;energy+=d;
      if(d>=14){++changed;sx+=px;sy+=py;}
    }
    out.energy=n?energy/n:0;out.changed_pixels=changed*2400;
    if(changed){out.cx=sx/changed;out.cy=sy/changed;}return out;
  }
 private:
  uint8_t previous_[384],difference_[384];bool ready_,pair_ready_;
};
inline const char* state_name(State state){
  return state==Fallen?"FALLEN":state==Suspected?"SUSPECTED":state==Normal?"NORMAL":"EMPTY";
}
}
