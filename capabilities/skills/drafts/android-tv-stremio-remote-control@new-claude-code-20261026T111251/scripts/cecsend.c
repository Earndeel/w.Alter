/* Envoie un message HDMI-CEC brut depuis le dongle Android TV (pilote sunxi /dev/cec, root nécessaire).
 * Format repris de hdmi_cec.cupid.so (Hdmi2xCecDevice::transmit) : ioctl 0xC0346305 sur une
 * structure de 52 octets.
 *
 *   cecsend <dest> <octet hex>...      ex. cecsend 0 44 00  (= <User Control Pressed> Select vers la télé)
 * L'émetteur est l'adresse logique 4 (lecteur 1) que la HAL a déjà prise ; dest F = diffusion.
 */
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <sys/ioctl.h>
#include <unistd.h>

#define CEC_TRANSMIT 0xC0346305u

int main(int argc, char **argv) {
    if (argc < 2 || argc > 17) {
        fprintf(stderr, "usage: cecsend <dest 0-F> [octets hex...]\n");
        return 2;
    }
    unsigned char buf[0x34];
    memset(buf, 0, sizeof buf);
    unsigned int *w = (unsigned int *)buf;
    int n = argc - 2;                                   /* octets après l'en-tête */
    w[0] = (unsigned int)(unsigned long)(buf + 0x0c);   /* la HAL y met l'adresse du message */
    w[3] = (unsigned int)(n + 1);                       /* longueur, en-tête compris */
    w[4] = 1000;                                        /* délai en ms */
    buf[0x20] = (unsigned char)((4 << 4) | (strtol(argv[1], NULL, 16) & 0xf));
    for (int i = 0; i < n; i++)
        buf[0x21 + i] = (unsigned char)strtol(argv[2 + i], NULL, 16);

    int fd = open("/dev/cec", O_RDWR);
    if (fd < 0) { perror("open /dev/cec"); return 1; }
    int r = ioctl(fd, CEC_TRANSMIT, buf);
    unsigned int status = *(unsigned int *)(buf + 0x18);
    printf("ioctl=%d errno=%d statut=%u (%s)\n", r, r < 0 ? errno : 0, status,
           status == 2 ? "acquitté" : status == 3 ? "non acquitté" : "?");
    close(fd);
    return r < 0;
}
