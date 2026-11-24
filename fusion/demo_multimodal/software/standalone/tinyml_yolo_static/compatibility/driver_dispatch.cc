#define YOLO_DRIVER_IMPLEMENTATION
#include "compat_runtime.h"
#include "platform/tinyml/ops/conv.h"
#include "platform/tinyml/ops/add.h"
#include "platform/tinyml/ops/mul.h"
#ifdef YOLO_OPT
#include "tiled_conv.h"
#include "fast_add.h"
#endif
OP_STATUS_T checked_conv_drv(
		const int stride_width,
		const int stride_height,
		const int dilation_width_factor,
		const int dilation_height_factor,
		const int pad_width,
		const int pad_height,
		const int32_t input_offset,
		const int32_t output_offset,

		const int batches,
		const int input_depth,
		const int output_depth,
		const int input_width,
		const int input_height,
		const int filter_width,
		const int filter_height,
		const int output_width,
		const int output_height,
		const int32_t output_activation_min,
		const int32_t output_activation_max,

		const int32_t *output_multiplier,
		const int32_t *output_shift,

		const int8_t *input_data,
		const int8_t *filter_data,
		const int32_t *bias_data,
		const int32_t *input_shape,
		const int32_t *output_shape,
		const int32_t *filter_shape,

		int8_t *output_data
		) {
if(batches!=1 || dilation_width_factor!=1 || dilation_height_factor!=1) { fallback_reason="conv_parameters"; return OP_ERR; }
#ifdef YOLO_OPT
return hardware_call(tiled_conv_drv,stride_width,stride_height,dilation_width_factor,dilation_height_factor,pad_width,pad_height,input_offset,output_offset,batches,input_depth,output_depth,input_width,input_height,filter_width,filter_height,output_width,output_height,output_activation_min,output_activation_max,output_multiplier,output_shift,input_data,filter_data,bias_data,input_shape,output_shape,filter_shape,output_data);
#else
return hardware_call(conv_drv,stride_width,stride_height,dilation_width_factor,dilation_height_factor,pad_width,pad_height,input_offset,output_offset,batches,input_depth,output_depth,input_width,input_height,filter_width,filter_height,output_width,output_height,output_activation_min,output_activation_max,output_multiplier,output_shift,input_data,filter_data,bias_data,input_shape,output_shape,filter_shape,output_data);
#endif
}
OP_STATUS_T checked_add_drv(
		int size,
		const int8_t *input1_data,
		const int8_t *input2_data,
		int8_t *output_data,
		int32_t input1_offset,
		int32_t input2_offset,
		int32_t output_offset,
		int32_t output_multiplier,
		int32_t output_shift,
		int32_t left_shift,
		int32_t input1_multiplier,
		int32_t input1_shift,
		int32_t input2_multiplier,
		int32_t input2_shift,
		int32_t quantized_activation_min,
		int32_t quantized_activation_max
		) {
#if defined(YOLO_DSP16) && defined(YOLO_OPT) && (!defined(YOLO_REALTIME) || defined(YOLO_CACHE32))
return exact_lut_add(size,input1_data,input2_data,output_data,input1_offset,input2_offset,output_offset,output_multiplier,output_shift,left_shift,input1_multiplier,input1_shift,input2_multiplier,input2_shift,quantized_activation_min,quantized_activation_max);
#else
return hardware_call(add_drv,size,input1_data,input2_data,output_data,input1_offset,input2_offset,output_offset,output_multiplier,output_shift,left_shift,input1_multiplier,input1_shift,input2_multiplier,input2_shift,quantized_activation_min,quantized_activation_max);
#endif
}
OP_STATUS_T checked_mul_drv(
		int32_t input1_offset,
		int32_t input2_offset,

		int32_t output_shift,
		int32_t output_multiplier,
		int32_t output_offset,

		int32_t quantized_activation_max,
		int32_t quantized_activation_min,
		int32_t bmax,
		int32_t ymax,
		int32_t xmax,
		int32_t cmax,
		const int *strides1,
		const int *strides2,
		const int8_t *input1_data,
		const int8_t *input2_data,
		int8_t *output_data
		) {
return hardware_call(mul_drv,input1_offset,input2_offset,output_shift,output_multiplier,output_offset,quantized_activation_max,quantized_activation_min,bmax,ymax,xmax,cmax,strides1,strides2,input1_data,input2_data,output_data);
}
OP_STATUS_T checked_mul_drv_elementwise(
		int size,
		int32_t input1_offset,
		int32_t input2_offset,

		int32_t output_shift,
		int32_t output_multiplier,
		int32_t output_offset,

		int32_t quantized_activation_max,
		int32_t quantized_activation_min,
		const int8_t *input1_data,
		const int8_t *input2_data,
		int8_t *output_data
		) {
if(!driver_enabled) return OP_ERR;
if(!mul_parameters_verified(input1_offset,input2_offset,output_shift,output_multiplier,output_offset,quantized_activation_max,quantized_activation_min)) { fallback_reason="mul_parameter_preflight"; return OP_ERR; }
return hardware_call(mul_drv_elementwise,size,input1_offset,input2_offset,output_shift,output_multiplier,output_offset,quantized_activation_max,quantized_activation_min,input1_data,input2_data,output_data);
}
