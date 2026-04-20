# TPDF

一个图形界面的 **图片 ↔ PDF** 工具（中文）。

三个选项卡：

- **图片 → PDF**：把文件夹里的图片合成 PDF。
  - 可单向或双向统一高度 / 宽度。
  - 可按纸张比例（A3 / A4 / A5 / B4 / B5 等）或自定义比例（例 `297/210`、`1.414`）居中填充背景。
  - 纸张比例下自带 DPI 输入，绝对像素自动按 `毫米 × DPI / 25.4` 计算。
  - 填充色支持 **固定颜色**（自选）或 **自适应黑白**（按每张图片边缘亮度自动选择黑或白）。
- **PDF → 图片**：从 PDF 提取嵌入的原始图片（无损），或把每一页按指定 DPI 渲染为 PNG。
- **PDF 编辑**：合并 / 拆分 / 删除 / 重排 / 交换页面，一次性处理一个或多个 PDF。
  - 缩略图网格；单击 / `Ctrl+点击` / `Shift+点击` 支持单选、多选、范围选。
  - 支持按住鼠标拖拽重排；拖拽时显示蓝色插入线。
  - 大文件友好：可用页码表达式批量选择，如 `1-5, 7, 10-12` / `all` / `odd` / `even`。
  - 四种导出模式：合并为一个 PDF、按切分点拆分、每 N 页拆分、按来源文件拆分。
  - 导出使用 PyMuPDF 的 `insert_pdf`，**不会重新光栅化**，原始质量完整保留。

## 依赖管理：使用 uv（推荐）

[uv](https://docs.astral.sh/uv/) 是一个快速、零配置的 Python 包管理器，替代 conda / pip / venv。

### 1. 安装 uv

```shell
# Windows (PowerShell)
irm https://astral.sh/uv/install.ps1 | iex

# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
# 或：brew install uv / pipx install uv
```

### 2. 运行程序

```shell
uv run python TPDF.py
```

第一次运行时 uv 会自动：
- 根据 `pyproject.toml` 里的 `requires-python = ">=3.10"` 下载合适的 Python 版本
- 在项目目录下创建 `.venv/` 并安装 `pillow`、`pymupdf`
- 用这个虚拟环境启动程序

### 3. 打包为可执行文件

```shell
uv run --extra build python build.py
```

或清理后重建：

```shell
uv run --extra build python build.py --clean
```

产物：

| 平台 | 产物 | 说明 |
| --- | --- | --- |
| Windows | `dist/TPDF.exe` | onefile 单文件可执行（启动无黑色控制台） |
| macOS | `dist/TPDF.app` | 标准 `.app` 包，可拖进"应用程序"文件夹 |
| Linux | `dist/TPDF` | onefile 单文件可执行 |

> `TPDF.spec` 内部按平台自动分支：Windows/Linux 走 onefile，macOS 走 onedir + BUNDLE（`.app` 本质是目录，不能与 onefile 共存）。

打包脚本已在 `build.py` 中做了跨平台处理，脚本本身只是对 `uv sync` + `uv run pyinstaller TPDF.spec` 的薄封装；如果您想手工控制，也可以直接这两行：

```shell
uv sync --extra build
uv run pyinstaller --noconfirm TPDF.spec
```

### 打包产物签名（macOS 可选）

如果需要给 `.app` 签名以便在其他 Mac 上直接运行：

```shell
codesign --force --deep --sign - dist/TPDF.app
```

后续如果需要公证（notarize）发布到非开发模式的 Mac，请配合 Apple Developer 证书。

## 不用 uv，也行

`TPDF.py` 本身仅依赖 `pillow` 和 `pymupdf`，任何 Python ≥ 3.10 的环境都能跑：

```shell
pip install pillow pymupdf pyinstaller
python TPDF.py
pyinstaller --noconfirm TPDF.spec
```

## 目录说明

```
TPDF.py              # 主程序（单文件）
TPDF.spec            # PyInstaller 打包脚本（按平台分支）
pyproject.toml       # uv / pip 依赖声明
build.py             # 跨平台打包脚本
readme.md            # 本文件
icon/                # 应用图标
├── generate_icon.py # 图标生成器（可重跑）
├── TPDF.ico         # Windows 多尺寸图标（用于 exe 和窗口）
├── TPDF.icns        # macOS 图标（用于 .app bundle）
├── TPDF.png         # 256 px 通用 PNG
└── TPDF_{16,32,48,64,128,256,512}.png   # 供 Tk iconphoto 使用的多尺寸 PNG
legacy/              # 历史版本：旧的 CLI 脚本与上一版 GUI
```

图标样式想改？直接编辑 `icon/generate_icon.py` 的 `draw_icon()`，再 `uv run python icon/generate_icon.py` 重跑即可覆盖所有尺寸。
