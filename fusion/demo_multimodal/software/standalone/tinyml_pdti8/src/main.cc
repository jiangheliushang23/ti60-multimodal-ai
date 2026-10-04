#include <stdint.h>
#include <math.h>
#include "bsp.h"
#include "riscv.h"
#include "intc.h"
#include "MLX90640_API.h"
#include "thermal_display.h"

// All floating-point operations execute on the FPGA's RV32IM core using libgcc/libm.
// Adaptive display scale, independent of calibration. Emissivity/reflection assumptions
// follow the vendor demonstration; they are not a claim of calibrated system accuracy.
static constexpr uint32_t HZ=1000; // APB monotonic milliseconds, not CPU cycles.
static volatile uint32_t *const IO=(volatile uint32_t*)0xF8103000;
static volatile uint32_t *const BUFFER=(volatile uint32_t*)0xF8104000;
static volatile uint32_t *const IMAGE=(volatile uint32_t*)0xF8106000;
static volatile uint32_t *const RECORD=(volatile uint32_t*)0xF8101020;
static volatile uint32_t *const COMMIT=(volatile uint32_t*)0xF8101018;
static volatile uint32_t *const SYSTEM=(volatile uint32_t*)0xF8100000;
static volatile uint32_t *const DISPLAY=(volatile uint32_t*)0xF8101000;
static volatile uint32_t *const SHT=(volatile uint32_t*)0xF8102000;
static volatile uint32_t *const CAMERA=(volatile uint32_t*)0xF8105000;
static uint16_t ee[832],frame[834];
static paramsMLX90640 params;
static float temperatures[768];
static int16_t raw_centi[768];
static ThermalDisplay display;
static uint8_t bad[768];
static uint32_t frames=0,pages=0;
static uint32_t read_cycles=0,last_publish=0;
static bool published=false;

static uint32_t ticks(){return IO[5];}
static void log_camera(){
 static uint32_t last=0;static bool registers_logged=false;uint32_t now=ticks();
 if((uint32_t)(now-last)<1000)return;last=now;
 if(CAMERA[0]!=0x43414d32)return;
 bsp_printf("CAM ms=%d setup=%x good=%d bad=%d period_ticks=%d overflow=%d published=%d dropped=%d werr=%d rerr=%d underflow=%d seq=%d pixels=%d format=%x de_runs=%d packing=%x\r\n",
  now,CAMERA[1],CAMERA[2],CAMERA[3],CAMERA[4],CAMERA[5],CAMERA[6],CAMERA[7],CAMERA[8],CAMERA[9],CAMERA[10],CAMERA[11],CAMERA[12],CAMERA[13],CAMERA[14],CAMERA[15]);
 if(!registers_logged&&(CAMERA[1]&0xff)==0x1f){
  bsp_printf("CAM_REGS r0=%x r1=%x r2=%x r3=%x r4=%x r5=%x r6=%x r7=%x r8=%x\r\n",
   CAMERA[16],CAMERA[17],CAMERA[18],CAMERA[19],CAMERA[20],CAMERA[21],CAMERA[22],CAMERA[23],CAMERA[24]);
  registers_logged=true;
 }
}
// Sequence bracketing prevents mixed fields if a new SHT snapshot arrives during reads.
static void log_sht(){
 log_camera();
 static uint32_t last=0;
 uint32_t seq,status,raw,t,h,stamp,again;
 seq=SHT[5];status=SHT[0];raw=SHT[1];t=SHT[2];stamp=SHT[3];h=SHT[4];again=SHT[5];
 if(seq!=again)return;
 if(seq==last)return;last=seq;
 bsp_printf("SHT seq=%d status=%d raw=%x t_bcd=%x h_bcd=%x sample_ms=%d age_ms=%d seq_hex=%x seq_check=%x\r\n",
  seq,status,raw,t,h,stamp,ticks()-stamp,seq,again);
}

static uint32_t bcd(float x){
 int q=(int)(fabsf(x)*100.0f+0.5f);uint32_t b=x<0?0x80000000u:0;
 for(int i=0;i<5;i++){b|=(q%10)<<(i*4);q/=10;}return b;
}
static uint32_t milliseconds(uint32_t n){
 uint32_t value=0;if(n>9999)n=9999;
 for(int i=0;i<4;i++){value|=(n%10)<<(4*i);n/=10;}return value;
}
static bool finite_range(float f,float lo,float hi){return isfinite(f)&&f>=lo&&f<=hi;}

