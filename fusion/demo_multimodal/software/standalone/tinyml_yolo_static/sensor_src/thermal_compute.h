#pragma once
#include <cstdint>
#include "MLX90640_API.h"

// Vendor compensation equations, with EEPROM invariants cached once and
// frame invariants cached once per subpage. LUT replaces only fourth roots.
class ThermalCompute {
 public:
  void calibrate(const paramsMLX90640& params);
  bool prepare(uint16_t* frame,const paramsMLX90640& params,float emissivity,float reflected_offset_c);
  void calculate(const uint16_t* frame,const paramsMLX90640& params,float* result,unsigned first,unsigned count) const;
  float ambient=0,supply=0;
  static float fourth_root(float value);
 private:
  float alpha_base[768];
  float gain=0,ta_tr=0,cp=0,inv_emissivity=0,alpha_ta=0,kta_ta=0,kv_vdd=0,alpha_range[4];
  unsigned mode=0,page=0;
};
