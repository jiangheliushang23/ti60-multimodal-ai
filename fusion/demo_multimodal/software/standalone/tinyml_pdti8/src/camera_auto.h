#pragma once
#include "camera_control.h"

// One short service call per IR scheduling slice. No I2C or frame busy waits.
struct CameraAuto {
 volatile uint32_t *a,*camera;
 enum State {Boot,WaitFrames,Snapshot,FrameWait,BusStart,BusWait,Gap,WbWait,Stopped} state;
 uint16_t exposure,r,b,since,last_sequence;
 uint8_t gain_index,settle,command,fault;
 uint32_t entered,updates;
 CameraStats stats;
 CameraDecision next;
 bool fresh,ready;
 CameraAuto(volatile uint32_t *registers,volatile uint32_t *old_camera):
  a(registers),camera(old_camera),state(Boot),exposure(2989),r(256),b(256),since(0),last_sequence(0),
  gain_index(82),settle(0),command(0),fault(0),entered(0),updates(0),stats{},next{},fresh(false),ready(false){}
 void stop(uint8_t code){fault=code;fresh=true;state=Stopped;}
 void enter(State s,uint32_t now){state=s;entered=now;}
 void step(uint32_t now){
  uint16_t f=a[13];uint32_t status=a[1];
  switch(state){
  case Boot:
   if(a[0]!=0x41555431||camera[0]!=0x43414d32){stop(0x11);break;}
   if((camera[1]&0xff)!=0x1f){if(now>12000)stop(0x12);break;}
   // Old readback order: digital low/high, analog low/high, VTS low/high,
   // exposure low/middle/high. Freeze if sensor mode/initial controls differ.
   {const uint32_t expected[]={0x3e0780,0x3e0600,0x3e0920,0x3e0883,0x320fdc,0x320e05,0x3e02d0,0x3e01ba,0x3e0000};
    for(unsigned i=0;i<9;i++)if(camera[16+i]!=expected[i]){stop(0x10);return;}}
   ready=true;since=f;settle=0;enter(WaitFrames,now);break;
  case WaitFrames:
   if((uint16_t)(f-since)>=settle){a[2]=1;enter(Snapshot,now);}
   else if(now-entered>500)stop(0x20);
   break;
  case Snapshot:
   if(status&1){if(now-entered>500)stop(0x21);break;}
   stats={static_cast<uint16_t>(a[2]),a[3],a[11],a[4],a[12],a[5],a[6],a[7],a[8],a[9],a[10]};
   if(stats.ae_count!=16320||stats.samples!=32640){stop(0x10);break;}
   if(stats.sequence==last_sequence){stop(0x22);break;}
   last_sequence=stats.sequence;next=camera_decide(stats,exposure,gain_index,r,b);fresh=true;
   since=f;
   if(next.sensor_update){command=0;enter(FrameWait,now);}
   else if(next.gain_r!=r||next.gain_b!=b){
    a[17]=uint32_t(next.gain_b)<<16|next.gain_r;enter(WbWait,now);
   }else{settle=1;enter(WaitFrames,now);}
   break;
  case FrameWait:
   if(f!=since)enter(BusStart,now);
   else if(now-entered>500)stop(0x20);
   break;
  case BusStart:
   if(!(status&10)){
    unsigned index=command>=5?command-5:command;
    a[14]=(command>=5?1u<<24:0)|(uint32_t(camera_expected(index,next.exposure,next.gain_index))<<16)|camera_register(index);
    a[15]=1;enter(BusWait,now);
   }else if(now-entered>250)stop(0x23);
   break;
  case BusWait:
   if(status&2){if(now-entered>250)stop(0x24);break;}
   {uint32_t response=a[16];unsigned index=command>=5?command-5:command;
    if((response>>8)!=1){stop(response>>8?response>>8:0x25);break;}
    if(command>=5&&uint8_t(response)!=camera_expected(index,next.exposure,next.gain_index)){stop(3);break;}}
   if(command==9){
    exposure=next.exposure;gain_index=next.gain_index;updates++;fresh=true;
    since=f;settle=4;enter(WaitFrames,now);
   }else{command++;enter(Gap,now);}
   break;
  case Gap:if(now-entered>=1)enter(BusStart,now);break;
  case WbWait:
   if(!(status&4)){r=next.gain_r;b=next.gain_b;fresh=true;since=f;settle=1;enter(WaitFrames,now);}
   else if(now-entered>500)stop(0x26);
   break;
  case Stopped:break;
  }
 }
};
