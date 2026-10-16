#include <cstdio>
#include <cassert>
#include "camera_auto.h"
int main(int argc,char **argv){
 if(argc>1){
  FILE *file=fopen(argv[1],"r");assert(file);unsigned ae,ac,clip,total,rs,rc,gs,gc,bs,bc,exp,gain,r,b;
  while(fscanf(file,"%u %u %u %u %u %u %u %u %u %u %u %u %u %u",&ae,&ac,&clip,&total,&rs,&rc,&gs,&gc,&bs,&bc,&exp,&gain,&r,&b)==14){
   CameraStats s={1,ae,ac,clip,total,rs,rc,gs,gc,bs,bc};
   CameraDecision d=camera_decide(s,exp,gain,r,b);
   printf("%u %u %u %u %u\n",d.exposure,d.gain_index,d.gain_r,d.gain_b,d.sensor_update);
  }
  fclose(file);return 0;
 }
 uint32_t a[18]={},camera[25]={};a[0]=0x41555431;camera[0]=0x43414d32;camera[1]=0x1f;
 unsigned expected[]={0x3e0780,0x3e0600,0x3e0920,0x3e0883,0x320fdc,0x320e05,0x3e02d0,0x3e01ba,0x3e0000};
 for(unsigned i=0;i<9;i++)camera[16+i]=expected[i];
 CameraAuto control(a,camera);control.step(0);assert(control.ready);
 control.step(1);assert(control.state==CameraAuto::Snapshot);
 a[1]=1;control.step(2);assert(control.state==CameraAuto::Snapshot);
 a[1]=0;a[2]=1;a[3]=100*16320;a[11]=16320;a[12]=32640;
 a[5]=100*8160;a[6]=8160;a[7]=100*16320;a[8]=16320;a[9]=100*8160;a[10]=8160;
 control.step(3);assert(control.state==CameraAuto::FrameWait);
 a[13]=1;control.step(4);assert(control.state==CameraAuto::BusStart);
 unsigned now=5;
 for(unsigned command=0;command<10;command++){
  control.step(now++);assert(control.state==CameraAuto::BusWait);
  unsigned index=command>=5?command-5:command;
  assert(a[14]==((command>=5?1u<<24:0)|(unsigned(camera_expected(index,2989,74))<<16)|camera_register(index)));
  a[1]=2;control.step(now++);assert(control.state==CameraAuto::BusWait);
  a[1]=0;a[16]=0x100|camera_expected(index,2989,74);control.step(now++);
  if(command<9){assert(control.state==CameraAuto::Gap);control.step(now++);assert(control.state==CameraAuto::BusStart);}
 }
 assert(control.updates==1&&control.gain_index==74&&control.exposure==2989);
 for(unsigned frame=2;frame<5;frame++){a[13]=frame;control.step(now++);assert(control.state==CameraAuto::WaitFrames);}
 a[13]=5;control.step(now++);assert(control.state==CameraAuto::Snapshot);
 // No acknowledgement stops auto; the service returns and leaves video controls alone.
 a[1]=1;control.step(now+501);assert(control.fault==0x21&&control.state==CameraAuto::Stopped);
 CameraAuto fault(a,camera);a[1]=0;fault.step(0);fault.state=CameraAuto::BusWait;fault.entered=0;a[16]=0x200;
 fault.step(1);assert(fault.fault==2&&fault.state==CameraAuto::Stopped);
 CameraAuto readback(a,camera);readback.step(0);readback.state=CameraAuto::BusWait;readback.command=5;readback.next.exposure=2989;a[16]=0x1ff;
 readback.step(1);assert(readback.fault==3);
 CameraAuto mode(a,camera);camera[16]^=1;mode.step(0);assert(mode.fault==0x10);
 // AWB commit remains pending through active pixels, then commits both values.
 camera[16]^=1;CameraAuto wb(a,camera);wb.step(0);wb.state=CameraAuto::Snapshot;
 a[2]=2;a[3]=60*16320;a[5]=30*8160;a[7]=60*16320;a[9]=90*8160;a[1]=0;
 wb.step(1);assert(wb.state==CameraAuto::WbWait&&wb.r==256&&wb.b==256);
 a[1]=4;wb.step(2);assert(wb.r==256&&wb.b==256);
 a[1]=0;wb.step(3);assert(wb.r==288&&wb.b==246);
 // Frame counter wrap is handled by uint16 distance.
 wb.state=CameraAuto::WaitFrames;wb.since=65534;wb.settle=4;wb.entered=0;a[13]=1;
 wb.step(4);assert(wb.state==CameraAuto::WaitFrames);a[13]=2;wb.step(5);assert(wb.state==CameraAuto::Snapshot);
 puts("PASS CPU scheduling: ten checked I2C ops, settle4, timeout/NACK/readback/mode freeze, frame-safe WB, counter wrap");
}