// One hardware transaction at a time. Polling never waits inside a service call.
struct BusRequest {
 bool active,retry_wait;
 uint16_t address,data,*destination;
 unsigned words,attempt;
 uint32_t started,retry_started;
} bus;
static void start_bus(){
 IO[1]=bus.address;IO[2]=bus.data;IO[3]=bus.words;
 IO[0]=1|(bus.destination?2:0);bus.started=ticks();
}
static void read_words(uint16_t address,unsigned words,uint16_t *destination){
 bus={true,false,address,0,destination,words,0,0,0};start_bus();
}
static void write_word(uint16_t address,uint16_t value){
 bus={true,false,address,value,nullptr,1,0,0,0};start_bus();
}
// 0 means pending; 1 success; other values preserve the existing hardware status.
static int poll_bus(){
 uint32_t now=ticks();
 if(bus.retry_wait){
  if((uint32_t)(now-bus.retry_started)<2)return 0;
  bus.retry_wait=false;start_bus();return 0;
 }
 if(IO[0]&1){
  if((uint32_t)(now-bus.started)<=HZ)return 0;
  bus.active=false;return 4;
 }
 int rc=IO[4];
 if(rc==2&&bus.attempt<2){
  bsp_printf("IR_RETRY status=%d reg=%x read=%d attempt=%d ms=%d\r\n",
   rc,(unsigned)bus.address,bus.destination?1:0,bus.attempt+1,now);
  bus.attempt++;bus.retry_wait=true;bus.retry_started=ticks();return 0;
 }
 bus.active=false;
 if(rc==1&&bus.destination)
  for(unsigned i=0;i<bus.words;i++)bus.destination[i]=(uint16_t)BUFFER[i];
 return rc;
}

