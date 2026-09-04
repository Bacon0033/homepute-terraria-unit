# Homepute Terraria Server unit

Production Terraria 1.4.5.7 dedicated server unit with persistent worlds and a generic Homepute HTTP/JSON data output. The channel returns server state and bounded recent output with `GET /v1/channel`; it accepts console commands with `POST /v1/channel` using `{ "type": "command", "command": "say hello" }`.

The implementation is intentionally expressed through the generic unit manifest data-port contract. No Terraria behavior is built into Homepute OS, Studio, Relay, or the Control Plane.
