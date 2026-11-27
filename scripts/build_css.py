"""Собирает Tailwind CSS через standalone CLI без Node.js."""

import os
import platform
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION = "v3.4.17"
CACHE_DIR = ROOT / ".cache" / "tailwind"
RELEASE_URL = (
    "https://github.com/tailwindlabs/tailwindcss/releases/download/"
    f"{VERSION}/{{binary}}"
)


def binary_name() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "windows":
        return "tailwindcss-windows-x64.exe"
    if system == "darwin":
        return "tailwindcss-macos-arm64" if "arm" in machine else "tailwindcss-macos-x64"
    if machine in ("x86_64", "amd64"):
        return "tailwindcss-linux-x64"
    return "tailwindcss-linux-arm64"


def ensure_binary() -> Path:
    name = binary_name()
    target = CACHE_DIR / name
    if target.exists():
        return target

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    url = RELEASE_URL.format(binary=name)
    print(f"Загрузка Tailwind CLI: {url}")
    request = urllib.request.Request(
        url, headers={"User-Agent": "MT-marks-tracker-build/1.0"}
    )
    tmp = target.with_suffix(target.suffix + ".tmp")
    with urllib.request.urlopen(request, timeout=120) as response, open(tmp, "wb") as handle:
        while chunk := response.read(1024 * 1024):
            handle.write(chunk)

    if os.name != "nt":
        tmp.chmod(0o755)
    os.replace(tmp, target)
    return target


def main() -> int:
    binary = ensure_binary()
    command = [
        str(binary),
        "-i",
        "assets/input.css",
        "-o",
        "assets/app.css",
        "-c",
        "tailwind.config.js",
        "--minify",
    ]
    print("Сборка assets/app.css...")
    subprocess.run(command, cwd=ROOT, check=True)
    output = ROOT / "assets" / "app.css"
    print(f"Готово: {output} ({output.stat().st_size / 1024:.1f} КБ)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
