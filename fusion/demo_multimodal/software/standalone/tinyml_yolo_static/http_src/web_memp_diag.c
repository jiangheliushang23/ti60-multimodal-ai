#include "web_memp_diag.h"
#include "lwip/priv/memp_priv.h"
#ifdef __riscv
#include <stdio.h>
struct pool_event { const struct memp_desc *pool; const void *node, *head; int freeing; };
static volatile struct pool_event events[64];
static volatile unsigned event_next;
#endif

static int pool_node(const struct memp_desc *d, const void *p) {
    mem_ptr_t base = (mem_ptr_t)LWIP_MEM_ALIGN(d->base), address = (mem_ptr_t)p;
    mem_ptr_t stride = MEMP_SIZE + MEMP_ALIGN_SIZE(d->size);
    return address >= base && address - base < stride * d->num &&
           (address - base) % stride == 0;
}

const char *wm_memp_check(const struct memp_desc *d, const void *node, int freeing) {
    const struct memp *p = *d->tab;
    unsigned visited = 0;
#ifdef __riscv
    unsigned i = event_next % 64;
    events[i].pool = d; events[i].node = node; events[i].head = p;
    events[i].freeing = freeing; ++event_next;
#endif
    if (freeing && !pool_node(d, node)) return "memp guard: invalid free";
    /* Validate the complete free list before any allocator dereference; the
     * length bound also catches cycles without chasing arbitrary addresses. */
    while (p) {
        if (!pool_node(d, p)) return "memp guard: invalid free-list node";
        if (++visited > d->num) return "memp guard: free-list cycle";
        if (freeing && p == node) return "memp guard: double free";
        p = p->next;
    }
    return 0;
}

void wm_memp_dump_trace(void) {
#ifdef __riscv
    unsigned end = event_next, i = end > 64 ? end - 64 : 0;
    for (; i < end; ++i) {
        const volatile struct pool_event *e = &events[i % 64];
        /* Print addresses only: a fatal path must not dereference a possibly
         * corrupted pool descriptor or linked list. */
        printf("MEMP_TRACE pool=%x node=%x head=%x free=%d\r\n",
                   (unsigned)e->pool, (unsigned)e->node, (unsigned)e->head, e->freeing);
    }
#endif
}
