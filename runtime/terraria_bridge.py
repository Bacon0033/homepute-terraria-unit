#!/usr/bin/env python3
import collections
import json
import os
import pty
import select
import signal
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

GAME_PORT = int(os.environ.get("TERRARIA_PORT", "7777"))
ADMIN_PORT = int(os.environ.get("HOMEPUTE_CHANNEL_PORT", "8080"))
WORLD_NAME = os.environ.get("TERRARIA_WORLD_NAME", "Homepute World")[:80]
WORLD_SIZE = max(1, min(3, int(os.environ.get("TERRARIA_WORLD_SIZE", "2"))))
MAX_PLAYERS = max(1, min(255, int(os.environ.get("TERRARIA_MAX_PLAYERS", "8"))))
PASSWORD = os.environ.get("TERRARIA_PASSWORD", "")[:128]
MOTD = os.environ.get("TERRARIA_MOTD", "Hosted on Homepute")[:256]
WORLD_PATH = "/config/homepute.wld"
LOGS = collections.deque(maxlen=500)
STATE = {"ready": False, "startedAt": time.time(), "commands": 0, "lastLineAt": None}
MASTER_FD = None
PROCESS = None


def event(kind, values):
    print("HOMEPUTE_EVENT_V1 " + json.dumps({"version": 1, "type": kind, "values": values}, separators=(",", ":")), flush=True)


def record(line):
    line = line.rstrip("\r\n")[:2048]
    if not line:
        return
    entry = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "message": line}
    LOGS.append(entry)
    STATE["lastLineAt"] = entry["timestamp"]
    if "server started" in line.lower() or "type 'help'" in line.lower():
        STATE["ready"] = True
    print(line, flush=True)


def write_config():
    os.makedirs("/config", exist_ok=True)
    values = [
        f"world={WORLD_PATH}",
        f"autocreate={WORLD_SIZE}",
        f"worldname={WORLD_NAME}",
        f"maxplayers={MAX_PLAYERS}",
        f"port={GAME_PORT}",
        f"password={PASSWORD}",
        f"motd={MOTD}",
        "secure=1",
        "language=en-US",
    ]
    with open("/config/serverconfig.txt", "w", encoding="utf-8") as config:
        config.write("\n".join(values) + "\n")
    open("/config/banlist.txt", "a", encoding="utf-8").close()


def read_output():
    while PROCESS and PROCESS.poll() is None:
        ready, _, _ = select.select([MASTER_FD], [], [], 1.0)
        if not ready:
            continue
        try:
            data = os.read(MASTER_FD, 4096)
        except OSError:
            break
        if not data:
            break
        for line in data.decode("utf-8", errors="replace").splitlines():
            record(line)


def send_command(command):
    if not PROCESS or PROCESS.poll() is not None or MASTER_FD is None:
        raise RuntimeError("server_not_running")
    command = str(command).replace("\r", "").replace("\n", "").strip()[:512]
    if not command:
        raise ValueError("command_required")
    os.write(MASTER_FD, (command + "\n").encode("utf-8"))
    STATE["commands"] += 1
    return command


def snapshot():
    running = PROCESS is not None and PROCESS.poll() is None
    return {
        "version": 1,
        "kind": "homepute.data-channel.snapshot",
        "service": "terraria",
        "running": running,
        "ready": running and STATE["ready"],
        "gamePort": GAME_PORT,
        "world": WORLD_NAME,
        "maxPlayers": MAX_PLAYERS,
        "commandsAccepted": STATE["commands"],
        "uptimeSeconds": max(0, int(time.time() - STATE["startedAt"])),
        "logs": list(LOGS)[-100:],
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "HomeputeTerraria/1"

    def send_json(self, status, value):
        body = json.dumps(value, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            return self.send_json(200 if PROCESS and PROCESS.poll() is None else 503, {"ok": bool(PROCESS and PROCESS.poll() is None), "ready": STATE["ready"]})
        if self.path == "/v1/channel":
            return self.send_json(200, snapshot())
        self.send_json(404, {"error": "not_found"})

    def do_POST(self):
        if self.path != "/v1/channel":
            return self.send_json(404, {"error": "not_found"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 65536:
                raise ValueError("invalid_body_size")
            value = json.loads(self.rfile.read(length))
            if value.get("type") != "command":
                raise ValueError("unsupported_message_type")
            command = send_command(value.get("command", ""))
            self.send_json(202, {"accepted": True, "command": command, "channel": snapshot()})
        except (ValueError, RuntimeError, json.JSONDecodeError) as error:
            self.send_json(400, {"error": str(error)})

    def log_message(self, _format, *_args):
        return


def shutdown(_signal, _frame):
    try:
        send_command("exit")
        PROCESS.wait(timeout=20)
    except Exception:
        if PROCESS and PROCESS.poll() is None:
            PROCESS.terminate()


write_config()
master, slave = pty.openpty()
MASTER_FD = master
PROCESS = subprocess.Popen(
    ["/vanilla/TerrariaServer", "-x64", "-config", "/config/serverconfig.txt", "-banlist", "/config/banlist.txt"],
    stdin=slave,
    stdout=slave,
    stderr=slave,
    close_fds=True,
)
os.close(slave)
signal.signal(signal.SIGTERM, shutdown)
signal.signal(signal.SIGINT, shutdown)
threading.Thread(target=read_output, daemon=True).start()
threading.Thread(target=ThreadingHTTPServer(("0.0.0.0", ADMIN_PORT), Handler).serve_forever, daemon=True).start()
event("presentation.update", {"terraria.world": WORLD_NAME, "terraria.gamePort": GAME_PORT})
while PROCESS.poll() is None:
    event("metric.update", {"terraria.uptimeSeconds": int(time.time() - STATE["startedAt"]), "terraria.commands": STATE["commands"]})
    time.sleep(15)
raise SystemExit(PROCESS.returncode or 0)
