#pragma once
#include <cstdint>
// SC431HAI datasheet sections 2.5 (group hold) and 2.8 (VTS).
// Same pixel/line clocks: VTS 1500 -> ~30 fps; VTS 9000 -> ~5 fps.
// This shares the runtime I2C mailbox with AE/AWB; caller must quiesce AE first.
struct CameraRate {
 enum State {Idle,Start,Wait,Gap,Apply,Settle,Failed} state=Idle;
 bool low=false,target=false;unsigned command=0,entered=0,frame=0,retries=0;uint8_t fault=0;
 unsigned response=0,bus_status=0,failed_command=0,failed_response=0;
 static const unsigned kCommandGuardMs=3,kRecoveryMs=5000;
 static uint16_t address(unsigned n){return n==0||n==3?0x3812:n==1||n==4?0x320e:0x320f;}
 static uint8_t value(unsigned n,bool slow){return n==0?0:n==3?0x30:(n==1||n==4)?(slow?0x23:0x05):(slow?0x28:0xdc);}
 bool settled()const{return state==Idle;}
 bool busy()const{return state!=Idle&&state!=Failed;}
 void request(bool slow,unsigned now,unsigned frames){if(state==Idle&&low!=slow){target=slow;command=0;retries=0;fault=0;state=Start;entered=now;frame=frames;}}
 void fail(unsigned code,unsigned now){
  fault=code;failed_command=command;failed_response=response;
  // A partial group-hold write must not leave the camera held indefinitely.
  // Retry the entire sequence, including release and readback, at normal VTS.
  if(retries<2){++retries;target=false;command=0;state=Gap;entered=now;}
  else {state=Failed;entered=now;}
 }
 void step(unsigned now,volatile uint32_t* a){
  const unsigned status=a[1];
  switch(state){
   case Idle:case Failed:return;
   case Start:
    if(!(status&10)){a[14]=(command>=4?1u<<24:0)|(unsigned(value(command,target))<<16)|address(command);a[15]=1;state=Wait;entered=now;}
    else if(unsigned(now-entered)>500)fail(1,now);return;
   case Wait:
    // A mailbox write crosses CPU/ISP clock domains. Do not accept the held
    // response of the previous operation before this transaction can finish.
    // Wait for BOTH request ACK and the physical bus to be idle, and sample
    // the response once. Fast operator callbacks may be only microseconds apart.
    if(unsigned(now-entered)<kCommandGuardMs)return;
    bus_status=status;
    if(status&10){if(unsigned(now-entered)>500)fail(2,now);return;}
    response=a[16];
    if((response>>8)!=1){fail(3,now);return;}
    if(command>=4&&uint8_t(response)!=value(command,target)){fail(4,now);return;}
    if(command==5){state=Settle;frame=a[13];entered=now;}
    else if(command==3){state=Apply;frame=a[13];entered=now;}
    else{++command;state=Gap;entered=now;}return;
   case Gap:if(unsigned(now-entered)>=1){state=Start;entered=now;}return;
   case Apply:
    // Group release can take effect at a sensor frame boundary. Read back
    // VTS only after two new SOFs, rather than checking the old shadow value.
    if(uint16_t(a[13]-frame)>=2){command=4;state=Start;entered=now;return;}
    if(unsigned(now-entered)>2000)fail(5,now);return;
   case Settle:
    if(uint16_t(a[13]-frame)>=2){low=target;fault=0;state=Idle;return;}
    if(unsigned(now-entered)>2000)fail(5,now);return;
  }
 }
 void retry_recovery(unsigned now,unsigned frames){
  if(state==Failed&&unsigned(now-entered)>=kRecoveryMs){
   target=false;command=0;retries=0;state=Start;entered=now;frame=frames;
  }
 }
};
