"""Select and install Re-Logic's Linux dedicated server for the native CPU."""
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import tempfile
from urllib.request import Request, urlopen
from zipfile import ZipFile

BUNDLED = "1458"
BUNDLED_SHA256 = "f513a4ac9789d34af766291ae217c9cd7d9472e13782a0e2b17512f70d7a8334"
SITE = "https://www.terraria.org"
ARCHIVE_LIMIT = 256 * 1024 * 1024


def official_download(path, timeout):
    request = Request(SITE + path, headers={"User-Agent": "Homepute/1.2 (Terraria dedicated server installer)", "Accept": "*/*"})
    return urlopen(request, timeout=timeout)


def resolve_release(selection):
    selection = selection.strip()
    if selection.upper() == "LATEST":
        with official_download("/api/get/dedicated-servers-names", timeout=12) as reply:
            names = json.loads(reply.read(4096))
        if not isinstance(names, list) or not names or not isinstance(names[0], str):
            raise ValueError("Unexpected Terraria PC release feed")
        match = re.fullmatch(r"terraria-server-(\d{3,8})\.zip", names[0])
        if not match:
            raise ValueError("Invalid PC archive in Terraria release feed")
        return match[1]
    if not re.fullmatch(r"1(?:\.\d{1,2}){2,3}|\d{3,8}", selection):
        raise ValueError("Enter LATEST or a Terraria release such as 1.4.5.8")
    return selection.replace(".", "")


def unpack(archive, version, dest, architecture):
    if version == BUNDLED:
        with archive.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != BUNDLED_SHA256:
                raise ValueError("Bundled Terraria archive checksum mismatch")
    prefix = version + "/Linux/"
    with ZipFile(archive) as files:
        if sum(i.file_size for i in files.infolist() if i.filename.startswith(prefix)) > ARCHIVE_LIMIT:
            raise ValueError("Terraria game files exceed the size limit")
        for info in files.infolist():
            if not info.filename.startswith(prefix) or info.is_dir():
                continue
            relative = Path(info.filename[len(prefix):])
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("Unexpected archive path")
            if architecture not in ("amd64", "x86_64") and (
                relative.parts[0] in ("lib64", "lib", "lib32")
                or relative.name.startswith(("mscorlib.", "System.", "Mono.", "TerrariaServer.bin."))
                or relative.name == "TerrariaServer"
            ):
                continue
            path = dest / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            with files.open(info) as src, path.open("wb") as out:
                shutil.copyfileobj(src, out)
            if relative.name == "TerrariaServer.bin.x86_64":
                path.chmod(0o755)
    if not (dest / "TerrariaServer.exe").is_file():
        raise ValueError("Release does not contain a supported Linux dedicated server")


def game_directory(selection):
    try:
        version = resolve_release(selection)
    except (OSError, ValueError) as error:
        if selection.strip().upper() != "LATEST":
            raise
        # Stay on the last resolved release during a feed outage.
        marker = Path("/config/.last-terraria-release")
        version = marker.read_text().strip() if marker.is_file() else BUNDLED
        if not re.fullmatch(r"\d{3,8}", version):
            raise ValueError("Invalid cached Terraria release") from error
        print(f"Terraria release feed unavailable, using cached release {version}", flush=True)
    dest = Path("/vanilla") if version == BUNDLED else Path.home() / ("game-" + version)
    if not (dest / "TerrariaServer.exe").is_file():
        url = f"/api/download/pc-dedicated-server/terraria-server-{version}.zip"
        print(f"Installing official Terraria server {version}", flush=True)
        with tempfile.TemporaryDirectory(dir=dest.parent) as staging:
            archive = Path(staging) / "server.zip"
            with official_download(url, timeout=60) as reply, archive.open("wb") as out:
                while chunk := reply.read(1024 * 1024):
                    if out.tell() + len(chunk) > ARCHIVE_LIMIT:
                        raise ValueError("Terraria archive exceeds the size limit")
                    out.write(chunk)
            unpack(archive, version, Path(staging) / "game", platform.machine())
            os.rename(Path(staging) / "game", dest)
    if selection.strip().upper() == "LATEST":
        (Path("/config/.last-terraria-release")).write_text(version)
    return dest, version
