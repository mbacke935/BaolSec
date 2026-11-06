# Relais Syslog BaolSec : rsyslog avec le pilote TLS OpenSSL et une file persistante.
FROM ubuntu:24.04
RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends rsyslog rsyslog-openssl ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && mkdir -p /var/spool/baolsec-relay
COPY rsyslog-baolsec.conf /etc/rsyslog-baolsec.conf
ENV BAOLSEC_GATEWAY_PORT=6514 \
    BAOLSEC_RELAY_DIR=/etc/baolsec-relay \
    BAOLSEC_SPOOL_DIR=/var/spool/baolsec-relay \
    BAOLSEC_LISTEN_PORT=514
VOLUME ["/var/spool/baolsec-relay"]
EXPOSE 514/udp 514/tcp
# rsyslog ouvre le port 514 puis reste au premier plan (-n) ; journaux du relais sur la sortie standard.
CMD ["rsyslogd", "-n", "-f", "/etc/rsyslog-baolsec.conf", "-i", "/tmp/rsyslogd.pid"]
