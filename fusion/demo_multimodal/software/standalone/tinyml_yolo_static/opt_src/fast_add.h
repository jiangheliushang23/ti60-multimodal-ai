#pragma once
#include "compat_runtime.h"
OP_STATUS_T exact_lut_add(int size,const int8_t* x,const int8_t* y,int8_t* out,
    int32_t xo,int32_t yo,int32_t zo,int32_t zm,int32_t zs,int32_t ls,
    int32_t xm,int32_t xs,int32_t ym,int32_t ys,int32_t amin,int32_t amax);
