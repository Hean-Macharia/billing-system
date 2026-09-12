FROM freeradius/freeradius-server:latest

# Install curl for healthchecks
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Copy configuration
COPY mods-enabled/rest /etc/freeradius/mods-enabled/rest
COPY sites-enabled/default /etc/freeradius/sites-enabled/default
COPY clients.conf /etc/freeradius/clients.conf
COPY dictionary.mikrotik /usr/share/freeradius/dictionary.mikrotik

# Create log directory
RUN mkdir -p /var/log/freeradius && chown freerad:freerad /var/log/freeradius

# Expose RADIUS ports
EXPOSE 1812/udp 1813/udp

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD radiusd -C || exit 1

CMD ["radiusd", "-X", "-f"]