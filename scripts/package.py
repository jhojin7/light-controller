"""Package an explicit list of application files, excluding local secrets."""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from check import check_project

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    "code.py",
    "boot.py",
    "config.json",
    "settings.toml.example",
    "README.md",
    "LICENSE",
    "docs/SETUP_GUIDE.md",
    "docs/FEATURE_MAP.md",
    "docs/TESTING.md",
    "assets/ui-preview.png",
)


def package_project():
    check_project()
    destination = ROOT / "dist" / "light-controller.zip"
    destination.parent.mkdir(exist_ok=True)
    temporary = destination.with_suffix(".zip.tmp")
    try:
        with ZipFile(temporary, "w", compression=ZIP_DEFLATED) as archive:
            for name in FILES:
                source = 'config.json.example' if name == 'config.json' else name
                archive.write(ROOT / source, arcname=name)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"Created {destination}")


if __name__ == "__main__":
    package_project()
