#include "compat_runtime.h"
#include "port.h"

// Existing FPGA defines.v: STANDARD=2, input parallelism 4, output parallelism 1.
int conv_depthw_mode=2, conv_depthw_lite_parallel=4;
#if defined(YOLO_CACHE32)
int add_mode=0, mul_mode=0, tinyml_cache=1;
#elif defined(YOLO_REALTIME)
int add_mode=2, mul_mode=0, tinyml_cache=1;
#elif defined(YOLO_DSP16)
int add_mode=0, mul_mode=0, tinyml_cache=1;
#elif defined(YOLO_DSP8X4)
int add_mode=2, mul_mode=0, tinyml_cache=1;
#else
int add_mode=2, mul_mode=2, tinyml_cache=1;
#endif
int fc_mode=0, lr_mode=0, min_max_mode=0;
const char* layer_mode="SOFTWARE";
extern "C" void compat_trap_entry();
namespace {
volatile uint32_t* reg(uint32_t address) { return reinterpret_cast<volatile uint32_t*>(address); }
uint64_t mtime() {
  auto* timer=reg(0xf8b0bff8u);
  uint32_t high,low,again;
  do { high=timer[1]; low=timer[0]; again=timer[1]; } while(high!=again);
  return (static_cast<uint64_t>(high)<<32)|low;
}
void deadline(uint64_t value) {
  auto* compare=reg(0xf8b04000u);
  compare[1]=0xffffffffu; compare[0]=static_cast<uint32_t>(value); compare[1]=value>>32;
  asm volatile("fence iorw, iorw" ::: "memory");
}
}
void cache_sync() {
  asm volatile("fence rw, rw\n.word 0x0000500f\nfence rw, rw" ::: "memory");
}
void watchdog_arm() { deadline(mtime()+1000000000ull); }
void watchdog_disarm() { deadline(~uint64_t(0)); }
void hardware_initialize() {
  watchdog_disarm();
  *reg(0xf8e00000u)=0;                 // PLIC CPU0 threshold.
  *reg(0xf8c00000u+16*4)=1;            // Accelerator interrupt priority.
  *reg(0xf8c02000u)=1u<<16;            // Only accelerator external interrupt.
  asm volatile("csrw mtvec, %0" :: "r"(compat_trap_entry));
  asm volatile("csrs mie, %0" :: "r"((1u<<11)|(1u<<7)));
  asm volatile("csrsi mstatus, 8");
}
extern "C" void compat_trap() {
  uint32_t cause,pc,value;
  asm volatile("csrr %0, mcause":"=r"(cause));
  asm volatile("csrr %0, mepc":"=r"(pc));
  asm volatile("csrr %0, mtval":"=r"(value));
  if(cause==0x8000000bu) {
    for(;;) {
      const unsigned irq=*reg(0xf8e00004u);
      if(!irq) break;
      if(irq!=16) compat_fatal("unexpected_external_interrupt");
      ops_drv_intr();
      *reg(0xf8e00004u)=irq;
    }
    return;
  }
  if(cause==0x80000007u) { watchdog_disarm(); compat_fatal("accelerator_timeout_10s"); }
  log_line("YOLO2_TRAP cause=%08x pc=%08x value=%08x node=%u",cause,pc,value,current_node);
  compat_fatal("trap");
}
