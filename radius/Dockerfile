FROM freeradius/freeradius-server:3.2.7

COPY mods-enabled/rest /etc/raddb/mods-available/rest
COPY sites-enabled/default.template /etc/raddb/sites-available/devzen.template
COPY clients.conf.template /etc/raddb/clients.conf.template
COPY entrypoint.sh /usr/local/bin/radius-entrypoint

RUN rm -f /etc/raddb/mods-enabled/rest \
    && ln -s ../mods-available/rest /etc/raddb/mods-enabled/rest \
    && rm -f /etc/raddb/sites-enabled/default \
    && ln -s ../sites-available/devzen /etc/raddb/sites-enabled/default \
    && chmod 755 /usr/local/bin/radius-entrypoint

EXPOSE 1812/udp 1813/udp

HEALTHCHECK --interval=30s --timeout=8s --start-period=15s --retries=3 \
    CMD radiusd -C || exit 1

ENTRYPOINT ["/usr/local/bin/radius-entrypoint"]
CMD ["radiusd", "-f"]
