# -*- mode: python ; coding: utf-8 -*-
"""TPDF PyInstaller 配置。

按平台分支：
- Windows / Linux：onefile 模式，产物 `dist/TPDF(.exe)` 单文件可执行。
- macOS：onedir 模式，产物 `dist/TPDF.app` 标准 .app 包。
  （macOS 的 .app 本质是目录，无法与 onefile 共存。）
"""
import sys

IS_MAC = sys.platform == "darwin"


a = Analysis(
    ['TPDF.py'],
    pathex=[],
    binaries=[],
    datas=[],
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
        icon=None,
        bundle_identifier='com.tpdf.app',
        info_plist={
            'CFBundleName': 'TPDF',
            'CFBundleDisplayName': 'TPDF',
            'CFBundleShortVersionString': '1.0.0',
            'CFBundleVersion': '1.0.0',
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
