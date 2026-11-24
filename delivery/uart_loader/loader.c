/* RAM-only UART transfer helper. Never launches or changes application code.
 * The host verifies every returned DDR byte before resuming entry 0x1000.
 * Scratch 0xc00000..0xc10000 is beyond current ELF RAM and below video DDR.
 */
#include <stdint.h>
#define MAX_BLOCK 4096u
#define FIRST 0x1000u
#define LIMIT 0x00c00000u
static volatile uint32_t *const uart=(volatile uint32_t *)0xf8010000u;
static uint8_t buffer[MAX_BLOCK];
static uint32_t table[256];
static inline void sync_cache(void) {
    __asm__ volatile("fence rw,rw\n.word 0x0000500f\nfence rw,rw" ::: "memory");
}
/* This Sapphire configuration does not expose CSR mcycle for reads. Use the
 * same 100 MHz CLINT timebase as the production application. */
static uint32_t ticks(void) {return *(volatile uint32_t *)0xf8b0bff8u;}
static int get_byte(void) {
    uint32_t t=ticks();
    while (!(uart[1]>>24)) if ((uint32_t)(ticks()-t)>500000000u) return -1;
    return uart[0]&255u;
}
static void put_byte(uint8_t b) {while (!((uart[1]>>16)&255u)) {} uart[0]=b;}
static void put_word(uint32_t w) {for (unsigned i=0;i<4;i++) put_byte(w>>(i*8));}
static uint32_t word(const uint8_t *p) {return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;}
static uint32_t crc(const volatile uint8_t *p,uint32_t n) {
    uint32_t x=~0u;for (uint32_t i=0;i<n;i++) x=(x>>8)^table[(x^p[i])&255u];return ~x;
}
static void response(uint32_t cmd,uint32_t seq,uint32_t status,uint32_t n,uint32_t checksum) {
    put_word(0x524c5559u); /* YULR */
    put_word(cmd);put_word(seq);put_word(status);put_word(n);put_word(checksum);
}
void loader_main(void) {
    uart[2]=24;uart[3]=7; /* Same 500000 / 8N1 as the deployed application. */
    for (unsigned i=0;i<256;i++) {
        uint32_t x=i;for (unsigned j=0;j<8;j++) x=(x>>1)^((0u-(x&1u))&0xedb88320u);table[i]=x;
    }
    sync_cache();
    uint32_t magic=0;
    for (;;) {
        int b=get_byte();if (b<0) {magic=0;continue;}
        magic=(magic>>8)|(uint32_t)b<<24;
        if (magic!=0x514c5559u) continue; /* YULQ */
        magic=0;uint8_t h[20];unsigned i;
        for (i=0;i<20;i++) {b=get_byte();if (b<0) break;h[i]=b;}
        if (i!=20) continue;
        uint32_t cmd=word(h),seq=word(h+4),address=word(h+8),n=word(h+12),checksum=word(h+16);
        if (cmd==1) {response(cmd,seq,0,MAX_BLOCK,0x00010001u);continue;}
        if ((cmd!=2&&cmd!=3&&cmd!=4)||address<FIRST||address>=LIMIT||!n||n>LIMIT-address||
            ((cmd==2||cmd==3)&&n>MAX_BLOCK)) {response(cmd,seq,1,0,0);continue;}
        volatile uint8_t *p=(volatile uint8_t *)address;
        if (cmd==2) {
            for (i=0;i<n;i++) {b=get_byte();if (b<0) break;buffer[i]=b;}
            if (i!=n) {response(cmd,seq,2,0,0);continue;}
            if (crc(buffer,n)!=checksum) {response(cmd,seq,3,0,0);continue;}
            for (i=0;i<n;i++) p[i]=buffer[i];
            sync_cache();uint32_t actual=crc(p,n);
            response(cmd,seq,actual==checksum?0:4,0,actual);
        } else if (cmd==3) {
            sync_cache();for (i=0;i<n;i++) buffer[i]=p[i];
            response(cmd,seq,0,n,crc(buffer,n));for (i=0;i<n;i++) put_byte(buffer[i]);
        } else {
            sync_cache();uint32_t actual=crc(p,n);
            response(cmd,seq,actual==checksum?0:4,0,actual);
        }
    }
}
