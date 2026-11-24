#pragma once
#include <cstdint>
namespace scene_power {
enum Mode {Normal,Entering,Sleep,Recovering,Verifying};
inline const char* name(Mode s){return s==Normal?"NORMAL":s==Entering?"ENTERING":s==Sleep?"LOW":s==Recovering?"RECOVERING":"VERIFYING";}
inline unsigned display_status(Mode mode,unsigned fps_x10,bool valid){
 if(fps_x10>999)fps_x10=999;
 const unsigned bcd=((fps_x10/100)<<8)|(((fps_x10/10)%10)<<4)|(fps_x10%10);
 return unsigned(mode)|(valid?8u:0u)|(bcd<<4);
}
struct Manager {
 static const unsigned kEmptyMs=30000,kEvidenceGapMs=3000,kWakeCooldownMs=5000,kVerifyMs=5000;
 Mode mode=Normal;bool empty=false,alarm=false;unsigned empty_since=0,last_frame=0,last_change=0;
 bool verification_rejected=false;unsigned verify_started=0;
 bool want_low()const{return mode==Entering||mode==Sleep;}
 bool inference_allowed()const{return mode==Normal||(mode==Entering&&!verification_rejected)||mode==Verifying;}
 bool led()const{return mode==Sleep||mode==Recovering||mode==Verifying||(mode==Entering&&verification_rejected);}
 unsigned empty_ms(unsigned now)const{return empty?unsigned(now-empty_since):0;}
 void observe(unsigned time,bool present,bool fall_alarm){
  // A thermal wake gives YOLO five seconds of fresh, normal-rate frames.
  // Negative results keep the window open; a real person ends it immediately.
  if(mode==Verifying){
   if(int32_t(time-verify_started)<0)return;
   last_frame=time;alarm=fall_alarm;
   if(present||fall_alarm){mode=Normal;empty=false;verification_rejected=false;last_change=time;}
   return;
  }
  alarm=fall_alarm;
  if(present||fall_alarm){empty=false;if(mode==Entering||mode==Sleep)wake(time);last_frame=time;return;}
  if(mode!=Normal&&mode!=Entering)return;
  if(!empty||unsigned(time-last_frame)>kEvidenceGapMs){empty=true;empty_since=time;}
  last_frame=time;
  if(mode==Normal&&unsigned(time-empty_since)>=kEmptyMs&&unsigned(time-last_change)>=kWakeCooldownMs){mode=Entering;last_change=time;}
 }
 void tick(unsigned now){
  if(mode==Verifying&&unsigned(now-verify_started)>=kVerifyMs){
   mode=Entering;verification_rejected=true;empty=false;last_change=now;
  }
 }
 void no_frame(unsigned now){if(unsigned(now-last_frame)>kEvidenceGapMs){empty=false;if(mode==Entering)wake(now);}}
 void wake(unsigned now){if(mode==Sleep||mode==Entering){mode=Recovering;last_change=now;empty=false;verification_rejected=false;}}
 void camera_state(unsigned now,bool low,bool settled,bool failed){
  if(failed){mode=Normal;empty=false;verification_rejected=false;last_change=now;return;}
  if(!settled)return;
  if(mode==Entering&&low){mode=Sleep;last_change=now;}
  if(mode==Recovering&&!low){mode=Verifying;empty=false;last_frame=now;last_change=now;verify_started=now;}
 }
};
struct MotionWake {
 uint8_t background[384];bool seeded=false;unsigned confirmations=0;
 void reset(const uint8_t* p=nullptr){seeded=p;confirmations=0;if(p)for(unsigned i=0;i<384;++i)background[i]=p[i];}
 bool update(const uint8_t* p){
  if(!seeded){reset(p);return false;}
  unsigned changed=0,energy=0;int signed_sum=0;
  for(unsigned i=0;i<384;++i){int d=int(p[i])-background[i];signed_sum+=d;unsigned a=d<0?-d:d;energy+=a;changed+=a>=18;}
  // A global exposure change does not by itself look like a local entrant.
  int mean=signed_sum/384;unsigned local=0;
  for(unsigned i=0;i<384;++i){int d=int(p[i])-background[i]-mean;local+=(d<0?-d:d)>=16;}
  const bool event=(changed>=10&&local>=8&&energy>=800);
  confirmations=event?confirmations+1:0;
  if(!event)for(unsigned i=0;i<384;++i)background[i]=(background[i]*31u+p[i]+16)/32;
  return confirmations>=2;
 }
};
}
