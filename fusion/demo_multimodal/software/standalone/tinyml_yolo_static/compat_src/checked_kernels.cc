#include "compat_runtime.h"
#include "port.h"
#include <cstring>
#include <algorithm>
#include "tensorflow/lite/kernels/internal/tensor_ctypes.h"

Phase phase=Phase::Qualify;
unsigned current_node, hash_failures, qualify_failures;
bool driver_enabled, node_used_hardware;
bool qualified[kNodeCount];
bool node_used_software_fast,software_qualified[kNodeCount];
unsigned node_ms[kNodeCount];
const char* fallback_reason="reference_only";
namespace {
TfLiteRegistration original_conv,original_add,original_mul;
alignas(64) int8_t hardware_output[192*192*16];
unsigned bytes(const TfLiteEvalTensor* t) {
  unsigned result=t->type==kTfLiteInt32?4:1;
  for(int i=0;i<t->dims->size;++i) result*=t->dims->data[i];
  return result;
}
bool aliases(TfLiteContext* context,TfLiteNode* node,TfLiteEvalTensor* output) {
  const uintptr_t begin=reinterpret_cast<uintptr_t>(output->data.raw);
  const uintptr_t end=begin+bytes(output);
  for(int i=0;i<node->inputs->size;++i) {
    if(node->inputs->data[i]<0) continue;
    const auto* input=context->GetEvalTensor(context,node->inputs->data[i]);
    const uintptr_t ib=reinterpret_cast<uintptr_t>(input->data.raw);
    if(ib<end && begin<ib+bytes(input)) return true;
  }
  return false;
}
TfLiteStatus invoke(TfLiteContext* context,TfLiteNode* node,TfLiteRegistration& original) {
  node_used_hardware=false;
  node_used_software_fast=false;
  fallback_reason="software_selected";
  driver_enabled=phase==Phase::Qualify || (phase==Phase::Hybrid && (qualified[current_node]||software_qualified[current_node]));
  auto* output=context->GetEvalTensor(context,node->outputs->data[0]);
  if(aliases(context,node,output)) { driver_enabled=false; fallback_reason="inplace_alias"; }
  const uint32_t begin=milliseconds();
  TfLiteStatus status=original.invoke(context,node);
  const unsigned hw_ms=milliseconds()-begin;
  driver_enabled=false;
  if(status!=kTfLiteOk || phase!=Phase::Qualify || (!node_used_hardware&&!node_used_software_fast)) return status;
  const bool was_hardware=node_used_hardware;
  const unsigned count=bytes(output);
  if(count>sizeof(hardware_output)) compat_fatal("comparison_buffer");
  memcpy(hardware_output,output->data.int8,count);
  const uint32_t ref_begin=milliseconds();
  status=original.invoke(context,node); // Identical inputs, drivers disabled; leave reference output in graph.
  const unsigned ref_ms=milliseconds()-ref_begin;
  unsigned different=0,maximum=0;
  for(unsigned i=0;i<count;++i) {
    const unsigned delta=std::abs(int(hardware_output[i])-int(output->data.int8[i]));
    different+=delta!=0; maximum=std::max(maximum,delta);
  }
  const bool exact=different==0 && status==kTfLiteOk;
  // This layer had an actual transient hardware mismatch in the v1 board run.
  // Keep production timing runs on software until its DMA/coherency cause is isolated.
  const bool quarantined=current_node==100;
  qualified[current_node]=was_hardware && exact && !quarantined;
  software_qualified[current_node]=!was_hardware && exact && !quarantined;
  qualify_failures+=!exact;
  if(quarantined) log_line("YOLO2_POLICY node=100 use=SOFTWARE reason=prior_board_mismatch_not_root_caused");
  log_line("YOLO2_QUALIFY node=%u op=%s bytes=%u diff=%u max_abs=%u fast_ms=%u sw_ms=%u accepted=%u backend=%s",
           current_node,kNodeMetadata[current_node].name,count,different,maximum,hw_ms,ref_ms,
           qualified[current_node]||software_qualified[current_node],was_hardware?"DSP":"SOFTWARE_LUT");
  return status;
}
TfLiteStatus conv(TfLiteContext* c,TfLiteNode* n) { return invoke(c,n,original_conv); }
TfLiteStatus add(TfLiteContext* c,TfLiteNode* n) { return invoke(c,n,original_add); }
TfLiteStatus mul(TfLiteContext* c,TfLiteNode* n) { return invoke(c,n,original_mul); }
}
TfLiteRegistration checked_registration(TfLiteRegistration original,int builtin) {
  if(builtin==3) { original_conv=original; original.invoke=conv; }
  else if(builtin==0) { original_add=original; original.invoke=add; }
  else if(builtin==18) { original_mul=original; original.invoke=mul; }
  return original;
}
