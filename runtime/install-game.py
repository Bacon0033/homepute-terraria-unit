"""Install the exact managed dedicated server distributed by Re-Logic."""
import hashlib
import os
import platform
from pathlib import Path
import shutil
from zipfile import ZipFile

VERSION = "1458"
SHA256 = "f513a4ac9789d34af766291ae217c9cd7d9472e13782a0e2b17512f70d7a8334"
target = os.environ.get("TARGETARCH") or platform.machine()
bundled_runtime = target in ("amd64", "x86_64")
with open("/tmp/terraria-server.zip", "rb") as archive:
    if hashlib.file_digest(archive, "sha256").hexdigest() != SHA256:
        raise ValueError("Dedicated server archive checksum mismatch")
    with ZipFile(archive) as files:
        for info in files.infolist():
            prefix = f"{VERSION}/Linux/"
            if not info.filename.startswith(prefix) or info.is_dir():
                continue
            relative = Path(info.filename[len(prefix):])
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("Unexpected archive path")
            native_assets = relative.parts[0] in ("lib64", "lib", "lib32") or relative.name.startswith(("mscorlib.", "System.", "Mono.")) or relative.name in ("TerrariaServer", "TerrariaServer.bin.x86_64")
            if native_assets and not bundled_runtime:
                continue
            dest = Path("/vanilla") / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            with files.open(info) as src, dest.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            if relative.name == "TerrariaServer.bin.x86_64":
                dest.chmod(0o755)
assert Path("/vanilla/TerrariaServer.exe").is_file()
