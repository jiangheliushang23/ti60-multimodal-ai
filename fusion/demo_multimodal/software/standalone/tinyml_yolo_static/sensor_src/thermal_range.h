#pragma once
#include "MLX90640_API.h"
// Same vendor equations, bounded subset of pixel indices; other pixels untouched.
void MLX90640_CalculateToRange(uint16_t*,const paramsMLX90640*,float,float,float*,unsigned,unsigned);
