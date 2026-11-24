#pragma once
#include "syn6658_voice.h"
#include "uart_voice_controller.h"

namespace voice_uart {
// One speaker serializes both identities. A new fall takes priority over a
// recovery sentence; no STOP from a second controller can corrupt the wire.
class FallQueue {
 public:
  Controller controller;
  unsigned person_id=0,person_event=0,queued=0,cancelled=0,overflow=0,serial=0;
  void initialize(uint32_t now){controller.initialize(now);}
  unsigned waiting()const{return count_;}
  bool running()const{return running_;}
  void clear(uint32_t now){
    assist_pending_=false;controller.cancel_assist();
    cancelled+=count_;count_=0;
    controller.observe(now,false,false,0);controller.cancel_recovery();
    if(controller.phase!=Playing)running_=false;
    for(unsigned i=0;i<2;++i)seen_[i]=recovery_seen_[i]=recovery_pending_[i]={0,0};
  }
  unsigned observe(uint32_t now,const syn6658_voice::FallEvent (&events)[2]){
    unsigned added=0;
    bool new_fall=false;for(unsigned i=0;i<2;++i)new_fall|=events[i].alarm&&events[i].event;
    if(new_fall){assist_pending_=false;controller.cancel_assist();}
    for(unsigned i=0;i<count_;){
      const auto& p=pending_[i];
      if(!valid(events,p.id,p.kind)){erase(i);++cancelled;}else ++i;
    }
    if(running_&&!valid(events,person_id,controller.kind)){
      if(controller.kind==Recovery){controller.cancel_recovery();running_=false;}
      else {controller.observe(now,false,false,0);if(controller.phase!=Playing)running_=false;}
    }
    for(unsigned lane=0;lane<2;++lane){
      const auto& e=events[lane];
      auto& recovery=recovery_pending_[lane];
      if(recovery.id!=e.track_id||e.alarm)recovery={0,0};
      if(e.track_id&&e.alarm&&e.event&&
         (seen_[lane].id!=e.track_id||seen_[lane].event!=e.event_id)){
        seen_[lane]={e.track_id,e.event_id};
        // A fall must not wait behind a stale "stood up" message.
        if(running_&&controller.kind==Recovery){controller.cancel_recovery();running_=false;}
        // Other identities' queued recovery messages remain valid; service()
        // selects the urgent fall first without deleting those reminders.
        if(append(e.track_id,e.event_id,now,Fall))added|=1u<<lane;
      }
      if(e.track_id&&e.recovered&&!e.alarm)recovery={e.track_id,e.event_id};
      if(recovery.id&&e.displayed&&!e.alarm&&
         (recovery_seen_[lane].id!=e.track_id||recovery_seen_[lane].event!=e.event_id)){
        if(append(e.track_id,e.event_id,now,Recovery)){
          recovery_seen_[lane]=recovery;recovery={0,0};added|=1u<<(lane+2);
        }
      }
    }
    return added;
  }
  bool unauthorized(uint32_t now){if(assist_pending_||(controller.kind==Unauthorized&&controller.phase!=Idle))return false;assist_pending_=true;assist_at_=now;return true;}
  bool test(uint32_t now){return !running_&&!count_&&controller.test(now);}
  template<class Hardware>void service(uint32_t now,Hardware& hw){
    for(unsigned i=0;i<count_;){
      if(uint32_t(now-pending_[i].at)>=(pending_[i].kind==Recovery?30000u:10000u)){erase(i);++cancelled;}else ++i;
    }
    if(!running_&&controller.phase==Idle&&count_){
      unsigned at=0;for(unsigned i=0;i<count_;++i)if(pending_[i].kind==Fall){at=i;break;}
      const auto next=pending_[at];erase(at);
      person_id=next.id;person_event=next.event;
      controller.observe(now,false,false,0);
      if(next.kind==Recovery)running_=controller.recover(now,++serial);
      else {controller.observe(now,true,true,++serial);running_=true;}
    }
    if(assist_pending_&&uint32_t(now-assist_at_)>=10000)assist_pending_=false;
    if(assist_pending_&&!running_&&!count_&&controller.phase==Idle){controller.unauthorized(now,++serial);assist_pending_=false;}
    const unsigned finished=controller.uart_completed+controller.failed;
    controller.service(now,hw);
    if(controller.uart_completed+controller.failed!=finished)running_=false;
  }
 private:
  bool assist_pending_=false;uint32_t assist_at_=0;
  struct Key {unsigned id,event;};
  struct Pending {unsigned id,event;uint32_t at;Kind kind;};
  Key seen_[2]={{0,0},{0,0}},recovery_seen_[2]={{0,0},{0,0}},recovery_pending_[2]={{0,0},{0,0}};
  Pending pending_[4];unsigned count_=0;bool running_=false;
  static bool valid(const syn6658_voice::FallEvent (&e)[2],unsigned id,Kind kind){
    for(unsigned i=0;i<2;++i)if(id&&e[i].track_id==id)return kind==Recovery?!e[i].alarm:e[i].alarm;
    return false;
  }
  bool append(unsigned id,unsigned event,uint32_t at,Kind kind){
    if(count_==4){++overflow;return false;}
    pending_[count_++]={id,event,at,kind};++queued;return true;
  }
  void erase(unsigned at){for(unsigned i=at+1;i<count_;++i)pending_[i-1]=pending_[i];--count_;}
};
}