enum class IrState {
 Reset,InitDelay,EepromFirst,EepromSecond,ControlRead,ControlWrite,ControlCheck,
 Warmup,PollStart,PollDone,PollDelay,ClearDone,FrameDone,CheckDone,
 Calculate,Prepare,PublishWait,CommitWait,Recover,Stopped
};
static IrState state=IrState::Reset,after_publish=IrState::Reset;
static uint16_t control,status_word,control_check;
static unsigned overruns=0,pixel_cursor=0,publish_status=0;
static uint32_t wait_started=0,poll_started=0,read_started=0,calc_started=0;
static uint32_t calc_ms=0,update_ms=0,publish_ms=0;
static float ambient=0;
static void show_status(unsigned status,IrState next){
 publish_status=status;after_publish=next;wait_started=ticks();state=IrState::PublishWait;
}
static void fail(unsigned code){
 // Old temperatures must not be reused across a failed acquisition/reinitialization.
 pages=0;published=false;show_status(code,IrState::Recover);
}
static bool check_parameters(){
 for(int i=0;i<832;i++)if(ee[i]!=frame[i])return false;
 if(!(ee[51]&0xff00)||!(ee[50]&0x03ff)||!ee[48])return false;
 if(MLX90640_ExtractParameters(ee,&params)!=0)return false;
 if(params.kVdd==0||params.KtPTAT==0||params.gainEE==0)return false;
 for(int i=0;i<768;i++)bad[i]=0;
 for(int j=0;j<5;j++){
  if(params.brokenPixels[j]<768)bad[params.brokenPixels[j]]=1;
  if(params.outlierPixels[j]<768)bad[params.outlierPixels[j]]=1;
 }
 for(int i=0;i<768;i++)if(!bad[i]&&params.alpha[i]==0)return false;
 return true;
}
static bool prepare_image(){
 unsigned page=frame[833];
 for(int i=0;i<768;i++){
  unsigned pattern=(i/32)&1;if(frame[832]&0x1000)pattern^=i&1;
  if(pattern==page&&!bad[i]&&!finite_range(temperatures[i],-40,300))return false;
 }
 pages|=1u<<page;frames++;
 if(pages!=3){show_status(0,IrState::PollStart);return true;}
 for(int i=0;i<768;i++)if(bad[i]){
  float sum=0;int n=0;
  int neighbours[4]={i%32?i-1:-1,i%32<31?i+1:-1,i>=32?i-32:-1,i<736?i+32:-1};
  for(int j:neighbours)if(j>=0&&!bad[j]){sum+=temperatures[j];n++;}
  if(!n)return false;temperatures[i]=sum/n;
 }
 for(int i=0;i<768;i++){
  float t=temperatures[i];if(!finite_range(t,-40,300))return false;
  raw_centi[i]=(int16_t)(t*100.0f+(t<0?-0.5f:0.5f));
 }
 display.update(raw_centi,page,frame[832]&0x1000,bad);
 show_status(1,IrState::PollStart);return true;
}
static bool display_ready(){
 if((DISPLAY[1]&5)==4)return true;
 if((uint32_t)(ticks()-wait_started)>2000){
  bsp_printf("FATAL display_timeout status=%x\r\n",DISPLAY[1]);state=IrState::Stopped;
 }
 return false;
}
static void ir_step(){
 if(bus.active){
  int rc=poll_bus();if(rc==0)return;
  if(rc!=1){fail(rc);return;}
 }
 switch(state){
 case IrState::Reset:
  pages=0;published=false;display.reset();show_status(8,IrState::InitDelay);break;
 case IrState::InitDelay:
  if((uint32_t)(ticks()-wait_started)<1000)break;
  read_words(0x2400,832,ee);state=IrState::EepromFirst;break;
 case IrState::EepromFirst:
  read_words(0x2400,832,frame);state=IrState::EepromSecond;break;
 case IrState::EepromSecond:
  // EEPROM extraction remains a one-time initialization/recovery calculation.
  if(!check_parameters()){fail(6);break;}
  read_words(0x800d,1,&control);state=IrState::ControlRead;break;
 case IrState::ControlRead:
  control=(control&0xfc70)|0x0181;
  write_word(0x800d,control);state=IrState::ControlWrite;break;
 case IrState::ControlWrite:
  read_words(0x800d,1,&control_check);state=IrState::ControlCheck;break;
 case IrState::ControlCheck:
  if(control_check!=control){fail(6);break;}
  frame[832]=control;
  bsp_printf("IR_INIT eeprom_double_read=OK calibration=OK control=%x bus_seq=%d\r\n",control,IO[6]);
  wait_started=ticks();state=IrState::Warmup;break;
 case IrState::Warmup:
  if((uint32_t)(ticks()-wait_started)>=1000)state=IrState::PollStart;
  break;
 case IrState::PollStart:
  poll_started=ticks();overruns=0;
  read_words(0x8000,1,&status_word);state=IrState::PollDone;break;
 case IrState::PollDone:
  if(status_word&8){write_word(0x8000,0x0030);state=IrState::ClearDone;}
  else if((uint32_t)(ticks()-poll_started)>3*HZ)fail(5);
  else{wait_started=ticks();state=IrState::PollDelay;}
  break;
 case IrState::PollDelay:
  if((uint32_t)(ticks()-wait_started)<2)break;
  read_words(0x8000,1,&status_word);state=IrState::PollDone;break;
 case IrState::ClearDone:
  read_started=ticks();read_words(0x0400,832,frame);state=IrState::FrameDone;break;
 case IrState::FrameDone:
  read_cycles=ticks()-read_started;
  read_words(0x8000,1,&status_word);state=IrState::CheckDone;break;
 case IrState::CheckDone:
  if(status_word&8){
   if(++overruns>=5){fail(3);break;}
   write_word(0x8000,0x0030);state=IrState::ClearDone;break;
  }
  if(status_word&6){fail(7);break;}
  frame[833]=status_word&1;calc_started=ticks();
  ambient=MLX90640_GetTa(frame,&params);
  if(!finite_range(MLX90640_GetVdd(frame,&params),2.6f,3.7f)||
     !finite_range(ambient,-40,85)||(int16_t)frame[778]==0){fail(7);break;}
  pixel_cursor=0;state=IrState::Calculate;break;
 case IrState::Calculate:
  // At most 32 pixel positions per call, preserving the vendor's operation order.
  MLX90640_CalculateToRange(frame,&params,0.95f,ambient-8.0f,temperatures,pixel_cursor,pixel_cursor+32);
  pixel_cursor+=32;
  if(pixel_cursor==768)state=IrState::Prepare;
  break;
 case IrState::Prepare:
  if(!prepare_image())fail(7);
  break;
 case IrState::PublishWait:
  if(!display_ready())break;
  RECORD[0]=publish_status;RECORD[5]=frames;RECORD[6]=pages;
  if(publish_status==1){
   for(int i=0;i<768;i++)IMAGE[i]=display.color(i);
   RECORD[1]=bcd(display.minimum/100.0f);RECORD[2]=bcd(display.maximum/100.0f);
   RECORD[3]=bcd(display.filtered[12*32+16]/100.0f);RECORD[4]=bcd(ambient);
   RECORD[7]=bcd(display.low/100.0f);RECORD[8]=bcd(display.high/100.0f);RECORD[9]=display.hotspot;
#ifdef THERMAL_FIXED_SCALE
   RECORD[10]=0;
#else
   RECORD[10]=1;
#endif
   publish_ms=ticks();calc_ms=publish_ms-calc_started;
   update_ms=published?publish_ms-last_publish:0;last_publish=publish_ms;published=true;
   RECORD[11]=milliseconds(read_cycles);RECORD[12]=milliseconds(calc_ms);RECORD[13]=milliseconds(update_ms);
  }
  asm volatile("fence iorw, iorw" ::: "memory");*COMMIT=1;
  wait_started=ticks();state=IrState::CommitWait;break;
 case IrState::CommitWait:
  if(!display_ready())break;
  if(publish_status==1)
   bsp_printf("IR seq=%d page=%d min_centi=%d max_centi=%d center_centi=%d ta_bcd=%x read_ms=%d calc_ms=%d update_ms=%d publish_ms=%d display_seq=%d ack=%x\r\n",
    frames,(unsigned)frame[833],(int)display.minimum,(int)display.maximum,(int)display.filtered[12*32+16],
    bcd(ambient),read_cycles,calc_ms,update_ms,publish_ms,DISPLAY[4],DISPLAY[1]);
  else
   bsp_printf("IR_STATUS status=%d frames=%d pages=%d ms=%d display_seq=%d ack=%x\r\n",
    publish_status,frames,pages,ticks(),DISPLAY[4],DISPLAY[1]);
  wait_started=ticks();state=after_publish;break;
 case IrState::Recover:
  if((uint32_t)(ticks()-wait_started)>=1000)state=IrState::Reset;
  break;
 case IrState::Stopped:break;
 }
}
extern "C" void trap(){
 bsp_printf("FATAL trap mcause=%x mepc=%x mtval=%x\r\n",csr_read(mcause),csr_read(mepc),csr_read(mtval));
 for(;;){};
}
extern "C" int main(){
 csr_write(mtvec,trap_entry);
 bsp_printf("FUSION_BOOT stage=2 camera_and_sensors version=00010000 ir_service=1\r\n");
 uint32_t id=SYSTEM[0],version=SYSTEM[1],display_id=DISPLAY[0];
 if(id!=0x4d4d4631||version!=0x00010000||display_id!=0x46555331){
  bsp_printf("FATAL register_id_mismatch system=%x version=%x display=%x\r\n",id,version,display_id);
  for(;;){};
 }
 bsp_printf("FUSION_READY system=%x display=%x ms=%d\r\n",id,display_id,ticks());
 uint32_t last_report=ticks(),steps=0,max_step=0,max_slice=0,max_init=0;
 for(;;){
  log_sht(); // Also services camera diagnostics during bus waits and calculation slices.
  uint32_t start=ticks();IrState previous=state;ir_step();uint32_t elapsed=ticks()-start;
  steps++;
  if(previous==IrState::EepromSecond){if(elapsed>max_init)max_init=elapsed;}
  else if(elapsed>max_step)max_step=elapsed;
  if(previous==IrState::Calculate&&elapsed>max_slice)max_slice=elapsed;
  if((uint32_t)(ticks()-last_report)>=5000){
   bsp_printf("IR_SERVICE steps=%d max_step_ms=%d max_slice_ms=%d max_init_ms=%d ms=%d\r\n",
    steps,max_step,max_slice,max_init,ticks());
   last_report=ticks();steps=0;max_step=0;max_slice=0;max_init=0;
  }
 }
}
