FROM ghcr.io/beardedio/terraria@sha256:3f4f2969811de6e464ef980fdc19aec22afe84bdc608861d93e6522b0ae4762c

LABEL org.opencontainers.image.source="https://github.com/Bacon0033/homepute-terraria-unit" \
      org.opencontainers.image.description="Terraria dedicated server runtime for Homepute" \
      org.opencontainers.image.licenses="MIT"

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 \
    && rm -rf /var/lib/apt/lists/*

COPY terraria_bridge.py /opt/homepute/terraria_bridge.py
EXPOSE 7777/tcp 8080/tcp
ENTRYPOINT ["python3", "/opt/homepute/terraria_bridge.py"]
