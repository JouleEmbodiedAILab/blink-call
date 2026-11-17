"""Package a standalone build with source provenance and SHA-256 checksums."""

import hashlib
import json
import platform
import struct
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    root = Path(__file__).resolve().parents[2]
    distribution = Path(sys.argv[1]).resolve()
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    required = (
        "BlinkCall.exe",
        "VERSION",
        "LICENSE",
        "assets/audio/prompt.wav",
        "assets/audio/ring_01.wav",
        "assets/icons/app_icon.ico",
        "assets/qss/light.qss",
        "assets/qss/dark.qss",
    )
    for name in required:
        if not (distribution / name).is_file():
            raise RuntimeError(f"Required release file is missing: {name}")
    if (distribution / "VERSION").read_text(encoding="utf-8").strip() != version:
        raise RuntimeError("Packaged version does not match the source VERSION.")
    with (distribution / "BlinkCall.exe").open("rb") as stream:
        header = stream.read(4096)
    if header[:2] != b"MZ":
        raise RuntimeError("Release executable is not a Windows PE file.")
    offset = struct.unpack_from("<I", header, 0x3C)[0]
    if header[offset : offset + 4] != b"PE\0\0" or struct.unpack_from("<H", header, offset + 4)[0] != 0x8664:
        raise RuntimeError("Release executable is not Windows x64.")
    if subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"], cwd=root).strip():
        raise RuntimeError("Tracked source files changed during the build.")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    build_info = {
        "version": version,
        "source_commit": commit,
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "executable_sha256": sha256(distribution / "BlinkCall.exe"),
        "dependencies": dict(sorted((item.metadata["Name"], item.version) for item in metadata.distributions())),
    }
    info_text = json.dumps(build_info, ensure_ascii=False, indent=2) + "\n"
    output = root / "dist/windows"
    output.mkdir(parents=True, exist_ok=True)
    archive_path = output / f"BlinkCall-windows-x64-v{version}.zip"
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(distribution.rglob("*")):
            relative = path.relative_to(distribution)
            if path.is_file() and not {"configs", "logs", "__pycache__"}.intersection(relative.parts):
                archive.write(path, relative.as_posix())
        archive.writestr("build-info.json", info_text)
    with zipfile.ZipFile(archive_path) as archive:
        bad_file = archive.testzip()
        if bad_file:
            raise RuntimeError(f"Release ZIP integrity check failed: {bad_file}")
    (output / "build-info.json").write_text(info_text, encoding="utf-8")
    (output / "SHA256SUMS.txt").write_text(f"{sha256(archive_path)}  {archive_path.name}\n", encoding="utf-8")
    print(f"Prepared {archive_path.name} from {commit}; ZIP integrity verified.")


if __name__ == "__main__":
    main()
