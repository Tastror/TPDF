"""TPDF 打包脚本（跨平台，基于 uv + PyInstaller）。

用法：
    uv run --extra build python build.py             # 同步依赖并打包
    uv run --extra build python build.py --clean     # 先清理 build/ dist/
    python build.py --no-sync                         # 跳过 uv sync（调试用）

产物：
    Windows:  dist/TPDF.exe          （onefile，单文件可执行）
    macOS:    dist/TPDF.app          （onedir 打包的标准 .app 包）
    Linux:    dist/TPDF              （onefile，单文件可执行）

先决条件：
    - 安装 uv：https://docs.astral.sh/uv/（或 `pipx install uv` / `brew install uv`）
    - 第一次执行会自动下载 Python（按 pyproject.toml 的 requires-python），
      并在 ./.venv/ 下安装 pillow / pymupdf / pyinstaller。
"""
from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
SPEC = "TPDF.spec"


def run(cmd: list[str]) -> int:
    print("▶", " ".join(cmd))
    return subprocess.call(cmd, cwd=ROOT)


def check_uv() -> None:
    if shutil.which("uv") is None:
        print(
            "错误：未找到 `uv` 命令。请先安装：\n"
            "  Windows (PowerShell):  irm https://astral.sh/uv/install.ps1 | iex\n"
            "  macOS / Linux:         curl -LsSf https://astral.sh/uv/install.sh | sh\n"
            "  或：pipx install uv / brew install uv",
            file=sys.stderr,
        )
        sys.exit(1)


def clean() -> None:
    for name in ("build", "dist"):
        p = ROOT / name
        if p.exists():
            shutil.rmtree(p)
            print(f"  已删除 {p.relative_to(ROOT)}/")


def report_output() -> None:
    system = platform.system()
    dist = ROOT / "dist"
    produced: list[Path] = []
    if system == "Windows":
        for cand in [dist / "TPDF.exe"]:
            if cand.exists():
                produced.append(cand)
    elif system == "Darwin":
        for cand in [dist / "TPDF.app"]:
            if cand.exists():
                produced.append(cand)
    else:
        for cand in [dist / "TPDF"]:
            if cand.exists():
                produced.append(cand)

    if not produced:
        print("\n未在 dist/ 下找到预期产物，请检查上方 PyInstaller 输出。")
        return
    print("\n✓ 打包完成：")
    for p in produced:
        size = _path_size(p)
        size_str = f"{size / 1024 / 1024:.1f} MB" if size else ""
        print(f"    {p}    {size_str}")


def _path_size(p: Path) -> int:
    if p.is_file():
        return p.stat().st_size
    if p.is_dir():
        return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Build TPDF")
    ap.add_argument("--clean", action="store_true",
                    help="先删除 build/ 与 dist/ 再打包")
    ap.add_argument("--no-sync", action="store_true",
                    help="跳过 `uv sync`（默认会执行以确保环境一致）")
    args = ap.parse_args()

    check_uv()

    if args.clean:
        print("▶ 清理 build/ dist/")
        clean()

    if not args.no_sync:
        rc = run(["uv", "sync", "--extra", "build"])
        if rc != 0:
            return rc

    rc = run(["uv", "run", "pyinstaller", "--noconfirm", SPEC])
    if rc != 0:
        return rc

    report_output()
    return 0


if __name__ == "__main__":
    sys.exit(main())
