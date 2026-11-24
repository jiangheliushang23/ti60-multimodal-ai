#pragma once
#include <cstdint>
// Measure acknowledged rolling-map updates and complete pairs separately.
// A duplicate subpage never counts as a complete 768-pixel refresh.
struct ThermalRate {
 unsigned updates_tenths=0,pairs_tenths=0;
 unsigned epoch=0,updates=0,pairs=0,pair_mask=0;bool seeded=false;
 void reset(){*this=ThermalRate();}
 void acknowledge(unsigned now,unsigned page){
  pair_mask|=1u<<(page&1u);if(pair_mask==3){++pairs;pair_mask=0;}
  if(!seeded){seeded=true;epoch=now;updates=0;pairs=0;return;}
  ++updates;const unsigned dt=now-epoch;
  if(dt>=1000){
   updates_tenths=(updates*10000u+dt/2)/dt;
   pairs_tenths=(pairs*10000u+dt/2)/dt;
   epoch=now;updates=0;pairs=0;
  }
 }
};
