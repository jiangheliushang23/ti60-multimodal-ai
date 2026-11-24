#ifndef TI60_WEB_LWIPOPTS_H
#define TI60_WEB_LWIPOPTS_H
/* Application configuration, not the unadapted BSP's DMA/checksum defaults. */
#define NO_SYS 1
#define SYS_LIGHTWEIGHT_PROT 0
#define LWIP_SOCKET 0
#define LWIP_NETCONN 0
#define LWIP_IPV4 1
#define LWIP_IPV6 0
#define LWIP_TCP 1
#define LWIP_UDP 1
#define LWIP_ARP 1
#define LWIP_ICMP 1
#define LWIP_DHCP 0
#define LWIP_DNS 0
#define LWIP_AUTOIP 0
#define LWIP_IGMP 0
#define IP_FORWARD 0
#define IP_REASSEMBLY 0
#define IP_FRAG 0
#define LWIP_STATS 0
#define MEM_ALIGNMENT 4
#define MEM_SIZE 65536
/* Diagnostic candidate: pool red zones plus validation before list access. */
#define MEMP_OVERFLOW_CHECK 1
#define MEM_OVERFLOW_CHECK 1
#define WM_MEMP_DIAGNOSTICS 1
#define MEMP_NUM_TCP_PCB 12
#define MEMP_NUM_TCP_PCB_LISTEN 1
#define MEMP_NUM_TCP_SEG 32
#define MEMP_NUM_UDP_PCB 2
#ifdef WM_TEST_CHAINED_PBUFS
#define PBUF_POOL_SIZE 32
#define PBUF_POOL_BUFSIZE 256
#else
#define PBUF_POOL_SIZE 16
#define PBUF_POOL_BUFSIZE 1536
#endif
#define TCP_MSS 1460
#define TCP_WND 5840
#define TCP_SND_BUF 5840
#define TCP_SND_QUEUELEN 16
/* Bounded copied responses do not need spare tail reservations. Disable the
 * optional append optimization while diagnosing board-only pointer faults.
 * This is a configuration comparison, not proof of the prior fault's cause. */
#define TCP_OVERSIZE 0
#define TCP_QUEUE_OOSEQ 0
#define TCP_LISTEN_BACKLOG 1
#define CHECKSUM_GEN_IP 1
#define CHECKSUM_GEN_UDP 1
#define CHECKSUM_GEN_TCP 1
#define CHECKSUM_CHECK_IP 1
#define CHECKSUM_CHECK_UDP 1
#define CHECKSUM_CHECK_TCP 1
#endif
