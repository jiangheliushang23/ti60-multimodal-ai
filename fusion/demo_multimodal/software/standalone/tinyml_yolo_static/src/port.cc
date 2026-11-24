#include "port.h"
#include <stdarg.h>
#include <stdio.h>
#include "tensorflow/lite/micro/micro_time.h"

namespace {
volatile uint32_t* const uart = reinterpret_cast<volatile uint32_t*>(0xf8010000u);
void write_char(char value) {
#ifdef YOLO_QEMU
  auto* u = reinterpret_cast<volatile uint8_t*>(0x10000000u);
  while (!(u[5] & 0x20)) {}
  u[0] = value;
#else
  while (((uart[1] >> 16) & 255) == 0) {}
  uart[0] = static_cast<uint8_t>(value);
#endif
}
}

extern "C" void DebugLog(const char* message) {
  while (*message) write_char(*message++);
}

void uart_write_bytes(const uint8_t* data,unsigned bytes) {
  while(bytes--)write_char(static_cast<char>(*data++));
}

void log_line(const char* format, ...) {
  char buffer[1024];
  va_list arguments;
  va_start(arguments, format);
  vsnprintf(buffer, sizeof(buffer), format, arguments);
  va_end(arguments);
  DebugLog(buffer);
  DebugLog("\r\n");
}

uint32_t milliseconds() {
#ifdef YOLO_MULTIMODAL
  // Common video/IR/environment clock; never mix CLINT epoch with APB stamps.
  return *reinterpret_cast<volatile uint32_t*>(0xf8103014u);
#else
#ifdef YOLO_QEMU
  volatile uint32_t* timer = reinterpret_cast<volatile uint32_t*>(0x0200bff8u);
  uint32_t high, low, again;
  do { high = timer[1]; low = timer[0]; again = timer[1]; } while (high != again);
  return static_cast<uint32_t>(((static_cast<uint64_t>(high) << 32) | low) / 10000u);
#else
#ifdef YOLO_DSP16
  // The visual-only accelerator build omits sensor APB registers. Use the
  // Sapphire CLINT's 100 MHz timer, also used by the accelerator watchdog.
  volatile uint32_t* timer = reinterpret_cast<volatile uint32_t*>(0xf8b0bff8u);
  uint32_t high,low,again;
  do { high=timer[1];low=timer[0];again=timer[1]; } while(high!=again);
  return static_cast<uint32_t>(((static_cast<uint64_t>(high)<<32)|low)/100000u);
#else
  // Existing fusion hardware's monotonic APB millisecond counter.
  return *reinterpret_cast<volatile uint32_t*>(0xf8103014u);
#endif
#endif
#endif
}

int read_command() {
#ifdef YOLO_QEMU
  return -1;
#else
  return (uart[1] >> 24) ? static_cast<int>(uart[0] & 255) : -1;
#endif
}

void platform_finish(bool success) {
#ifdef YOLO_QEMU
  *reinterpret_cast<volatile uint32_t*>(0x00100000u) = success ? 0x5555u : 0x13333u;
#else
  (void)success;
  asm volatile("fence iorw, iorw" ::: "memory");
#endif
}

extern "C" void yolo_trap(unsigned cause, unsigned pc, unsigned value) {
  log_line("YOLO_FATAL reason=trap mcause=%08x mepc=%08x mtval=%08x", cause, pc, value);
  platform_finish(false);
  for (;;) {}
}

namespace tflite {
int32_t ticks_per_second() { return 1000; }
int32_t GetCurrentTimeTicks() { return static_cast<int32_t>(milliseconds()); }
}

extern "C" { void* __dso_handle = &__dso_handle; }
