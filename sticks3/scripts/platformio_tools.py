"""Use the target-local native filesystem builder when one has been prepared."""
from pathlib import Path

Import("env")
native = Path(env.subst("$PROJECT_DIR")) / ".local/mklittlefs-src/mklittlefs"
if native.is_file():
    env.Replace(MKFSTOOL=str(native))
