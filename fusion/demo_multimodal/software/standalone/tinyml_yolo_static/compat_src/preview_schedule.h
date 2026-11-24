#pragma once
#include <stdint.h>
// CLINT runs at 100 MHz. Periodic preview and the original 10 s watchdog
// share one timer compare, with an independent deadline for each task.
struct PreviewSchedule {
 static constexpr uint64_t period=500000ull;
 uint64_t next=~uint64_t(0),watchdog=~uint64_t(0);
 void start(uint64_t now){next=now+period;}
 void arm(uint64_t now){watchdog=now+1000000000ull;}
 void disarm(){watchdog=~uint64_t(0);}
 bool expired(uint64_t now)const{return now>=watchdog;}
 bool due(uint64_t now)const{return now>=next;}
 void completed(uint64_t now){next=now+period;}
 uint64_t compare()const{return next<watchdog?next:watchdog;}
};
