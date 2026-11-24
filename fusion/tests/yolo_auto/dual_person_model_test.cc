#include <algorithm>
#include <stdint.h>
#include "fixture.h"
#include "person_pair.h"
struct TestTensor {struct {int8_t* int8;} data;};
namespace tflite {
struct MicroInterpreter {
 TestTensor tensors[3];
 TestTensor* output(unsigned i){return tensors+i;}
};
}
// Generated verbatim from the production candidate/NMS/decoder functions.
#include "decoder_under_test.inc"
extern "C" {
int8_t pair_heads[kOutputBytes];
unsigned pair_fresh=1;
int pair_output[14];
void run_pair_model(){
 tflite::MicroInterpreter interpreter;unsigned offset=0;
 for(unsigned i=0;i<3;++i){interpreter.tensors[i].data.int8=pair_heads+offset;offset+=kHeadBytes[i];}
 decode(interpreter);
 const auto view=person_roi::full();
 person_roi::Planner planner;
 auto primary=planner.select(view,boxes,box_count,0);
 if(!pair_fresh)primary.valid=false;
 person_pair::Detections frame;frame.add(view,boxes,box_count);
 const auto second=frame.second(primary,pair_fresh);
 pair_output[0]=box_count;pair_output[1]=primary.valid+second.valid;
 unsigned at=2;
 for(const auto& d:{primary,second}){
  pair_output[at++]=d.valid;pair_output[at++]=d.box.x1;pair_output[at++]=d.box.y1;
  pair_output[at++]=d.box.x2;pair_output[at++]=d.box.y2;pair_output[at++]=d.score;
 }
}
}
