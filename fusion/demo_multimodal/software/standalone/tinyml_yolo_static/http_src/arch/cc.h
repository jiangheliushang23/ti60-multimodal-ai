#ifndef WM_RV32_CC_H
#define WM_RV32_CC_H
/* RV32 little endian; board provides these functions. Assertions must halt. */
#include <stdint.h>
#ifdef _MSC_VER
/* Only the native protocol regression uses MSVC; RV32 GCC uses lwIP defaults. */
#define PACK_STRUCT_BEGIN __pragma(pack(push, 1))
#define PACK_STRUCT_END __pragma(pack(pop))
#define PACK_STRUCT_STRUCT
#endif
void wm_platform_assert(const char *message);
uint32_t wm_platform_random(void);
#define BYTE_ORDER LITTLE_ENDIAN
#define LWIP_PLATFORM_DIAG(x)                                                                      \
    do {                                                                                           \
    } while (0)
#define LWIP_PLATFORM_ASSERT(x) wm_platform_assert(x)
#define LWIP_RAND() wm_platform_random()
#define LWIP_NO_INTTYPES_H 1
#define LWIP_NO_CTYPE_H 1
#define X8_F "02x"
#define U16_F "u"
#define S16_F "d"
#define X16_F "x"
#define U32_F "u"
#define S32_F "d"
#define X32_F "x"
#define SZT_F "u"
#endif
