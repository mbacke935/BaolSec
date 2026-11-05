# Relais Syslog (pfSense)

pfSense n'accepte pas d'agent : il envoie ses journaux en Syslog à ce relais,
qui les conserve sur disque puis les transmet en Syslog TLS (port 6514) à la passerelle.
Configuration à valider en C7.
