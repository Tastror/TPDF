"""TPDF 发布构建脚本：一键产出带 `OS + 架构 + 版本号` 命名的发布产物。

⚠️ 关于"交叉编译"
---------------------
PyInstaller **不支持**真正的跨平台编译（Windows 上没法打出 macOS `.app`，反过来也不行）。
本脚本是"多平台发布流程"而不是"交叉编译"：你需要在 **每一个目标 OS 上各跑一次**，
它会自动识别当前系统，把产物统一规范命名并放进 `dist/release/`。

所有平台的产物汇总到同一个 `dist/release/` 目录后，再用 `release_publish.py` 一次性上传到 GitHub Release。

用法
----
    uv run --extra build python release_build.py              # 增量构建 + 命名
    uv run --extra build python release_build.py --clean      # 清理 build/ dist/ 后构建（发布建议用这个）
    uv run --extra build python release_build.py --keep-raw   # 保留 dist/ 下 PyInstaller 原始产物

命名规则（`dist/release/` 下）
-----------------------------
    Windows x64:    TPDF-v{version}-windows-x64.exe
    Windows arm64:  TPDF-v{version}-windows-arm64.exe
    Linux   x64:    TPDF-v{version}-linux-x64
    Linux   arm64:  TPDF-v{version}-linux-arm64
    macOS   arm64:  TPDF-v{version}-macos-arm64.zip     （zip 内是 TPDF.app，用 ditto 打包以保留可执行位）
    macOS   x64:    TPDF-v{version}-macos-x64.zip

每个产物旁会同时生成 `.sha256` 校验文件，方便上传后核对。
"""
from __future__ import annotations

import argparse
import hashlib
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
PYPROJECT = ROOT / "pyproject.toml"
DIST = ROOT / "dist"
RELEASE_DIR = DIST / "release"


def read_version() -> str:
    text = PYPROJECT.read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
    if not m:
        print("错误：无法从 pyproject.toml 读取 version。", file=sys.stderr)
        sys.exit(1)
    return m.group(1)


def detect_os_arch() -> tuple[str, str]:
    """返回 (os_label, arch_label)，用于文件命名。"""
    system = platform.system()
    machine = platform.machine().lower()

    if system == "Windows":
        os_label = "windows"
    elif system == "Darwin":
        os_label = "macos"
    elif system == "Linux":
        os_label = "linux"
    else:
        os_label = system.lower()

    # 归一化常见 arch 标签
    if machine in ("amd64", "x86_64", "x64"):
        arch_label = "x64"
    elif machine in ("arm64", "aarch64"):
        arch_label = "arm64"
    elif machine in ("x86", "i386", "i686"):
        arch_label = "x86"
    else:
        arch_label = machine or "unknown"

    return os_label, arch_label


def run(cmd: list[str]) -> None:
    print("▶", " ".join(cmd))
    rc = subprocess.call(cmd, cwd=ROOT)
    if rc != 0:
        print(f"命令失败（退出码 {rc}）：{' '.join(cmd)}", file=sys.stderr)
        sys.exit(rc)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024
    return f"{n:.1f} TB"


def finalize_windows(version: str, arch: str) -> Path:
    src = DIST / "TPDF.exe"
    if not src.exists():
        raise FileNotFoundError(f"未找到 {src}，PyInstaller 可能失败。")
    dst = RELEASE_DIR / f"TPDF-v{version}-windows-{arch}.exe"
    shutil.copy2(src, dst)
    return dst


def finalize_linux(version: str, arch: str) -> Path:
    src = DIST / "TPDF"
    if not src.exists():
        raise FileNotFoundError(f"未找到 {src}，PyInstaller 可能失败。")
    dst = RELEASE_DIR / f"TPDF-v{version}-linux-{arch}"
    shutil.copy2(src, dst)
    # 确保可执行位
    dst.chmod(dst.stat().st_mode | 0o111)
    return dst


def finalize_macos(version: str, arch: str) -> Path:
    app = DIST / "TPDF.app"
    if not app.exists():
        raise FileNotFoundError(f"未找到 {app}，PyInstaller 可能失败。")
    dst = RELEASE_DIR / f"TPDF-v{version}-macos-{arch}.zip"
    if dst.exists():
        dst.unlink()
    # `ditto` 会保留可执行位、符号链接和扩展属性，比 shutil.make_archive 更安全
    run([
        "ditto", "-c", "-k",
        "--sequesterRsrc", "--keepParent",
        str(app), str(dst),
    ])
    return dst


FINALIZERS = {
    "Windows": finalize_windows,
    "Linux": finalize_linux,
    "Darwin": finalize_macos,
}


def build(clean: bool) -> None:
    """调用 build.py 完成"uv sync + pyinstaller"。保持构建逻辑单一入口。"""
    cmd = [sys.executable, str(ROOT / "build.py")]
    if clean:
        cmd.append("--clean")
    run(cmd)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="TPDF 发布构建：自动识别平台 / 架构 / 版本号，规范命名产物。"
    )
    ap.add_argument("--clean", action="store_true",
                    help="构建前清理 build/ dist/（发布强烈建议开启）")
    ap.add_argument("--keep-raw", action="store_true",
                    help="保留 dist/ 下 PyInstaller 原始产物（默认只保留 dist/release/）")
    args = ap.parse_args()

    version = read_version()
    os_label, arch_label = detect_os_arch()
    system = platform.system()

    finalizer = FINALIZERS.get(system)
    if finalizer is None:
        print(f"错误：不支持的操作系统 {system}", file=sys.stderr)
        return 1

    print(f"▶ 目标产物：TPDF v{version}  ({os_label}-{arch_label})")

    build(clean=args.clean)

    RELEASE_DIR.mkdir(parents=True, exist_ok=True)

    try:
        artifact = finalizer(version, arch_label)
    except FileNotFoundError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 1

    # 生成 sha256
    digest = sha256_of(artifact)
    sha_file = artifact.with_suffix(artifact.suffix + ".sha256")
    sha_file.write_text(f"{digest}  {artifact.name}\n", encoding="utf-8")

    # 清理 dist/ 下 PyInstaller 中间产物，只保留 release/
    if not args.keep_raw:
        for entry in DIST.iterdir():
            if entry.resolve() == RELEASE_DIR.resolve():
                continue
            if entry.is_dir():
                shutil.rmtree(entry, ignore_errors=True)
            else:
                try:
                    entry.unlink()
                except OSError:
                    pass

    size = human_size(artifact.stat().st_size)
    print("\n✓ 发布产物已生成：")
    print(f"    {artifact}")
    print(f"    大小：{size}")
    print(f"    sha256：{digest}")
    print(f"    校验文件：{sha_file.name}")
    print("\n下一步：在所有目标平台都跑完本脚本后，执行 `python release_publish.py` 一键发布。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
