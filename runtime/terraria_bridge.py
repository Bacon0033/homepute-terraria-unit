#!/usr/bin/env python3
import codecs
import collections
import hmac
import json
import os
import pty
import re
from pathlib import Path
from game_release import game_directory
import select
import signal
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

GAME_PORT = int(os.environ.get("TERRARIA_PORT", "7777"))
ADVERTISED_PORT = int(os.environ.get("TERRARIA_HOST_PORT", str(GAME_PORT)))
ADMIN_PORT = int(os.environ.get("HOMEPUTE_CHANNEL_PORT", "8080"))
WORLD_NAME = os.environ.get("TERRARIA_WORLD_NAME", "Homepute World")[:80]
WORLD_SIZE = max(1, min(3, int(os.environ.get("TERRARIA_WORLD_SIZE", "2"))))
MAX_PLAYERS = max(1, min(255, int(os.environ.get("TERRARIA_MAX_PLAYERS", "8"))))
PASSWORD = os.environ.get("TERRARIA_PASSWORD", "")[:128]
MOTD = os.environ.get("TERRARIA_MOTD", "Hosted on Homepute")[:256]
WORLD_PATH = "/config/homepute.wld"
LOGS = collections.deque(maxlen=500)
STATE = {"ready": False, "startedAt": time.time(), "commands": 0, "lastLineAt": None}
SAMPLES = collections.deque(maxlen=120)
MASTER_FD = None
PROCESS = None


def event(kind, values):
    print("HOMEPUTE_EVENT_V1 " + json.dumps({"version": 1, "type": kind, "values": values}, separators=(",", ":")), flush=True)


def record(line):
    line = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", line).rstrip("\r\n")[:2048]
    if not line:
        return
    entry = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "message": line}
    LOGS.append(entry)
    banner = re.search(r"Terraria Server v([0-9.]+)", line)
    if banner:
        STATE["gameVersion"] = banner[1]
        event("presentation.update", {"terraria.version": banner[1]})
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
        "upnp=0",
        "secure=1",
        "language=en-US",
    ]
    with open("/config/serverconfig.txt", "w", encoding="utf-8") as config:
        config.write("\n".join(line.replace("\n", " ").replace("\r", " ") for line in values) + "\n")
    open("/config/banlist.txt", "a", encoding="utf-8").close()


def read_output():
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    pending = ""
    while True:
        ready, _, _ = select.select([MASTER_FD], [], [], 1.0)
        if not ready:
            if PROCESS.poll() is not None:
                break
            continue
        try:
            data = os.read(MASTER_FD, 4096)
        except OSError:
            break
        if not data:
            break
        lines = re.split(r"[\r\n]", pending + decoder.decode(data))
        pending = lines.pop()[:2048]
        for line in lines:
            record(line)
    record(pending + decoder.decode(b"", final=True))


def send_command(command):
    if not PROCESS or PROCESS.poll() is not None or MASTER_FD is None:
        raise RuntimeError("server_not_running")
    command = str(command).strip()
    if not command or len(command) > 512 or any(ord(c) < 32 for c in command):
        raise ValueError("command_required")
    os.write(MASTER_FD, (command + "\n").encode("utf-8"))
    STATE["commands"] += 1
    return command


def measure_game():
    previous = None
    ticks = os.sysconf("SC_CLK_TCK")
    while PROCESS.poll() is None:
        try:
            # /proc/PID/stat fields 14 and 15 are user and kernel CPU ticks.
            fields = Path(f"/proc/{PROCESS.pid}/stat").read_text().rsplit(")", 1)[1].split()
            cpu = (int(fields[11]) + int(fields[12])) / ticks
            now = time.monotonic()
            pages = int(Path(f"/proc/{PROCESS.pid}/statm").read_text().split()[1])
            if previous:
                usage = round(100 * (cpu - previous[0]) / (now - previous[1]), 1)
                SAMPLES.append({"time": int(time.time()), "cpuPercent": usage,
                                "memoryMiB": round(pages * os.sysconf("SC_PAGE_SIZE") / 1048576, 1)})
            previous = (cpu, now)
        except (OSError, ValueError, IndexError):
            pass
        time.sleep(2)


