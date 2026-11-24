#include "fast_memory_ops.h"
#include "compat_runtime.h"
#include "fixture.h"
#include "tensorflow/lite/c/builtin_op_data.h"
#include <algorithm>
#include <cstring>

namespace {
TfLiteRegistration originals[3];
alignas(64) int8_t reference_copy[192*192*16];
alignas(64) int8_t pool_rows[32*32*256];
TfLiteStatus pad(TfLiteContext* c,TfLiteNode* n,bool v2) {
  auto* x=c->GetEvalTensor(c,n->inputs->data[0]);auto* y=c->GetEvalTensor(c,n->outputs->data[0]);
  auto* p=c->GetEvalTensor(c,n->inputs->data[1]);const int32_t* a=p->data.i32;
  if(x->type!=kTfLiteInt8||x->dims->size!=4||a[0]||a[1]||a[6]||a[7])return originals[v2?1:0].invoke(c,n);
  const int h=x->dims->data[1],w=x->dims->data[2],channels=x->dims->data[3];
  const int oh=y->dims->data[1],ow=y->dims->data[2],batches=x->dims->data[0];
  const int value=v2?c->GetEvalTensor(c,n->inputs->data[2])->data.int8[0]:kPadZeroPoints[current_node];
  if(a[2]<0||a[4]<0||oh<a[2]+h||ow<a[4]+w)return originals[v2?1:0].invoke(c,n);
  for(int b=0;b<batches;++b) {
    auto* dest=y->data.int8+b*oh*ow*channels;
    memset(dest,value,a[2]*ow*channels);
    for(int row=0;row<h;++row) {
      auto* line=dest+(row+a[2])*ow*channels;
      memset(line,value,a[4]*channels);
      memcpy(line+a[4]*channels,x->data.int8+(b*h+row)*w*channels,w*channels);
      memset(line+(a[4]+w)*channels,value,(ow-a[4]-w)*channels);
    }
    memset(dest+(a[2]+h)*ow*channels,value,(oh-a[2]-h)*ow*channels);
  }
  return kTfLiteOk;
}
TfLiteStatus pool(TfLiteContext* c,TfLiteNode* n) {
  auto* x=c->GetEvalTensor(c,n->inputs->data[0]);auto* y=c->GetEvalTensor(c,n->outputs->data[0]);
  auto* p=static_cast<TfLitePoolParams*>(n->builtin_data);
  const int h=x->dims->data[1],w=x->dims->data[2],ch=x->dims->data[3];
  const int oh=y->dims->data[1],ow=y->dims->data[2];
  if(x->type!=kTfLiteInt8||x->dims->size!=4||x->dims->data[0]!=1||p->padding!=kTfLitePaddingValid||
      p->stride_width!=1||p->stride_height!=1||p->activation!=kTfLiteActNone||h*ow*ch>int(sizeof(pool_rows)))
    return originals[2].invoke(c,n);
  for(int row=0;row<h;++row)for(int col=0;col<ow;++col) {
    int8_t* d=pool_rows+(row*ow+col)*ch;
    memcpy(d,x->data.int8+(row*w+col)*ch,ch);
    for(int k=1;k<p->filter_width;++k) {
      const auto* s=x->data.int8+(row*w+col+k)*ch;
      for(int i=0;i<ch;++i)d[i]=std::max(d[i],s[i]);
    }
  }
  for(int row=0;row<oh;++row) {
    int8_t* d=y->data.int8+row*ow*ch;memcpy(d,pool_rows+row*ow*ch,ow*ch);
    for(int k=1;k<p->filter_height;++k) {
      const auto* s=pool_rows+(row+k)*ow*ch;
      for(int i=0;i<ow*ch;++i)d[i]=std::max(d[i],s[i]);
    }
  }
  return kTfLiteOk;
}
TfLiteStatus checked(TfLiteContext* c,TfLiteNode* n,int slot) {
  auto result=slot<2?pad(c,n,slot==1):pool(c,n);
  if(phase!=Phase::Qualify||result!=kTfLiteOk)return result;
  auto* out=c->GetEvalTensor(c,n->outputs->data[0]);unsigned count=1;
  for(int i=0;i<out->dims->size;++i)count*=out->dims->data[i];
  if(count>sizeof(reference_copy))compat_fatal("memory_op_buffer");
  memcpy(reference_copy,out->data.int8,count);
  result=originals[slot].invoke(c,n);
  if(result!=kTfLiteOk||memcmp(reference_copy,out->data.int8,count))compat_fatal("memory_op_reference");
  return result;
}
TfLiteStatus pad1(TfLiteContext*c,TfLiteNode*n){return checked(c,n,0);}
TfLiteStatus pad2(TfLiteContext*c,TfLiteNode*n){return checked(c,n,1);}
TfLiteStatus maxpool(TfLiteContext*c,TfLiteNode*n){return checked(c,n,2);}
}
TfLiteRegistration fast_memory_registration(TfLiteRegistration r,int builtin) {
  const int slot=builtin==34?0:builtin==60?1:2;originals[slot]=r;
  r.invoke=slot==0?pad1:slot==1?pad2:maxpool;return r;
}
