FROM python:3.12-slim-bookworm AS game
ARG TARGETARCH
COPY terraria-server.zip game_release.py install-game.py /tmp/
RUN python /tmp/install-game.py

FROM debian:bookworm-slim
LABEL org.opencontainers.image.source="https://github.com/Bacon0033/homepute-terraria-unit"
RUN apt-get update && apt-get install -y --no-install-recommends python3 mono-runtime libmono-system-windows-forms4.0-cil libmono-system-runtime-serialization4.0-cil libmono-sqlite4.0-cil ca-certificates && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --create-home terraria && install -d -o terraria -g terraria /config
COPY --from=game /vanilla /vanilla
COPY terraria_bridge.py game_release.py /opt/homepute/
WORKDIR /vanilla
EXPOSE 7777/tcp 8080/tcp
ENTRYPOINT ["python3", "-u", "/opt/homepute/terraria_bridge.py"]
