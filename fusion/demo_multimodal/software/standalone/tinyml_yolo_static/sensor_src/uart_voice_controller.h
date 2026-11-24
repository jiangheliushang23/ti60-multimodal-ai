#pragma once
#include <stdint.h>
#include "uart_voice_transport.h"

namespace voice_uart {
enum Phase { Idle, Gap, Playing };
enum Kind { None, Fall, Test, Recovery, Unauthorized };
enum Error { Ok, Expired, TransportInvalid, NoAcknowledgment, Rejected, PlaybackTimeout, Cancelled, StatusTimeout };
static const uint8_t kFall[]={0xbc,0xec,0xb2,0xe2,0xb5,0xbd,0xb5,0xf8,0xb5,0xb9,
  0xa3,0xac,0xc7,0xeb,0xc8,0xb7,0xc8,0xcf,0xb0,0xb2,0xc8,0xab};
static const uint8_t kTest[]={0xd3,0xef,0xd2,0xf4,0xb2,0xa5,0xb1,0xa8,0xb2,0xe2,0xca,0xd4};
// GBK: the two bounded UART frames form the user's complete recovery sentence.
static const uint8_t kRecoveryIntro[]={0xbc,0xec,0xb2,0xe2,0xb5,0xbd,0xc4,0xfa,0xd2,0xd1,
  0xd6,0xd8,0xd0,0xc2,0xd5,0xbe,0xc6,0xf0,0xa3,0xac};
static const uint8_t kRecoverySafety[]={0xc7,0xeb,0xc8,0xb7,0xc8,0xcf,0xc9,0xed,0xcc,0xe5,
  0xd7,0xb4,0xbf,0xf6,0xa3,0xac,0xd7,0xa2,0xd2,0xe2,0xb0,0xb2,0xc8,0xab,0xa1,0xa3};
static const uint8_t kUnauthorizedIntro[]={0xb7,0xc7,0xca,0xda,0xc8,0xa8,0xca,0xb1,0xb6,0xce,0xc8,0xcb,0xc8,0xcb,0xcc,0xe5};
static const uint8_t kUnauthorizedEnd[]={0xb3,0xf6,0xcf,0xd6,0xa3,0xac,0xc7,0xeb,0xbc,0xb0,0xca,0xb1,0xb9,0xd8,0xd7,0xa2};
class Controller {
 public:
  Phase phase=Idle;Kind kind=None;Error error=Ok;
  unsigned reports=0,requested=0,accepted=0,uart_completed=0,failed=0,dropped=0,event_id=0,busy_seen=0;
  Result last_result=NoReply;
  void initialize(uint32_t value){boot_=value;initialized_=true;}
  void observe(uint32_t value,bool alarm,bool event,unsigned id){
    if(!alarm){
      episode_=false;
      if(pending_==Fall){pending_=None;++dropped;error=Cancelled;++reports;}
      if(kind==Fall&&phase==Gap){phase=Idle;error=Cancelled;++dropped;++reports;}
    }
    if(alarm&&event&&!episode_){episode_=true;queue(value,Fall,id);}
  }
  bool test(uint32_t value){return queue(value,Test,0);}
  bool recover(uint32_t value,unsigned id){return queue(value,Recovery,id);}
  bool unauthorized(uint32_t value,unsigned id){return queue(value,Unauthorized,id);}
  void cancel_assist(){if(pending_==Unauthorized)pending_=None;if(kind==Unauthorized&&phase!=Idle){phase=Idle;error=Cancelled;++dropped;++reports;}}
  void cancel_recovery(){
    if(pending_==Recovery)pending_=None;
    if(kind==Recovery&&phase!=Idle){phase=Idle;error=Cancelled;++dropped;++reports;}
  }
  template<class Hardware> void service(uint32_t value,Hardware& hw){
    if(!initialized_)return;
    if(phase==Idle){
      if(pending_==None)return;
      if(elapsed(value,queued_,3000)){kind=pending_;event_id=pending_id_;pending_=None;fail(Expired);return;}
      if(!elapsed(value,boot_,1000)||!elapsed(value,last_frame_,200))return;
      kind=pending_;event_id=pending_id_;part_=pending_part_;pending_=None;
      static const uint8_t stop[]={0xfd,0,1,2};
      last_result=hw.send(stop,4);last_frame_=value;
      if(last_result!=Ack41){fail(result_error());return;}
      phase=Gap;started_=value;++reports;return;
    }
    if(phase==Gap){
      // service timestamps precede a bounded <=65ms transfer: 265ms here
      // guarantees at least 200ms after that outgoing frame actually ended.
      if(!elapsed(value,started_,265))return;
      uint8_t frame[32]={0xfd,0,0,1,1};
      const uint8_t* text=kind==Fall?kFall:kind==Recovery?(part_?kRecoverySafety:kRecoveryIntro):kind==Unauthorized?(part_?kUnauthorizedEnd:kUnauthorizedIntro):kTest;
      unsigned bytes=kind==Fall?sizeof(kFall):kind==Recovery?(part_?sizeof(kRecoverySafety):sizeof(kRecoveryIntro)):kind==Unauthorized?(part_?sizeof(kUnauthorizedEnd):sizeof(kUnauthorizedIntro)):sizeof(kTest);
      frame[2]=uint8_t(bytes+2);for(unsigned n=0;n<bytes;++n)frame[n+5]=text[n];
      last_result=hw.send(frame,bytes+5);last_frame_=value;
      if(last_result!=Ack41){fail(result_error());return;}
      ++accepted;phase=Playing;started_=last_query_=value;missed_=0;busy_seen=0;++reports;return;
    }
    if(elapsed(value,started_,30000)){fail(PlaybackTimeout);return;}
    if(!elapsed(value,last_query_,500))return;
    last_query_=value;last_result=hw.query();last_frame_=value;++reports;
    if(last_result==Idle4F){
      phase=Idle;error=Ok;missed_=0;
      if((kind==Recovery||kind==Unauthorized)&&part_==0){
        // Wait for the module to finish the first part before sending the
        // second. Never enlarge the original 32-byte / 65-ms transport budget.
        pending_=kind;pending_id_=event_id;pending_part_=1;queued_=value;
      }else ++uart_completed;
      return;
    }
    if(last_result==Busy4E){busy_seen=1;missed_=0;return;}
    if(++missed_>=3)fail(StatusTimeout);
  }
 private:
  uint32_t boot_=0,queued_=0,started_=0,last_frame_=0,last_query_=0;
  unsigned pending_id_=0,missed_=0;Kind pending_=None;
  unsigned part_=0,pending_part_=0;
  bool initialized_=false,episode_=false;
  static bool elapsed(uint32_t value,uint32_t from,unsigned ms){return uint32_t(value-from)>=ms;}
  bool queue(uint32_t value,Kind kind,unsigned id){
    if(!initialized_||(kind==Test&&(pending_!=None||phase!=Idle))||(kind==Fall&&pending_==Fall)){
      ++dropped;++reports;return false;
    }
    if(pending_==Test)++dropped;
    pending_=kind;pending_id_=id;pending_part_=0;queued_=value;++requested;error=Ok;++reports;return true;
  }
  Error result_error()const{return last_result==Invalid?TransportInvalid:last_result==Nak45?Rejected:NoAcknowledgment;}
  void fail(Error value){error=value;++failed;phase=Idle;++reports;}
};
}
