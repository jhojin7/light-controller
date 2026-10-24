#!/usr/bin/env python3
"""Build a compatible LittleFS image tool natively on Apple Silicon."""
from pathlib import Path
import platform
import subprocess

ROOT = Path(__file__).resolve().parents[1]
REVISION = "975bd0f28e0976c1c018062537c23c8768b09076"  # upstream 3.2.0, disk format 2.0


def main():
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        return
    source = ROOT / ".local/mklittlefs-src"
    if not source.exists():
        source.parent.mkdir(exist_ok=True)
        subprocess.run(["git", "clone", "--recursive", "--depth", "1", "--branch", "3.2.0",
                        "https://github.com/earlephilhower/mklittlefs.git", str(source)], check=True)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    if revision != REVISION:
        raise SystemExit("Native filesystem tool checkout differs from pinned revision")
    # Upstream 3.2 predates these Apple Clang warnings. Keep disk-format 2.0
    # compatibility with Arduino 2.x rather than upgrade the on-device format.
    subprocess.run(["make", "-j4", "CXXFLAGS=-Wno-error=deprecated-declarations -Wno-error=vla-cxx-extension"], cwd=source, check=True)
    subprocess.run([str(source / "mklittlefs"), "--version"], check=True)


if __name__ == "__main__":
    main()
