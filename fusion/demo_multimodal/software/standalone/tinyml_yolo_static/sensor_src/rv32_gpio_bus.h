#pragma once
#include <stdint.h>

namespace voice_gpio {
struct Rv32Bus {
  // The adapter owns this flag only during the existing service() safe point.
  bool at_safe_point=false;
  bool clock_read_valid=false;
  static volatile uint32_t* gpio(){return reinterpret_cast<volatile uint32_t*>(0xf8105300u);}
  static void fence(){asm volatile("fence iorw,iorw":::"memory");}
  uint64_t ticks(){
    volatile uint32_t* timer=reinterpret_cast<volatile uint32_t*>(0xf8b0bff8u);
    uint32_t high,low,again;
    // Bounded coherent read; inconsistent/stalled timer then fails wait().
    clock_read_valid=false;
    for(unsigned n=0;n<8;++n){
      high=timer[1];low=timer[0];again=timer[1];
      if(high==again){clock_read_valid=true;return (uint64_t(high)<<32)|low;}
    }
    return 0;
  }
  bool timer_valid(){return clock_read_valid;}
  unsigned inputs(){fence();return gpio()[2];}
  void outputs(unsigned value){fence();gpio()[1]=value;fence();}
  bool safe_point(){return at_safe_point;}
  uint32_t disable_irq(){
    uint32_t previous;
    asm volatile("csrrci %0,mstatus,8":"=r"(previous)::"memory");
    return previous;
  }
  void restore_irq(uint32_t previous){
    // Restore only the saved MIE bit, preserving other current mstatus fields.
    if(previous&8)asm volatile("csrsi mstatus,8":::"memory");
    else asm volatile("csrci mstatus,8":::"memory");
  }
};
}
