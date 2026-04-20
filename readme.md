# TPDF

一个图形界面的 **图片 ↔ PDF** 工具（中文）。

三个选项卡：

- **图片 → PDF**：把文件夹里的图片合成 PDF。
  - 可单向或双向统一高度 / 宽度。
  - 可按纸张比例（A3 / A4 / A5 / B4 / B5 / 1:1 / 16:9 / 9:16 等，或自定义 `高/宽`）居中填充背景。
  - 填充色支持 **固定颜色**（自选）或 **自适应黑白**（按每张图片边缘亮度自动选择黑或白）。
- **PDF → 图片**：从 PDF 提取嵌入的原始图片（无损），或把每一页按指定 DPI 渲染为 PNG。
- **PDF 编辑**：合并 / 拆分 / 删除 / 重排 / 交换页面，一次性处理一个或多个 PDF。
  - 缩略图网格；单击 / `Ctrl+点击` / `Shift+点击` 支持单选、多选、范围选。
  - 支持按住鼠标拖拽重排；拖拽时显示蓝色插入线。
  - 大文件友好：可用页码表达式批量选择，如 `1-5, 7, 10-12` / `all` / `odd` / `even`。
  - 四种导出模式：合并为一个 PDF、按切分点拆分、每 N 页拆分、按来源文件拆分。
  - 导出使用 PyMuPDF 的 `insert_pdf`，**不会重新光栅化**，原始质量完整保留。

## 安装

```shell
conda create --name tpdf python=3.12
conda activate tpdf
pip install pillow pymupdf pyinstaller
```

- `pillow`：图像处理（必需）
- `pymupdf`：PDF 读取（仅「PDF → 图片」使用；未安装时程序仍可用，只是该页会提示）
- `pyinstaller`：打包

## 运行

```shell
python TPDF.py
```

## 打包

```shell
pyinstaller -F -w TPDF.spec
```

可执行文件会生成在 `dist/` 目录下。

## 目录说明

```
TPDF.py         # 主程序
TPDF.spec       # PyInstaller 打包脚本
readme.md       # 本文件
legacy/         # 历史版本：旧的单功能 CLI 脚本与上一版 GUI，保留以备参考
```
