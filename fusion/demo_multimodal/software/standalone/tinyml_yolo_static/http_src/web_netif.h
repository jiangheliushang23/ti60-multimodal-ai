#ifndef WEB_NETIF_H
#define WEB_NETIF_H
#include "lwip/netif.h"
#include <stdint.h>
#define WM_ETH_FRAME_MAX 1514u /* Ethernet II, no VLAN, no FCS */
struct wm_mac_ops {
    /* Receive: 1 means copied complete frame into dst; 0 means no data;
     * -1 means a dropped/invalid frame. Release DMA ownership only after copy.
     * Never return a DMA pointer for lwIP to retain. FCS must be stripped. */
    int (*receive_copy)(void *context, uint8_t *dst, unsigned capacity, unsigned *length);
    /* Send: copy/enqueue the complete frame before returning 1; return 0 if
     * busy or -1 on error. The buffer can be reused immediately on return.
     * DMA implementations MUST copy into their own TX-owned buffer first.
     * MAC appends padding/FCS; hardware checksum offload is disabled. */
    int (*send_copy)(void *context, const uint8_t *src, unsigned length);
    int (*link_up)(void *context);
};
struct wm_netif {
    const struct wm_mac_ops *ops;
    void *context;
    uint8_t mac[6], rx[WM_ETH_FRAME_MAX], tx[WM_ETH_FRAME_MAX];
    uint32_t rx_frames, rx_dropped, tx_frames, tx_dropped;
};
/* Pass an initialized wm_netif as netif_add's state, wm_netif_init as init,
 * and ethernet_input as input. No register addresses or PHY guesses here. */
err_t wm_netif_init(struct netif *);
void wm_netif_poll(struct netif *, unsigned receive_budget);
#endif
