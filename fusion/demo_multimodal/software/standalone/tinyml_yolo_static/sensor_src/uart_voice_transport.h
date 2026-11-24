#pragma once
#include <stdint.h>

// VGP1 GPIO UART: TX=bit1 (module RXD), RX=bit0 (module TXD).
// CS stays high, CLK stays low. RDY is disconnected and never used.
namespace voice_uart {
enum Result { Ack41, Nak45, Busy4E, Idle4F, NoReply, Invalid };
template<class Bus> class Transport {
 public:
  explicit Transport(Bus& bus):bus_(bus){}
  void initialize(){bus_.outputs(6);}
  Result send(const uint8_t* bytes,unsigned size){return exchange(bytes,size,false);}
  Result query(){static const uint8_t frame[]={0xfd,0,1,0x21};return exchange(frame,4,true);}
  unsigned commands()const{return commands_;}
  uint64_t last_duration_ticks()const{return duration_;}
  bool duration_valid()const{return valid_;}
  unsigned last_rx()const{return last_rx_;}
  unsigned framing_errors()const{return framing_;}
  unsigned max_poll_gap_ticks()const{return max_gap_;}
 private:
  static const uint32_t kBit=10417,kLimit=6500000,kReply=3000000;
  Bus& bus_;
  uint64_t start_=0,due_=0,previous_=0,duration_=0;
  unsigned commands_=0,last_rx_=0,framing_=0,max_gap_=0,rx_state_=0,rx_bit_=0,rx_value_=0;
  bool timer_ok_=true,valid_=false,query_=false;
  Result reply_=NoReply;
  uint64_t now(){uint64_t value=bus_.ticks();timer_ok_=timer_ok_&&bus_.timer_valid();return value;}
  bool bounded(uint64_t value){return timer_ok_&&value>=start_&&value-start_<kLimit;}
  void poll(uint64_t value){
    unsigned high=bus_.inputs()&1;
    if(previous_&&value>=previous_&&value-previous_>max_gap_)max_gap_=unsigned(value-previous_);
    previous_=value;
    if(!rx_state_){if(!high){rx_state_=1;rx_bit_=rx_value_=0;due_=value+kBit+kBit/2;}return;}
    if(value<due_)return;
    if(value-due_>=kBit/2){++framing_;rx_state_=0;return;}
    if(rx_state_==1){rx_value_|=high<<rx_bit_;due_+=kBit;if(++rx_bit_==8)rx_state_=2;return;}
    if(!high)++framing_;
    else {
      last_rx_=rx_value_;
      if(query_){if(rx_value_==0x4e)reply_=Busy4E;else if(rx_value_==0x4f)reply_=Idle4F;else if(rx_value_==0x45)reply_=Nak45;}
      else {if(rx_value_==0x41)reply_=Ack41;else if(rx_value_==0x45)reply_=Nak45;}
    }
    rx_state_=0;
  }
  bool wait_until(uint64_t target){
    for(unsigned n=0;n<1000000;++n){uint64_t value=now();if(!bounded(value))return false;poll(value);if(value>=target)return true;}
    timer_ok_=false;return false;
  }
  Result exchange(const uint8_t* bytes,unsigned size,bool query){
    valid_=false;duration_=0;last_rx_=framing_=max_gap_=rx_state_=rx_bit_=rx_value_=0;previous_=0;
    reply_=NoReply;query_=query;timer_ok_=true;
    if(!bus_.safe_point()||!size||size>32)return Invalid;
    const uint32_t saved=bus_.disable_irq();
    start_=now();bool ok=timer_ok_&&(bus_.inputs()&1);uint64_t edge=start_;
    for(unsigned i=0;ok&&i<size;++i){
      // Each write occurs at an absolute bit deadline, limiting cumulative drift.
      bus_.outputs(4);edge+=kBit;ok=wait_until(edge);
      for(unsigned bit=0;ok&&bit<8;++bit){bus_.outputs((bytes[i]&(1u<<bit))?6:4);edge+=kBit;ok=wait_until(edge);}
      if(ok){bus_.outputs(6);edge+=kBit;ok=wait_until(edge);}
    }
    bus_.outputs(6);
    const uint64_t tx_end=now();
    if(ok){
      // Discard any response completed before the complete outgoing frame.
      // RX is already running during the last stop bit; its pending byte remains.
      reply_=NoReply;
      for(unsigned n=0;n<1000000;++n){
        uint64_t value=now();if(!bounded(value)||value<tx_end){ok=false;break;}
        poll(value);
        if(reply_!=NoReply||value-tx_end>=kReply)break;
        if(n==999999){timer_ok_=false;ok=false;}
      }
    }
    const uint64_t end=now();valid_=ok&&bounded(end)&&!framing_;
    duration_=end>=start_?end-start_:0;++commands_;
    bus_.restore_irq(saved);
    return valid_?reply_:Invalid;
  }
};
}
