.section .rodata.yolo_assets,"a",@progbits
.balign 64
.global yolo_model
yolo_model:
.incbin "optimized/raw96x192/model.tflite"
.balign 64
.global yolo_input
yolo_input:
.incbin "optimized/raw96x192/generated/input.bin"
.balign 64
.global yolo_expected
yolo_expected:
.incbin "optimized/raw96x192/generated/expected.bin"