def snapshot(include_logs=False):
    running = PROCESS is not None and PROCESS.poll() is None
    return {
        "version": 1,
        "kind": "homepute.data-channel.snapshot",
        "service": "terraria",
        "running": running,
        "ready": running and STATE["ready"],
        "gamePort": ADVERTISED_PORT,
        "world": WORLD_NAME,
        "gameVersion": STATE.get("gameVersion", RELEASE),
        "samples": list(SAMPLES),
        "consoleAuthorized": include_logs,
        "maxPlayers": MAX_PLAYERS,
        "commandsAccepted": STATE["commands"],
        "uptimeSeconds": max(0, int(time.time() - STATE["startedAt"])),
        "logs": list(LOGS)[-100:] if include_logs else [],
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

    def dashboard_authorized(self):
        key = os.environ.get("TERRARIA_CONSOLE_KEY", "")
        supplied = self.headers.get("X-Terraria-Console-Key", "")
        return len(key) >= 16 and hmac.compare_digest(supplied.encode(), key.encode())

    def do_GET(self):
        if self.path == "/health":
            return self.send_json(200 if STATE["ready"] and PROCESS and PROCESS.poll() is None else 503, {"ok": bool(PROCESS and PROCESS.poll() is None), "ready": STATE["ready"]})
        if self.path == "/v1/channel":
            return self.send_json(200, snapshot(self.dashboard_authorized()))
        self.send_json(404, {"error": "not_found"})

    def do_POST(self):
        if self.path == "/actions/console":
            token = os.environ.get("HOMEPUTE_API_TOKEN", "")
            deployment = os.environ.get("HOMEPUTE_DEPLOYMENT_ID", "")
            if not token or not deployment or not hmac.compare_digest(self.headers.get("Authorization", "").encode(), ("Bearer " + token).encode()) or self.headers.get("X-Homepute-Deployment") != deployment:
                return self.send_json(403, {"error": "forbidden"})
            try:
                size = int(self.headers.get("Content-Length", 0))
                if not 0 < size <= 4096:
                    raise ValueError("invalid_body_size")
                message = json.loads(self.rfile.read(size))
                if not isinstance(message, dict) or not isinstance(message.get("command"), str):
                    raise ValueError("command_required")
                send_command(message["command"])
                return self.send_json(200, {"message": "Command delivered to Terraria"})
            except (ValueError, RuntimeError) as error:
                return self.send_json(400, {"error": str(error)})
        if self.path != "/v1/channel":
            return self.send_json(404, {"error": "not_found"})
        if not self.dashboard_authorized():
            return self.send_json(403, {"error": "Owner console key required"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 65536:
                raise ValueError("invalid_body_size")
            value = json.loads(self.rfile.read(length))
            if not isinstance(value, dict) or value.get("type") != "command" or not isinstance(value.get("command"), str):
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


# Older releases created root-owned worlds. Migrate only the dedicated volume,
# leave symbolic links untouched, and run the game and HTTP service unprivileged.
if os.geteuid() == 0:
    import pwd
    user = pwd.getpwnam("terraria")
    for base, dirs, files, fd in os.fwalk("/config", follow_symlinks=False):
        os.fchown(fd, user.pw_uid, user.pw_gid)
        for name in files:
            os.chown(name, user.pw_uid, user.pw_gid, dir_fd=fd, follow_symlinks=False)
    os.setgroups([])
    os.setgid(user.pw_gid)
    os.setuid(user.pw_uid)
    os.environ["HOME"] = user.pw_dir
os.umask(0o077)
write_config()
master, slave = pty.openpty()
MASTER_FD = master
game_dir, RELEASE = game_directory(os.environ.get("TERRARIA_VERSION", "LATEST"))
bundled = game_dir / "TerrariaServer.bin.x86_64"
launcher = [bundled] if bundled.is_file() else ["mono", game_dir / "TerrariaServer.exe"]
os.environ["MONO_IOMAP"] = "all"
PROCESS = subprocess.Popen(
    [*launcher, "-config", "/config/serverconfig.txt", "-banlist", "/config/banlist.txt"],
    cwd=game_dir,
    stdin=slave,
    stdout=slave,
    stderr=slave,
    close_fds=True,
)
os.close(slave)
signal.signal(signal.SIGTERM, shutdown)
signal.signal(signal.SIGINT, shutdown)
threading.Thread(target=measure_game, daemon=True).start()
threading.Thread(target=read_output, daemon=True).start()
threading.Thread(target=ThreadingHTTPServer(("0.0.0.0", ADMIN_PORT), Handler).serve_forever, daemon=True).start()
event("presentation.update", {"terraria.world": WORLD_NAME, "terraria.gamePort": ADVERTISED_PORT})
while PROCESS.poll() is None:
    event("metric.update", {"terraria.uptimeSeconds": int(time.time() - STATE["startedAt"]), "terraria.commands": STATE["commands"]})
    try:
        PROCESS.wait(timeout=15)
    except subprocess.TimeoutExpired:
        pass
raise SystemExit(PROCESS.returncode or 0)
