#ifndef WEB_MEMP_DIAG_H
#define WEB_MEMP_DIAG_H
#include "lwip/memp.h"
/* Called inside lwIP's pool critical section, before dereferencing a node.
 * Returns a fixed diagnostic string on corruption, NULL on success. */
const char *wm_memp_check(const struct memp_desc *desc, const void *node, int freeing);
void wm_memp_dump_trace(void);
#endif
