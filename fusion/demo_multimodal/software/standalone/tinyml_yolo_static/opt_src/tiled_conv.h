#pragma once
#include "platform/tinyml/ops/ops_api.h"
extern unsigned conv_tile_weight_bytes;
OP_STATUS_T tiled_conv_drv(int sw,int sh,int dw,int dh,int pw,int ph,
    int32_t input_offset,int32_t output_offset,int batches,int ci,int co,
    int iw,int ih,int kw,int kh,int ow,int oh,int32_t amin,int32_t amax,
    const int32_t* multiplier,const int32_t* shift,const int8_t* input,
    const int8_t* filter,const int32_t* bias,const int32_t* input_shape,
    const int32_t* output_shape,const int32_t* filter_shape,int8_t* output);
