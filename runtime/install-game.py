import os
from pathlib import Path
import platform
from game_release import BUNDLED, unpack

unpack(Path("/tmp/terraria-server.zip"), BUNDLED, Path("/vanilla"),
       os.environ.get("TARGETARCH") or platform.machine())
