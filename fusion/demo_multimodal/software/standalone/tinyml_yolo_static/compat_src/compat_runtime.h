#pragma once
#include <stdint.h>
#include "platform/tinyml/ops/ops_api.h"
#include "tensorflow/lite/c/common.h"
#include "node_metadata.h"

enum class Phase { Qualify, Software, Hybrid };
extern Phase phase;
extern unsigned current_node;
extern bool driver_enabled, node_used_hardware;
extern bool node_used_software_fast,software_qualified[kNodeCount];
extern const char* fallback_reason;
extern bool qualified[kNodeCount];
extern unsigned node_ms[kNodeCount], hash_failures, qualify_failures;
void hardware_initialize();
void watchdog_arm();
void watchdog_disarm();
void cache_sync();
void compat_fatal(const char* reason);
uint32_t fnv(const uint8_t* data, unsigned bytes);

template<class F, class... Args> OP_STATUS_T hardware_call(F function, Args... args) {
  if(!driver_enabled) return OP_ERR;
  cache_sync();
  watchdog_arm();
  const OP_STATUS_T status=function(args...);
  watchdog_disarm();
  cache_sync();
  if(status==OP_OK) node_used_hardware=true;
  else fallback_reason="driver_declined";
  return status;
}

TfLiteRegistration checked_registration(TfLiteRegistration original, int builtin);
bool mul_parameters_verified(int32_t input1_offset,int32_t input2_offset,int32_t shift,
                             int32_t multiplier,int32_t output_offset,int32_t maximum,int32_t minimum);
