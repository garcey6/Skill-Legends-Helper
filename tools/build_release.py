"""Build a one-folder PyInstaller release with a safe runtime payload.

The release deliberately uses one-folder mode: the recognition assets are tens of
megabytes, and one-file mode would unpack them to a temp directory on every run.
The build dependency lives in ``requirements-build.txt``; it is not a runtime
dependency and must not be added to ``requirements.txt``.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

APP_NAME = "XuanJiHelper"
DEFAULT_OUT = ROOT / "dist"
DEFAULT_WORK = ROOT / "build" / "release"

DATA_FORBIDDEN_FILES = {
    "data/settings.json",
    "data/server_url.txt",
    "data/overlay_position.json",
    "data/meta_stats.json",
}
DATA_FORBIDDEN_DIRS = {
    "data/captures",
    "data/uploads",
    "data/source",
    "data/__pycache__",
}
TOP_LEVEL_FILES = ("README.md", "LICENSE", "CHANGELOG.md")
DOC_FILES = ("USER_GUIDE.md", "RISK.md", "DEVELOPMENT.md", "HOLDOUT.md", "RELEASE.md", "ROADMAP.md")


@dataclass(frozen=True)
class ReleaseFile:
    source: Path
    arcname: str


def _is_forbidden_data(relative: str) -> bool:
    normalized = relative.replace("\\", "/")
    if normalized in DATA_FORBIDDEN_FILES:
        return True
    if normalized.endswith(".pyc") or normalized.endswith("/__pycache__"):
        return True
    if any(normalized == item or normalized.startswith(item + "/") for item in DATA_FORBIDDEN_DIRS):
        return True
    return False


def _walk_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if path.is_file():
            yield path


def collect_release_files(root: Path = ROOT) -> List[ReleaseFile]:
    """Return runtime files only; secrets and local state never enter the zip."""
    root = Path(root)
    if not root.is_dir():
        raise FileNotFoundError(f"project root not found: {root}")

    collected: List[ReleaseFile] = []

    data_root = root / "data"
    if data_root.is_dir():
        for path in _walk_files(data_root):
            relative = path.relative_to(root).as_posix()
            if not _is_forbidden_data(relative):
                collected.append(ReleaseFile(path, relative))

    static_root = root / "static"
    if static_root.is_dir():
        for path in _walk_files(static_root):
            collected.append(ReleaseFile(path, path.relative_to(root).as_posix()))

    for name in TOP_LEVEL_FILES:
        path = root / name
        if path.is_file():
            collected.append(ReleaseFile(path, name))

    docs_root = root / "docs"
    if docs_root.is_dir():
        for name in DOC_FILES:
            path = docs_root / name
            if path.is_file():
                collected.append(ReleaseFile(path, f"docs/{name}"))

    seen: set[str] = set()
    unique: List[ReleaseFile] = []
    for item in collected:
        if item.arcname in seen:
            continue
        seen.add(item.arcname)
        unique.append(item)
    return sorted(unique, key=lambda item: item.arcname)


def sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def write_checksum(archive: Path) -> Path:
    archive = Path(archive)
    digest = sha256_file(archive)
    target = archive.with_name(archive.name + ".sha256")
    target.write_text(f"{digest}  {archive.name}\n", encoding="ascii")
    return target


def read_version(root: Path = ROOT) -> str:
    init = Path(root) / "app" / "__init__.py"
    for line in init.read_text(encoding="utf-8").splitlines():
        if line.startswith("__version__"):
            return line.split("=", 1)[1].strip().strip("\"'")
    raise ValueError(f"no __version__ in {init}")


def release_manifest(
    files: Sequence[ReleaseFile],
    *,
    version: str,
    built_at: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "name": APP_NAME,
        "version": version,
        "built_at": built_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "python": platform.python_version(),
        "platform": platform.system().lower(),
        "files": [
            {"path": item.arcname, "sha256": sha256_file(item.source), "bytes": item.source.stat().st_size}
            for item in files
        ],
    }


def stage_payload(files: Sequence[ReleaseFile], stage: Path) -> None:
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    for item in files:
        destination = stage / item.arcname
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item.source, destination)


def _pyinstaller_command(
    *,
    root: Path,
    entry: Path,
    stage: Path,
    dist: Path,
    work: Path,
    spec: Path,
    name: str,
) -> List[str]:
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--onedir",
        "--name",
        name,
        "--distpath",
        str(dist),
        "--workpath",
        str(work),
        "--specpath",
        str(spec),
        "--paths",
        str(root),
        "--add-data",
        f"{stage}{os.pathsep}.",
        str(entry),
    ]
    # Test-only dependencies must never leak into a release even if the build
    # environment happens to have them installed.
    for module in ("pytest", "_pytest", "tests", "test"):
        command.extend(["--exclude-module", module])
    if importlib.util.find_spec("rapidocr_onnxruntime") is not None:
        command.extend(["--collect-all", "rapidocr_onnxruntime"])
    return command


def _zip_release(dist: Path, folder: str, archive: Path) -> Path:
    if archive.exists():
        archive.unlink()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as handle:
        for path in sorted(dist.joinpath(folder).rglob("*")):
            if path.is_file():
                handle.write(path, path.relative_to(dist).as_posix())
    return archive


def build(
    *,
    out: Path = DEFAULT_OUT,
    work: Path = DEFAULT_WORK,
    dry_run: bool = False,
    root: Path = ROOT,
) -> Dict[str, Any]:
    files = collect_release_files(root)
    version = read_version(root)
    manifest = release_manifest(files, version=version)

    if dry_run:
        print(f"{APP_NAME} {version}: {len(files)} files, {sum(item.source.stat().st_size for item in files)} bytes")
        for item in files:
            print(f"  {item.arcname}")
        return manifest

    if importlib.util.find_spec("PyInstaller") is None:
        raise SystemExit(
            "未安装 PyInstaller。请先执行：\n"
            "  python -m pip install -r requirements-build.txt\n"
            "（构建依赖不进入 requirements.txt）"
        )

    out = Path(out)
    work = Path(work)
    out.mkdir(parents=True, exist_ok=True)
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    stage = work / "payload"
    stage_payload(files, stage)

    app_dir = out / APP_NAME
    if app_dir.exists():
        shutil.rmtree(app_dir)
    spec_dir = work / "spec"
    spec_dir.mkdir()
    command = _pyinstaller_command(
        root=root,
        entry=Path(root) / "agent.py",
        stage=stage,
        dist=out,
        work=work / "pyinstaller",
        spec=spec_dir,
        name=APP_NAME,
    )
    subprocess.run(command, check=True, cwd=str(root))

    exe = app_dir / f"{APP_NAME}.exe"
    if not exe.is_file():
        raise SystemExit(f"PyInstaller finished but {exe} is missing")

    (app_dir / "release.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    archive = out / f"{APP_NAME}-{version}-windows-x64.zip"
    _zip_release(out, APP_NAME, archive)
    checksum = write_checksum(archive)
    print(f"发行包：{archive}")
    print(f"校验值：{checksum.read_text(encoding='ascii').strip()}")
    return manifest


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--work", type=Path, default=DEFAULT_WORK)
    parser.add_argument("--dry-run", action="store_true", help="只列出会打包的文件")
    args = parser.parse_args(argv)
    try:
        build(out=args.out, work=args.work, dry_run=args.dry_run)
    except subprocess.CalledProcessError as exc:
        print(f"PyInstaller 失败，退出码 {exc.returncode}", file=sys.stderr)
        return exc.returncode or 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
