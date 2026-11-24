#include "web_netif.h"
#include "lwip/etharp.h"
#include "lwip/pbuf.h"
static err_t send_frame(struct netif *netif, struct pbuf *p) {
    struct wm_netif *d = (struct wm_netif *)netif->state;
    int sent;
    if (p->tot_len < 14 || p->tot_len > WM_ETH_FRAME_MAX) {
        ++d->tx_dropped;
        return ERR_IF;
    }
    if (pbuf_copy_partial(p, d->tx, p->tot_len, 0) != p->tot_len) {
        ++d->tx_dropped;
        return ERR_IF;
    }
    sent = d->ops->send_copy(d->context, d->tx, p->tot_len);
    /* A full synchronous MAC is temporary backpressure. Keep TCP's queued
     * bytes for its next output attempt instead of aborting the connection. */
    if (sent == 0)
        return ERR_MEM;
    if (sent != 1) {
        ++d->tx_dropped;
        return ERR_IF;
    }
    ++d->tx_frames;
    return ERR_OK;
}
err_t wm_netif_init(struct netif *netif) {
    struct wm_netif *d = (struct wm_netif *)netif->state;
    unsigned i;
    if (!d || !d->ops || !d->ops->receive_copy || !d->ops->send_copy || !d->ops->link_up)
        return ERR_ARG;
    netif->name[0] = 'w';
    netif->name[1] = 'm';
    netif->hwaddr_len = 6;
    for (i = 0; i < 6; ++i)
        netif->hwaddr[i] = d->mac[i];
    netif->mtu = 1500;
    netif->flags = NETIF_FLAG_ETHARP | NETIF_FLAG_BROADCAST;
    netif->output = etharp_output;
    netif->linkoutput = send_frame;
    return ERR_OK;
}
void wm_netif_poll(struct netif *netif, unsigned budget) {
    struct wm_netif *d = (struct wm_netif *)netif->state;
    if (d->ops->link_up(d->context)) {
        if (!netif_is_link_up(netif))
            netif_set_link_up(netif);
    } else {
        if (netif_is_link_up(netif))
            netif_set_link_down(netif);
        return;
    }
    while (budget--) {
        struct pbuf *p;
        unsigned n = 0;
        int ready = d->ops->receive_copy(d->context, d->rx, WM_ETH_FRAME_MAX, &n);
        if (!ready)
            break;
        if (ready != 1 || n < 14 || n > WM_ETH_FRAME_MAX) {
            ++d->rx_dropped;
            continue;
        }
        p = pbuf_alloc(PBUF_RAW, (u16_t)n, PBUF_POOL);
        if (!p) {
            ++d->rx_dropped;
            continue;
        }
        if (pbuf_take(p, d->rx, (u16_t)n) != ERR_OK) {
            pbuf_free(p);
            ++d->rx_dropped;
            continue;
        }
        if (netif->input(p, netif) != ERR_OK) {
            pbuf_free(p);
            ++d->rx_dropped;
        } else
            ++d->rx_frames;
    }
}
