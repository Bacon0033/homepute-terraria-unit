"""Run two disposable boots of a pinned local image. No router requests are made."""
import hashlib
import http.client
import json
import os
from pathlib import Path
import secrets
import socket
import struct
import subprocess
import sys
import time
import uuid
from world_client import check_world

image = sys.argv[1]
name = "hp-terraria-smoke-" + uuid.uuid4().hex[:14]
volume = name + "-world"
secret = secrets.token_hex(24)
admin = secrets.token_hex(24)
env = {**os.environ, "TERRARIA_CONSOLE_KEY": admin, "HOMEPUTE_API_TOKEN": secret}

def engine(*args):
    return subprocess.check_output(["docker", *args], env=env, text=True).strip()

def call(port, path, value=None, headers=None):
    con = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        con.request("POST" if value is not None else "GET", path, json.dumps(value) if value is not None else None, headers or {})
        response = con.getresponse()
        return response.status, json.loads(response.read())
    finally:
        con.close()

def fingerprint():
    return engine("exec", name, "python3", "-c", "import hashlib;print(hashlib.sha256(open('/config/homepute.wld','rb').read()).hexdigest())")

engine("volume", "create", volume)
try:
    for boot in (1, 2):
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            advertised = reservation.getsockname()[1]
        engine("run", "-d", "--name", name, "-e", "TERRARIA_HOST_PORT=" + str(advertised), "-p", f"127.0.0.1:{advertised}:7777/tcp", "-p", "127.0.0.1::8080/tcp",
               "-e", "TERRARIA_VERSION=1.4.5.8", "-e", "TERRARIA_WORLD_SIZE=1", "-e", "TERRARIA_WORLD_NAME=SDK fixture", "-e", "TERRARIA_CONSOLE_KEY",
               "-e", "HOMEPUTE_API_TOKEN", "-e", "HOMEPUTE_DEPLOYMENT_ID=" + name, "-v", volume + ":/config", image)
        channel = int(engine("port",name,"8080/tcp").split(":")[-1])
        game = int(engine("port",name,"7777/tcp").split(":")[-1])
        for _ in range(180):
            try:
                if call(channel,"/health")[0] == 200:
                    break
            except (OSError, http.client.HTTPException):
                pass
            if engine("inspect","-f","{{.State.Running}}",name) != "true":
                raise RuntimeError("Terraria exited during startup: " + engine("logs", "--tail", "24", name)[-2200:])
            time.sleep(1)
        else:
            raise RuntimeError("Terraria did not finish starting")
        state = call(channel, "/v1/channel")[1]
        assert state["gamePort"] == game == advertised
        assert state["gameVersion"] == "1.4.5.8"
        assert not state["consoleAuthorized"]
        for _ in range(5):
            if call(channel, "/v1/channel")[1]["samples"]:
                break
            time.sleep(1)
        sample = call(channel, "/v1/channel")[1]["samples"][-1]
        assert sample["memoryMiB"] > 0 and sample["cpuPercent"] >= 0
        try:
            if boot == 1 and len(sys.argv) > 2:
                subprocess.run(["node", str(Path(__file__).with_name("gateway-fixture.cjs")), sys.argv[2], str(game)], check=True, timeout=30)
            else:
                for attempt in range(20):
                    try:
                        check_world(game)
                        break
                    except (ConnectionError, TimeoutError):
                        if attempt == 19:
                            raise
                        time.sleep(1)
        except Exception:
            print(engine("logs", "--tail", "30", name)[-3600:], file=sys.stderr)
            print(engine("exec", name, "cat", "/proc/net/tcp", "/proc/net/tcp6"), file=sys.stderr)
            raise
        for attempt in range(10):
            try:
                with socket.create_connection(("127.0.0.1", game), 4) as sock:
                    sock.sendall(bytes([13,0,1,9])+b"Terraria0")
                    with sock.makefile("rb") as wire:
                        header = wire.read(2)
                        if len(header) != 2:
                            raise ConnectionError("Game closed before the protocol reply")
                        length = struct.unpack("<H", header)[0]
                        assert length == 25 and wire.read(length-2) == bytes([2,2,19])+b"LegacyMultiplayer.4"+bytes([0])
                break
            except (ConnectionError, TimeoutError):
                if attempt == 9:
                    raise
                time.sleep(1)
        assert call(channel,"/v1/channel",{"type":"command","command":"playing"})[0] == 403
        assert call(channel,"/v1/channel",{"type":"command","command":"playing"},{"X-Terraria-Console-Key":admin})[0] == 202
        assert call(channel,"/actions/console",{"command":"playing"})[0] == 403
        assert call(channel,"/actions/console",{"command":"playing"},{"Authorization":"Bearer "+secret,"X-Homepute-Deployment":name})[0] == 200
        assert call(channel,"/v1/channel")[1]["logs"]==[]
        if boot==2:
            assert fingerprint()==before, "World contents changed before gameplay on second boot"
        engine("stop","-t","45",name)
        if boot==1:
            copy=engine("run","--rm","--entrypoint","python3","-v",volume+":/saved:ro",image,"-c","import hashlib;print(hashlib.sha256(open('/saved/homepute.wld','rb').read()).hexdigest())")
            assert len(copy)==64
            before=copy
        engine("rm",name)
    print(json.dumps({"boots":2,"architecture":engine("image","inspect","-f","{{.Architecture}}",image),"gameGreeting":True,"worldMetadataReceived":True,"alternateHostPorts":True,"worldRetained":True,"commandsAuthenticated":True,"disposableGateway":len(sys.argv)>2,"routerMappingAttempted":False}))
finally:
    subprocess.run(["docker","rm","-f",name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    engine("volume","rm",volume)
