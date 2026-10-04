"""Port the verified calibration loop to Sapphire MMIO; no hardware access."""
from pathlib import Path

root = Path(__file__).resolve().parents[2]
source = (root/'sensors/ir_thermal_hdmi_v3_20260930/firmware/main.cpp').read_text(encoding='utf-8')
source = source.replace('#include <math.h>', '#include <math.h>\n#include "bsp.h"\n#include "riscv.h"\n#include "intc.h"')
source = source.replace('static constexpr uint32_t HZ=148500000;', 'static constexpr uint32_t HZ=1000; // APB monotonic milliseconds, not CPU cycles.')
for old,new in [('0x10000000','0xF8103000'),('0x10001000','0xF8104000'),('0x20000000','0xF8106000'),('0x20001000','0xF8101020'),('0x20002000','0xF8101018')]:
    source=source.replace(old,new)
source=source.replace('static uint16_t ee[832],frame[834];', '''static volatile uint32_t *const SYSTEM=(volatile uint32_t*)0xF8100000;
static volatile uint32_t *const DISPLAY=(volatile uint32_t*)0xF8101000;
static volatile uint32_t *const SHT=(volatile uint32_t*)0xF8102000;
static uint16_t ee[832],frame[834];''')
source=source.replace('static void delay_ms(uint32_t ms){uint32_t t=ticks();while((uint32_t)(ticks()-t)<(HZ/1000)*ms){} }', '''// Sequence bracketing prevents mixed fields if a new SHT snapshot arrives during reads.
static void log_sht(){
 static uint32_t last=0;
 uint32_t seq,status,raw,t,h,stamp,again;
 do{seq=SHT[5];status=SHT[0];raw=SHT[1];t=SHT[2];stamp=SHT[3];h=SHT[4];again=SHT[5];}while(seq!=again);
 if(seq==last)return;last=seq;
 bsp_printf("SHT seq=%d status=%d raw=%x t_bcd=%x h_bcd=%x sample_ms=%d age_ms=%d\\r\\n",
  seq,status,raw,t,h,stamp,ticks()-stamp);
}
static void delay_ms(uint32_t ms){uint32_t t=ticks();while((uint32_t)(ticks()-t)<ms){log_sht();} }''')
begin=source.index('static int transact(')
end=source.index('static int read_words(',begin)
source=source[:begin]+'''static int transact(uint16_t address,int read,uint16_t data,unsigned words){
 // The bus engine always issues STOP after NACK. These sensor commands are
 // idempotent; retry the complete transaction and consume buffer only on success.
 for(unsigned attempt=0;attempt<3;attempt++){
  IO[1]=address;IO[2]=data;IO[3]=words;IO[0]=1|(read?2:0);
  uint32_t t=ticks();
  while(IO[0]&1)if((uint32_t)(ticks()-t)>HZ)return 4;
  int rc=IO[4];
  if(rc!=2||attempt==2)return rc;
  bsp_printf("IR_RETRY status=%d reg=%x read=%d attempt=%d ms=%d\\r\\n",rc,(unsigned)address,read,attempt+1,ticks());
  delay_ms(2);
 }
 return 2;
}
''' + source[end:]
source=source.replace('static void commit(){while(*COMMIT){} *COMMIT=1;while(*COMMIT){} }', '''static void wait_display(){
 uint32_t start=ticks();
 while((DISPLAY[1]&5)!=4){
  if((uint32_t)(ticks()-start)>2000){
   bsp_printf("FATAL display_timeout status=%x\\r\\n",DISPLAY[1]);
   for(;;)log_sht(); // Stop publishing; hardware subsequently marks IR stale.
  }
 }
}
static void commit(){
 wait_display();asm volatile("fence iorw, iorw" ::: "memory");
 *COMMIT=1;wait_display();
}''')
source=source.replace('static void show_status(unsigned s){RECORD[0]=s;RECORD[5]=frames;RECORD[6]=pages;commit();}', '''static void show_status(unsigned s){
 wait_display();RECORD[0]=s;RECORD[5]=frames;RECORD[6]=pages;commit();
 bsp_printf("IR_STATUS status=%d frames=%d pages=%d ms=%d display_seq=%d ack=%x\\r\\n",
  s,frames,pages,ticks(),DISPLAY[4],DISPLAY[1]);log_sht();
}''')
source=source.replace('frame[832]=control;delay_ms(1000);return 1;', '''frame[832]=control;
 bsp_printf("IR_INIT eeprom_double_read=OK calibration=OK control=%x bus_seq=%d\\r\\n",control,IO[6]);
 delay_ms(1000);return 1;''')
source=source.replace('for(int i=0;i<768;i++)IMAGE[i]=display.color(i);','wait_display();\n for(int i=0;i<768;i++)IMAGE[i]=display.color(i);')
source=source.replace('// Measure real board clock cycles, including software work, not simulated FPS.','// APB milliseconds include software work; this is not camera or HDMI FPS.')
source=source.replace('last_publish=now;published=true;\n commit();return 1;', '''uint32_t update_ms=published?now-last_publish:0;
 last_publish=now;published=true;
 commit();
 bsp_printf("IR seq=%d page=%d min_centi=%d max_centi=%d center_centi=%d ta_bcd=%x read_ms=%d calc_ms=%d update_ms=%d publish_ms=%d display_seq=%d ack=%x\\r\\n",
  frames,page,(int)display.minimum,(int)display.maximum,(int)display.filtered[12*32+16],bcd(ta),
  read_cycles,now-calc_start,update_ms,now,DISPLAY[4],DISPLAY[1]);
 log_sht();return 1;''')
source=source.replace('extern "C" int main(){\n for(;;){', '''extern "C" void trap(){
 bsp_printf("FATAL trap mcause=%x mepc=%x mtval=%x\\r\\n",csr_read(mcause),csr_read(mepc),csr_read(mtval));
 for(;;){};
}
extern "C" int main(){
 csr_write(mtvec,trap_entry); // Stage 1 uses polling; no TinyML IRQs enabled yet.
 bsp_printf("FUSION_BOOT stage=1 sensors_only version=00010000\\r\\n");
 uint32_t id=SYSTEM[0],version=SYSTEM[1],display_id=DISPLAY[0];
 if(id!=0x4d4d4631||version!=0x00010000||display_id!=0x46555331){
  bsp_printf("FATAL register_id_mismatch system=%x version=%x display=%x\\r\\n",id,version,display_id);
  for(;;){};
 }
 wait_display();
 bsp_printf("FUSION_READY system=%x display=%x ms=%d\\r\\n",id,display_id,ticks());
 for(;;){''')
target=root/'fusion/demo_multimodal/software/standalone/tinyml_pdti8/src/main.cc'
target.write_text(source,encoding='utf-8')
print(target)
