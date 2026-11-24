#ifndef FUSION_FAST_PERSON_H_
#define FUSION_FAST_PERSON_H_
#include "person_layer.h"
namespace vision {
struct FastPersonResult {
  Box proposal, display;
  uint32_t seq, ms, generation;
  unsigned motion_pixels, foreground_pixels, similarity_bp;
  bool confirmed, scene_change;
};
// A fixed-camera, single-person tracker gated by the EXISTING MobileNet.
// A foreground component alone never establishes a human identity.
class FastPerson {
 public:
  void Reset();
  FastPersonResult Observe(const uint8_t* gray,uint32_t seq,uint32_t ms);
  bool Verify(const Box& sampled,uint32_t generation,int person_bp);
  FastPersonResult result() const { return result_; }
 private:
  uint16_t background_[kImagePixels],queue_[kImagePixels];
  uint8_t previous_[kImagePixels],original_[kImagePixels],estimated_[kImagePixels];
  uint8_t mask_[kImagePixels],work_[kImagePixels],scratch_[kImagePixels],motion_[kImagePixels];
  uint16_t reference_hist_[16],current_hist_[16],histogram_[256];
  Box components_[512],window_;
  FastPersonResult result_;
  unsigned reference_count_,negative_runs_;
  bool initialized_,confirmed_;
  void Dilate(const uint8_t* source,uint8_t* dest);
  void Erode(const uint8_t* source,uint8_t* dest);
  void Initialize(const uint8_t* gray);
};
// Context is square in the original 1280x720 scene, not in stretched AI96.
bool QuantizeFastContext(const uint8_t* gray,const Box& box,const int8_t* lut,
                         int8_t* input,unsigned view=0);
}
#endif
