# -*- mode: python ; coding: utf-8 -*-
"""TPDF PyInstaller 配置。

按平台分支：
- Windows / Linux：onefile 模式，产物 `dist/TPDF(.exe)` 单文件可执行。
- macOS：onedir 模式，产物 `dist/TPDF.app` 标准 .app 包。
  （macOS 的 .app 本质是目录，无法与 onefile 共存。）
"""
import re
import sys
from pathlib import Path

IS_MAC = sys.platform == "darwin"


ICON_ICO = 'icon/TPDF.ico'
ICON_ICNS = 'icon/TPDF.icns'


# 从 pyproject.toml 读取版本，保持唯一来源
def _read_version() -> str:
    try:
        text = (Path(SPECPATH) / "pyproject.toml").read_text(encoding="utf-8")
        m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
        return m.group(1) if m else "0.0.0"
    except Exception:
        return "0.0.0"


VERSION = _read_version()


a = Analysis(
    ['TPDF.py'],
    pathex=[],
    binaries=[],
    # 把 icon/ 目录整体打包进产物，让打包后的应用也能读到运行时窗口图标
    datas=[('icon', 'icon')],
    hiddenimports=['fitz'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)


if IS_MAC:
    # —— macOS：onedir + .app bundle ——
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name='TPDF',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name='TPDF',
    )
    app = BUNDLE(
        coll,
        name='TPDF.app',
        icon=ICON_ICNS,
        bundle_identifier='com.tpdf.app',
        info_plist={
            'CFBundleName': 'TPDF',
            'CFBundleDisplayName': 'TPDF',
            'CFBundleShortVersionString': VERSION,
            'CFBundleVersion': VERSION,
            'NSHighResolutionCapable': 'True',
        },
    )
else:
    # —— Windows / Linux：onefile ——
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name='TPDF',
        icon=ICON_ICO,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
