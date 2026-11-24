#pragma once
#include_next "platform/tinyml/ops/mul.h"
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
		);
#ifndef YOLO_DRIVER_IMPLEMENTATION
#define mul_drv checked_mul_drv
#endif
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
		);
#ifndef YOLO_DRIVER_IMPLEMENTATION
#define mul_drv_elementwise checked_mul_drv_elementwise
#endif
