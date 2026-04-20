"""TPDF — 图片 ↔ PDF 工具。

三个选项卡：
- 图片 → PDF：把文件夹里的图片合成 PDF，可统一高 / 宽、按纸张比例（A4 / B5 / …）
               居中填充背景，填充色支持固定色或按图像边缘自适应黑白。
- PDF → 图片：从 PDF 中提取嵌入图片，或按指定 DPI 逐页渲染为 PNG。
- PDF 编辑 ：合并多个 PDF、拆分、删除、重排、交换页面。缩略图可拖拽，
               也可用页码表达式（如 1-5,7,10-12）批量选择，适合大文件。
"""

from __future__ import annotations

import os
import re
import sys
import subprocess
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, ttk
from typing import Callable, Optional

from PIL import Image, ImageDraw, ImageStat, ImageTk

try:
    import fitz  # PyMuPDF；PDF → 图片 与 PDF 编辑 功能需要
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False


# =============================================================================
# 常量
# =============================================================================

SCALE = 1.2

WINDOW_SIZE = f"{int(780 * SCALE)}x{int(640 * SCALE)}"
MIN_WINDOW_SIZE = (int(680 * SCALE), int(540 * SCALE))

FONT_TITLE = ("微软雅黑", int(18 * SCALE), "bold")
FONT_HEAD = ("微软雅黑", int(11 * SCALE), "bold")
FONT_BODY = ("微软雅黑", int(10 * SCALE))
FONT_SMALL = ("微软雅黑", int(9 * SCALE))

PAD_XS = int(3 * SCALE)
PAD_S = int(6 * SCALE)
PAD_M = int(10 * SCALE)
PAD_L = int(16 * SCALE)

COLOR_BG = "#f4f5f7"
COLOR_MUTED = "#6b7280"
COLOR_ACCENT = "#2563eb"
COLOR_ACCENT_HOVER = "#1d4ed8"
COLOR_DANGER = "#b00020"
COLOR_BORDER = "#d0d4da"

VALID_IMG_SUFFIX = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tiff", ".webp"}

Image.MAX_IMAGE_PIXELS = 933_120_000

# 纸张尺寸（高_mm, 宽_mm）。实际像素由用户选的 DPI 计算得到。
PAPER_SIZES_MM: dict[str, tuple[float, float]] = {
    "A3": (420, 297), "A4": (297, 210), "A5": (210, 148),
    "A6": (148, 105), "A7": (105, 74),
    "B4": (353, 250), "B5": (250, 176), "B6": (176, 125),
}

DEFAULT_DPI = 150


# =============================================================================
# 工具函数
# =============================================================================

def get_desktop_path() -> str:
    """获取当前用户的桌面路径。"""
    if sys.platform == "win32":
        CREATE_NO_WINDOW = 0x08000000
        cmd = (
            r'reg query "HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion'
            r'\Explorer\User Shell Folders" /v "Desktop"'
        )
        try:
            result = subprocess.run(
                cmd, stdout=subprocess.PIPE, text=True, creationflags=CREATE_NO_WINDOW
            )
            return result.stdout.splitlines()[2].split()[2]
        except Exception:
            return os.path.expanduser("~/Desktop")
    return os.path.expanduser("~/Desktop")


def normalize_path(p: str) -> str:
    return p.replace("/", "\\") if sys.platform == "win32" else p


def pick_folder_into(entry: ttk.Entry, initial: Optional[str] = None) -> None:
    folder = filedialog.askdirectory(initialdir=initial or os.path.expanduser(get_desktop_path()))
    if folder:
        entry.delete(0, tk.END)
        entry.insert(0, normalize_path(folder))


def pick_pdf_into(entry: ttk.Entry, initial: Optional[str] = None) -> None:
    f = filedialog.askopenfilename(
        initialdir=initial or os.path.expanduser(get_desktop_path()),
        filetypes=[("PDF 文件", "*.pdf"), ("所有文件", "*.*")],
    )
    if f:
        entry.delete(0, tk.END)
        entry.insert(0, normalize_path(f))


def ensure_folder(folder: str) -> None:
    """若文件夹不存在，询问用户是否创建。"""
    if not folder:
        messagebox.showerror("错误", "路径为空")
        return
    if os.path.exists(folder):
        messagebox.showinfo("信息", "文件夹已存在，无需创建")
        return
    if messagebox.askyesno("确认", "文件夹不存在，是否创建？"):
        try:
            os.makedirs(folder)
            messagebox.showinfo("信息", "创建成功")
        except OSError as e:
            messagebox.showerror("错误", f"创建失败\n({e})")


def is_digit_or_empty(s: str) -> bool:
    return s.isdigit() or s == ""


def run_in_background(target: Callable[[], None]) -> None:
    threading.Thread(target=target, daemon=True).start()


def parse_page_ranges(expr: str, total: int) -> Optional[set[int]]:
    """把 `1-5, 7, 10-12` 样式的表达式解析为 **0-based** 页面索引集合。

    支持：
    - 空字符串 → 空集
    - 关键字 `all` / `odd` / `even`（忽略大小写，odd/even 基于 1-based 页码奇偶）
    - 英文/中文逗号、分号、空白分隔的多个片段
    - `a-b` 或 `a~b` 表示闭区间（不区分大小顺序）
    - 单个数字

    超出 `[1, total]` 的值被静默丢弃；无法解析时返回 `None`。
    """
    expr = expr.strip()
    if not expr:
        return set()
    low = expr.lower()
    if low == "all":
        return set(range(total))
    if low == "odd":
        return {i for i in range(total) if (i + 1) % 2 == 1}
    if low == "even":
        return {i for i in range(total) if (i + 1) % 2 == 0}

    result: set[int] = set()
    try:
        for part in re.split(r"[,，;；\s]+", expr):
            if not part:
                continue
            if re.search(r"[-~]", part):
                a, b = re.split(r"[-~]", part, maxsplit=1)
                lo, hi = sorted((int(a), int(b)))
                for i in range(lo, hi + 1):
                    if 1 <= i <= total:
                        result.add(i - 1)
            else:
                i = int(part)
                if 1 <= i <= total:
                    result.add(i - 1)
    except (ValueError, TypeError):
        return None
    return result


# =============================================================================
# 图像处理
# =============================================================================

def ensure_rgb(im: Image.Image) -> Image.Image:
    """确保图片模式适合用于合成/保存 PDF。"""
    return im if im.mode in ("RGB", "RGBA", "L") else im.convert("RGB")


def detect_edge_bw(im: Image.Image, band_ratio: float = 0.05) -> tuple[int, int, int]:
    """基于图像四条边缘的平均亮度，返回纯黑或纯白。

    填充区域是图像的外侧，所以取图像"最靠边的一圈像素"作为参考最合理：
    边缘若整体偏暗则填黑，否则填白。
    """
    gray = im.convert("L")
    w, h = gray.size
    band = max(1, int(min(w, h) * band_ratio))
    regions = [
        gray.crop((0, 0, w, band)),          # top
        gray.crop((0, h - band, w, h)),      # bottom
        gray.crop((0, 0, band, h)),          # left
        gray.crop((w - band, 0, w, h)),      # right
    ]
    avg = sum(ImageStat.Stat(r).mean[0] for r in regions) / len(regions)
    return (0, 0, 0) if avg < 128 else (255, 255, 255)


def resolve_fill_color(
    im: Image.Image,
    mode: str,
    fixed_color: tuple[int, int, int],
) -> tuple[int, int, int]:
    return detect_edge_bw(im) if mode == "auto" else fixed_color


def process_image(
    im: Image.Image,
    *,
    unify_h: bool,
    h_val: int,
    unify_w: bool,
    w_val: int,
    pad_ratio: Optional[float],
    fill_mode: str,
    fixed_color: tuple[int, int, int],
) -> Image.Image:
    """对单张图片依次应用：尺寸统一 → 按比例填充。"""
    im = ensure_rgb(im)
    w, h = im.size
    fill = resolve_fill_color(im, fill_mode, fixed_color)

    # 情况 A：同时设定高与宽 —— 固定画布，图像缩放后居中
    if unify_h and unify_w:
        cw, ch = w_val, h_val
        if w / h < cw / ch:
            nh, nw = ch, int(w * ch / h)
        else:
            nw, nh = cw, int(h * cw / w)
        scaled = im.resize((nw, nh))
        canvas = Image.new("RGB", (cw, ch), fill)
        canvas.paste(scaled, ((cw - nw) // 2, (ch - nh) // 2))
        return canvas

    # 情况 B：单向统一 —— 等比缩放
    if unify_h:
        im = im.resize((int(w * h_val / h), h_val))
    elif unify_w:
        im = im.resize((w_val, int(h * w_val / w)))

    # 情况 C：按纸张比例补边
    if pad_ratio is not None:
        w, h = im.size
        if h / w > pad_ratio:
            nh, nw = h, int(h / pad_ratio)
        else:
            nw, nh = w, int(w * pad_ratio)
        if (nw, nh) != (w, h):
            canvas = Image.new("RGB", (nw, nh), fill)
            canvas.paste(im, ((nw - w) // 2, (nh - h) // 2))
            im = canvas

    return im


# =============================================================================
# 自定义勾选 / 单选指示器图像
# =============================================================================

def _draw_check(
    size: int, *, bg: str, fg: Optional[str], border: str,
    canvas_bg: str = COLOR_BG,
) -> Image.Image:
    """圆角方形勾选框。fg=None 表示未选中（不画勾）。

    整张图以 `canvas_bg` 填充后在中间绘制指示器方块，确保无论 Tk 是否
    合成 RGBA，指示器在 LabelFrame / Frame 背景上都能清晰显示。
    """
    scale = 3
    s = size * scale
    img = Image.new("RGB", (s, s), canvas_bg)
    draw = ImageDraw.Draw(img)
    r = int(3 * scale)
    bw = max(1, int(scale * 1.0))
    pad = bw
    draw.rounded_rectangle(
        [pad, pad, s - 1 - pad, s - 1 - pad],
        radius=r, fill=bg, outline=border, width=bw,
    )
    if fg is not None:
        p1 = (s * 0.24, s * 0.52)
        p2 = (s * 0.44, s * 0.72)
        p3 = (s * 0.78, s * 0.30)
        draw.line([p1, p2, p3], fill=fg, width=int(scale * 1.8))
    return img.resize((size, size), Image.LANCZOS)


def _draw_radio(
    size: int, *, bg: str, fg: Optional[str], border: str,
    canvas_bg: str = COLOR_BG,
) -> Image.Image:
    """圆形单选按钮。fg=None 表示未选中（不画中心点）。"""
    scale = 3
    s = size * scale
    img = Image.new("RGB", (s, s), canvas_bg)
    draw = ImageDraw.Draw(img)
    bw = max(1, int(scale * 1.0))
    pad = bw
    draw.ellipse(
        [pad, pad, s - 1 - pad, s - 1 - pad],
        fill=bg, outline=border, width=bw,
    )
    if fg is not None:
        inset = int(s * 0.30)
        draw.ellipse([inset, inset, s - 1 - inset, s - 1 - inset], fill=fg)
    return img.resize((size, size), Image.LANCZOS)


def make_indicator_images() -> dict[str, Image.Image]:
    """返回 Checkbutton / Radiobutton 各种状态下的 PIL 图像。

    颜色方案（确保 disabled 状态视觉上一眼就能识别出"已禁用"）：
    - 选中·可用：蓝底白勾 / 蓝心圆
    - 未选·可用：白底浅灰描边
    - 选中·禁用：浅灰底 + 中灰勾 / 中灰心
    - 未选·禁用：非常浅的灰底 + 浅灰描边
    """
    size = int(16 * SCALE)
    return {
        "check_on":      _draw_check(size, bg=COLOR_ACCENT, fg="white",    border=COLOR_ACCENT),
        "check_off":     _draw_check(size, bg="white",       fg=None,       border="#9ca3af"),
        "check_dis_on":  _draw_check(size, bg="#d1d5db",    fg="#6b7280", border="#d1d5db"),
        "check_dis_off": _draw_check(size, bg="#e5e7eb",    fg=None,       border="#cbd5e1"),
        "radio_on":      _draw_radio(size, bg="white",       fg=COLOR_ACCENT, border=COLOR_ACCENT),
        "radio_off":     _draw_radio(size, bg="white",       fg=None,       border="#9ca3af"),
        "radio_dis_on":  _draw_radio(size, bg="#e5e7eb",    fg="#6b7280", border="#cbd5e1"),
        "radio_dis_off": _draw_radio(size, bg="#e5e7eb",    fg=None,       border="#cbd5e1"),
    }


# =============================================================================
# 进度对话框
# =============================================================================

class ProgressDialog:
    """带进度条、状态文字与取消按钮的模态顶层窗口。"""

    def __init__(self, parent: tk.Misc, title: str, maximum: int = 100) -> None:
        self.cancelled = False
        self.top = tk.Toplevel(parent)
        self.top.title(title)
        self.top.geometry("500x170")
        self.top.transient(parent)
        self.top.resizable(False, False)
        self.top.grab_set()
        self.top.protocol("WM_DELETE_WINDOW", self.request_cancel)

        body = ttk.Frame(self.top, padding=PAD_L)
        body.pack(fill="both", expand=True)

        self._label = ttk.Label(body, text="准备中…", font=FONT_BODY)
        self._label.pack(anchor="w", pady=(0, PAD_S))

        self._var = tk.IntVar(value=0)
        self._bar = ttk.Progressbar(body, variable=self._var, maximum=max(1, maximum))
        self._bar.pack(fill="x", pady=PAD_S)

        self._btn = ttk.Button(body, text="取消", command=self.request_cancel)
        self._btn.pack(pady=(PAD_M, 0))

    def set_maximum(self, m: int) -> None:
        self._bar.configure(maximum=max(1, m))

    def set_progress(self, val: int, text: Optional[str] = None) -> None:
        self._var.set(val)
        if text is not None:
            self._label.configure(text=text)
        try:
            self.top.update_idletasks()
        except tk.TclError:
            pass

    def request_cancel(self) -> None:
        self.cancelled = True
        self._btn.configure(text="取消中…", state="disabled")

    def finish(self, text: str) -> None:
        self._bar.configure(value=self._bar["maximum"])
        self._label.configure(text=text)
        self._btn.configure(text="完成", state="normal", command=self.close)

    def close(self) -> None:
        try:
            self.top.grab_release()
            self.top.destroy()
        except tk.TclError:
            pass


# =============================================================================
# 标签页基类
# =============================================================================

class TabBase(ttk.Frame):
    """所有标签页共用的基础 Frame，仅用于统一外边距。"""

    def __init__(self, master: ttk.Notebook) -> None:
        super().__init__(master, padding=(PAD_L, PAD_M, PAD_L, PAD_M))


# =============================================================================
# 图片 → PDF 标签页
# =============================================================================

class Img2PdfTab(TabBase):
    """图片 → PDF 标签页。

    尺寸/比例交互状态机（详见 `_refresh_sizes_ui`）：

    ── 基本约定 ────────────────────────────────
    - 四个独立勾选框：统一高度 / 统一宽度 / 按纸张比例 / 自定义比例
    - 四个勾选框 **任何时候都可以点**；冲突时仅通过"灰化对应的输入框 /
      下拉 / DPI"来表达，勾选框本身不被禁用
    - "按纸张比例"与"自定义比例"互斥（同时只生效一个，也可都不选）
    - "按纸张比例"与任意"统一"互斥：最后点的那个胜出，另一方自动关闭
    - 自定义比例下，"统一高度"与"统一宽度"互斥（另一维由比例派生）

    ── 值派生规则 ───────────────────────────────
    - 勾"按纸张比例"  → h/w = 纸张_mm × DPI / 25.4（两维都是只读派生值）
    - 勾"自定义比例" → 必须有一个"统一"作为基准（没有时默认勾"统一高度"）
        · 仅统一高度 → 宽只读，由高度按比例派生
        · 仅统一宽度 → 高只读，由宽度按比例派生
    - 未勾任何比例 + 仅统一高度      → 高可编辑；宽禁用（保原比例缩放）
    - 未勾任何比例 + 统一高度+统一宽度 → 高/宽都可编辑（固定画布）

    ── 填充色 ───────────────────────────────────
    只有真的会发生补边（任一比例启用 / 两个统一都勾）时才启用；其余情况灰化。
    """

    def __init__(self, master: ttk.Notebook, desktop: str) -> None:
        super().__init__(master)
        self.desktop = desktop

        # ── 路径 ──
        self.folder_var = tk.StringVar(
            value=normalize_path(str(Path(desktop) / "TPDF输入图片"))
        )
        self.output_var = tk.StringVar(value=normalize_path(desktop))

        # ── 尺寸状态 ──
        self.unify_h_var = tk.BooleanVar(value=True)
        self.unify_w_var = tk.BooleanVar(value=False)
        self.h_val_var = tk.StringVar(value="1754")
        self.w_val_var = tk.StringVar(value="1240")

        self.paper_on_var = tk.BooleanVar(value=False)
        self.paper_preset_var = tk.StringVar(value="A4")
        self.dpi_var = tk.StringVar(value=str(DEFAULT_DPI))

        self.custom_on_var = tk.BooleanVar(value=False)
        self.custom_ratio_var = tk.StringVar(value="")

        # ── 填充 ──
        self.fill_mode_var = tk.StringVar(value="fixed")  # "fixed" | "auto"
        self.fixed_color: tuple[int, int, int] = (255, 255, 255)
        self.fixed_hex: str = "#ffffff"

        # 避免 trace 递归
        self._updating = False

        self._build()
        self._install_traces()
        self._refresh_sizes_ui()
        self._refresh_fill_ui()

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------

    def _build(self) -> None:
        vcmd = (self.register(is_digit_or_empty), "%P")

        self._build_paths(vcmd)
        self._build_sizes(vcmd)
        self._build_fill()

        ttk.Button(
            self, text="  转为 PDF  ", style="Accent.TButton", command=self._on_start,
        ).pack(pady=(PAD_L, 0), ipadx=PAD_M)

    def _build_paths(self, vcmd) -> None:
        group = ttk.LabelFrame(self, text="路径", padding=PAD_M)
        group.pack(fill="x", pady=(0, PAD_S))
        group.columnconfigure(1, weight=1)

        ttk.Label(group, text="图片文件夹").grid(row=0, column=0, sticky="w", padx=(0, PAD_M))
        in_entry = ttk.Entry(group, textvariable=self.folder_var)
        in_entry.grid(row=0, column=1, sticky="ew")
        ttk.Button(
            group, text="选择", command=lambda: pick_folder_into(in_entry, self.desktop),
        ).grid(row=0, column=2, padx=(PAD_S, PAD_XS))
        ttk.Button(
            group, text="新建", command=lambda: ensure_folder(self.folder_var.get()),
        ).grid(row=0, column=3, padx=PAD_XS)

        ttk.Label(group, text="输出 PDF 到").grid(
            row=1, column=0, sticky="w", padx=(0, PAD_M), pady=(PAD_S, 0),
        )
        out_entry = ttk.Entry(group, textvariable=self.output_var)
        out_entry.grid(row=1, column=1, sticky="ew", pady=(PAD_S, 0))
        ttk.Button(
            group, text="选择", command=lambda: pick_folder_into(out_entry, self.desktop),
        ).grid(row=1, column=2, padx=(PAD_S, PAD_XS), pady=(PAD_S, 0))
        ttk.Label(
            group, text="（文件名自动生成）", font=FONT_SMALL, foreground=COLOR_MUTED,
        ).grid(row=1, column=3, padx=PAD_XS, pady=(PAD_S, 0), sticky="w")

    def _build_sizes(self, vcmd) -> None:
        group = ttk.LabelFrame(self, text="尺寸", padding=PAD_M)
        group.pack(fill="x", pady=PAD_S)

        # 行 1：统一高度 / 统一宽度
        row1 = ttk.Frame(group)
        row1.pack(fill="x")
        self._cb_h = ttk.Checkbutton(
            row1, text="统一高度", variable=self.unify_h_var, command=self._on_unify_h_change,
        )
        self._cb_h.pack(side="left", padx=(0, PAD_XS))
        self._e_h = ttk.Entry(
            row1, width=8, validate="key", validatecommand=vcmd, textvariable=self.h_val_var,
        )
        self._e_h.pack(side="left", padx=(0, PAD_L))
        self._cb_w = ttk.Checkbutton(
            row1, text="统一宽度", variable=self.unify_w_var, command=self._on_unify_w_change,
        )
        self._cb_w.pack(side="left", padx=(0, PAD_XS))
        self._e_w = ttk.Entry(
            row1, width=8, validate="key", validatecommand=vcmd, textvariable=self.w_val_var,
        )
        self._e_w.pack(side="left")
        self._lbl_px = ttk.Label(
            row1, text="像素", font=FONT_SMALL, foreground=COLOR_MUTED,
        )
        self._lbl_px.pack(side="left", padx=(PAD_S, 0))

        # 行 2：按纸张比例 + DPI
        row2 = ttk.Frame(group)
        row2.pack(fill="x", pady=(PAD_S, 0))
        self._cb_paper = ttk.Checkbutton(
            row2, text="按纸张比例", variable=self.paper_on_var, command=self._on_paper_toggle,
        )
        self._cb_paper.pack(side="left", padx=(0, PAD_XS))
        self._cb_paper_combo = ttk.Combobox(
            row2, values=list(PAPER_SIZES_MM.keys()), textvariable=self.paper_preset_var,
            state="readonly", width=6,
        )
        self._cb_paper_combo.pack(side="left", padx=(0, PAD_M))
        self._cb_paper_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_sizes_ui())
        self._lbl_dpi = ttk.Label(row2, text="DPI")
        self._lbl_dpi.pack(side="left")
        self._e_dpi = ttk.Entry(
            row2, width=5, validate="key", validatecommand=vcmd, textvariable=self.dpi_var,
        )
        self._e_dpi.pack(side="left", padx=PAD_XS)
        ttk.Label(
            row2, text="（300=印刷 / 150=常规 / 100=预览）",
            font=FONT_SMALL, foreground=COLOR_MUTED,
        ).pack(side="left", padx=(PAD_XS, 0))

        # 行 3：自定义比例
        row3 = ttk.Frame(group)
        row3.pack(fill="x", pady=(PAD_S, 0))
        self._cb_custom = ttk.Checkbutton(
            row3, text="自定义比例", variable=self.custom_on_var, command=self._on_custom_toggle,
        )
        self._cb_custom.pack(side="left", padx=(0, PAD_XS))
        self._e_custom = ttk.Entry(row3, width=10, textvariable=self.custom_ratio_var)
        self._e_custom.pack(side="left", padx=(0, PAD_S))
        ttk.Label(
            row3, text="高/宽，如 297/210、1.414",
            font=FONT_SMALL, foreground=COLOR_MUTED,
        ).pack(side="left")

    def _build_fill(self) -> None:
        group = ttk.LabelFrame(
            self, text="填充背景色（用于尺寸/比例产生的空白区域）", padding=PAD_M,
        )
        group.pack(fill="x", pady=PAD_S)
        self._fill_group = group

        row1 = ttk.Frame(group)
        row1.pack(fill="x")
        self._rb_fixed = ttk.Radiobutton(
            row1, text="固定颜色", variable=self.fill_mode_var, value="fixed",
            command=self._refresh_fill_ui,
        )
        self._rb_fixed.pack(side="left", padx=(0, PAD_S))
        self._swatch = tk.Label(
            row1, text="    ", bg=self.fixed_hex,
            relief="solid", borderwidth=1, highlightthickness=0,
        )
        self._swatch.pack(side="left", padx=PAD_S)
        self._pick_btn = ttk.Button(row1, text="选择颜色…", command=self._pick_color)
        self._pick_btn.pack(side="left", padx=PAD_S)

        row2 = ttk.Frame(group)
        row2.pack(fill="x", pady=(PAD_S, 0))
        self._rb_auto = ttk.Radiobutton(
            row2, text="自适应黑白", variable=self.fill_mode_var, value="auto",
            command=self._refresh_fill_ui,
        )
        self._rb_auto.pack(side="left")
        ttk.Label(
            row2,
            text="按每张图片的边缘亮度自动选择：偏暗填黑，偏亮填白",
            font=FONT_SMALL, foreground=COLOR_MUTED,
        ).pack(side="left", padx=PAD_S)

    def _install_traces(self) -> None:
        """监听所有会影响派生值/UI 状态的输入变量。"""
        self.h_val_var.trace_add("write", lambda *_: self._on_value_change("h"))
        self.w_val_var.trace_add("write", lambda *_: self._on_value_change("w"))
        self.dpi_var.trace_add("write", lambda *_: self._on_value_change("dpi"))
        self.custom_ratio_var.trace_add("write", lambda *_: self._on_value_change("ratio"))

    # ------------------------------------------------------------------
    # 状态联动
    # ------------------------------------------------------------------

    def _on_unify_h_change(self) -> None:
        # 用户刚刚点了"统一高度"。
        if self.unify_h_var.get():
            # 打开 → 与"按纸张比例"、自定义下的"统一宽度"互斥
            if self.paper_on_var.get():
                self.paper_on_var.set(False)
            if self.custom_on_var.get() and self.unify_w_var.get():
                self.unify_w_var.set(False)
        else:
            # 关闭 → 在"自定义比例"下，自动切换到"统一宽度"（保持有基准维度）
            if self.custom_on_var.get() and not self.unify_w_var.get():
                self.unify_w_var.set(True)
        self._refresh_sizes_ui()

    def _on_unify_w_change(self) -> None:
        # 同上，对称处理"统一宽度"。最后点的那个胜出；关闭时在 custom 下切换到另一边。
        if self.unify_w_var.get():
            if self.paper_on_var.get():
                self.paper_on_var.set(False)
            if self.custom_on_var.get() and self.unify_h_var.get():
                self.unify_h_var.set(False)
        else:
            if self.custom_on_var.get() and not self.unify_h_var.get():
                self.unify_h_var.set(True)
        self._refresh_sizes_ui()

    def _on_paper_toggle(self) -> None:
        if self.paper_on_var.get():
            # 纸张比例接管 → 取消自定义、取消两个统一
            self.custom_on_var.set(False)
            self.unify_h_var.set(False)
            self.unify_w_var.set(False)
        self._refresh_sizes_ui()

    def _on_custom_toggle(self) -> None:
        if self.custom_on_var.get():
            # 与"按纸张比例"互斥
            self.paper_on_var.set(False)
            # 自定义比例必须有一个基准维度：
            # - 若两者都勾 → 保留"统一高度"、取消"统一宽度"
            # - 若两者都没勾 → 默认勾上"统一高度"
            # - 若只有一个 → 保持不变
            if self.unify_h_var.get() and self.unify_w_var.get():
                self.unify_w_var.set(False)
            elif not self.unify_h_var.get() and not self.unify_w_var.get():
                self.unify_h_var.set(True)
        self._refresh_sizes_ui()

    def _on_value_change(self, source: str) -> None:
        if self._updating:
            return
        self._updating = True
        try:
            self._recompute_size_values(source)
        finally:
            self._updating = False

    # ------------------------------------------------------------------
    # 派生值计算
    # ------------------------------------------------------------------

    def _parse_ratio_or_none(self) -> Optional[float]:
        """返回当前启用的比例 (h/w)；未启用返回 None；解析失败（custom）返回 None。"""
        if self.paper_on_var.get():
            size = PAPER_SIZES_MM.get(self.paper_preset_var.get())
            if size:
                h_mm, w_mm = size
                return h_mm / w_mm
        if self.custom_on_var.get():
            txt = self.custom_ratio_var.get().strip()
            if not txt:
                return None
            try:
                val = float(eval(txt, {"__builtins__": {}}))
                if val > 0:
                    return val
            except Exception:
                return None
        return None

    def _parse_int(self, s: str) -> Optional[int]:
        try:
            v = int(s) if s else 0
            return v if v > 0 else None
        except ValueError:
            return None

    def _recompute_size_values(self, source: str = "") -> None:
        """根据当前模式把派生的宽/高值写回 StringVar。"""
        paper_on = self.paper_on_var.get()
        custom_on = self.custom_on_var.get()
        unify_h = self.unify_h_var.get()
        unify_w = self.unify_w_var.get()

        if paper_on:
            size = PAPER_SIZES_MM.get(self.paper_preset_var.get())
            if size:
                h_mm, w_mm = size
                dpi = self._parse_int(self.dpi_var.get()) or DEFAULT_DPI
                self.h_val_var.set(str(int(round(h_mm * dpi / 25.4))))
                self.w_val_var.set(str(int(round(w_mm * dpi / 25.4))))
            return

        if custom_on:
            ratio = self._parse_ratio_or_none()
            if ratio is None:
                return
            if unify_h and not unify_w:
                h = self._parse_int(self.h_val_var.get())
                if h:
                    self.w_val_var.set(str(int(round(h / ratio))))
            elif unify_w and not unify_h:
                w = self._parse_int(self.w_val_var.get())
                if w:
                    self.h_val_var.set(str(int(round(w * ratio))))
            return
        # 否则不做派生

    # ------------------------------------------------------------------
    # UI 状态刷新（统一出入口）
    # ------------------------------------------------------------------

    def _refresh_sizes_ui(self) -> None:
        paper_on = self.paper_on_var.get()
        custom_on = self.custom_on_var.get()
        unify_h = self.unify_h_var.get()
        unify_w = self.unify_w_var.get()

        # 不变量：启用"自定义比例"时必须至少有一个"统一"作为基准维度。
        # 兜底所有进入该状态的路径（含用户手动取消最后一个 unify）。
        # 默认偏向"统一高度"。
        if custom_on and not unify_h and not unify_w:
            self.unify_h_var.set(True)
            unify_h = True

        # 四个勾选框始终保持"可点"状态；冲突只通过灰化"输入框 / 下拉 / DPI"
        # 来表达。勾选框被禁用会违反"任何时候都可以点"的约定。
        self._cb_h.configure(state="normal")
        self._cb_w.configure(state="normal")
        self._cb_paper.configure(state="normal")
        self._cb_custom.configure(state="normal")

        # 高 / 宽 entry 三态
        # - editable：由用户输入
        # - readonly：显示派生值（灰色背景、不能编辑）
        # - disabled：灰化、不显示实际意义
        def _entry_state(editable: bool, readonly: bool, entry: ttk.Entry) -> None:
            if editable:
                entry.configure(state="normal")
            elif readonly:
                entry.configure(state="readonly")
            else:
                entry.configure(state="disabled")

        if paper_on:
            _entry_state(False, True, self._e_h)
            _entry_state(False, True, self._e_w)
        elif custom_on:
            if unify_h and not unify_w:
                _entry_state(True, False, self._e_h)
                _entry_state(False, True, self._e_w)
            elif unify_w and not unify_h:
                _entry_state(False, True, self._e_h)
                _entry_state(True, False, self._e_w)
            else:
                _entry_state(False, False, self._e_h)
                _entry_state(False, False, self._e_w)
        else:
            _entry_state(unify_h, False, self._e_h)
            _entry_state(unify_w, False, self._e_w)

        # 纸张比例组件
        self._cb_paper_combo.configure(state=("readonly" if paper_on else "disabled"))
        self._e_dpi.configure(state=("normal" if paper_on else "disabled"))

        # 自定义比例组件
        self._e_custom.configure(state=("normal" if custom_on else "disabled"))

        # 刷新派生值
        if not self._updating:
            self._updating = True
            try:
                self._recompute_size_values()
            finally:
                self._updating = False

        # 填充色也跟着一起刷新（可能因此启用/禁用）
        self._refresh_fill_ui()

    # ------------------------------------------------------------------
    # 填充色
    # ------------------------------------------------------------------

    def _fill_is_active(self) -> bool:
        """是否真正会发生补边（决定填充色区是否可用）。"""
        if self.paper_on_var.get() or self.custom_on_var.get():
            return True
        if self.unify_h_var.get() and self.unify_w_var.get():
            return True
        return False

    def _refresh_fill_ui(self) -> None:
        active = self._fill_is_active()
        is_fixed = self.fill_mode_var.get() == "fixed"

        state = "normal" if active else "disabled"
        self._rb_fixed.configure(state=state)
        self._rb_auto.configure(state=state)

        if active and is_fixed:
            self._pick_btn.configure(state="normal")
            self._swatch.configure(bg=self.fixed_hex)
        else:
            self._pick_btn.configure(state="disabled")
            self._swatch.configure(bg="#e5e7eb")

    def _pick_color(self) -> None:
        res = colorchooser.askcolor(title="选择填充颜色", initialcolor=self.fixed_hex)
        if res and res[1]:
            self.fixed_color = tuple(int(v) for v in res[0])
            self.fixed_hex = res[1]
            self._swatch.configure(bg=self.fixed_hex)

    # ------------------------------------------------------------------
    # 运行：校验与参数收集
    # ------------------------------------------------------------------

    def _validate_and_collect(self) -> Optional[dict]:
        dirname = self.folder_var.get()
        output_dir = self.output_var.get()

        if not os.path.isdir(dirname):
            messagebox.showerror("错误", "图片输入文件夹不存在")
            return None
        if not os.path.isdir(output_dir):
            messagebox.showerror("错误", "输出文件夹不存在")
            return None

        paper_on = self.paper_on_var.get()
        custom_on = self.custom_on_var.get()
        unify_h = self.unify_h_var.get()
        unify_w = self.unify_w_var.get()

        # 先把派生值写到最新
        self._updating = True
        try:
            self._recompute_size_values()
        finally:
            self._updating = False

        h_val = self._parse_int(self.h_val_var.get()) or 0
        w_val = self._parse_int(self.w_val_var.get()) or 0

        # 把 UI 状态"翻译"成 process_image 所需的三元组 (unify_h, unify_w, pad_ratio)
        pad_ratio: Optional[float] = None
        if paper_on:
            # 等价于固定画布（两个维度都已由 DPI 计算得出）
            eff_unify_h, eff_unify_w = True, True
            if h_val <= 0 or w_val <= 0:
                messagebox.showerror("错误", "纸张尺寸解析失败，请检查 DPI 是否为正整数")
                return None
        elif custom_on:
            ratio = self._parse_ratio_or_none()
            if ratio is None:
                messagebox.showerror("错误", "自定义比例无法解析（请填写如 297/210、1.414）")
                return None
            if unify_h and not unify_w:
                # 派生后 w_val 已经正确；作为固定画布处理
                eff_unify_h, eff_unify_w = True, True
                if h_val <= 0 or w_val <= 0:
                    messagebox.showerror("错误", "统一高度需为正整数")
                    return None
            elif unify_w and not unify_h:
                eff_unify_h, eff_unify_w = True, True
                if h_val <= 0 or w_val <= 0:
                    messagebox.showerror("错误", "统一宽度需为正整数")
                    return None
            else:
                # 都不选：原始尺寸按比例补边
                eff_unify_h, eff_unify_w = False, False
                pad_ratio = ratio
        else:
            # 无比例
            eff_unify_h, eff_unify_w = unify_h, unify_w
            if unify_h and h_val <= 0:
                messagebox.showerror("错误", "统一高度需为正整数")
                return None
            if unify_w and w_val <= 0:
                messagebox.showerror("错误", "统一宽度需为正整数")
                return None

        filenames = sorted(
            f for f in os.listdir(dirname)
            if os.path.splitext(f)[1].lower() in VALID_IMG_SUFFIX
        )
        if not filenames:
            messagebox.showerror("错误", "文件夹内没有支持的图片")
            return None

        return dict(
            dirname=dirname, output_dir=output_dir, filenames=filenames,
            unify_h=eff_unify_h, h_val=h_val,
            unify_w=eff_unify_w, w_val=w_val,
            pad_ratio=pad_ratio,
            fill_mode=self.fill_mode_var.get(),
            fixed_color=self.fixed_color,
        )

    def _on_start(self) -> None:
        cfg = self._validate_and_collect()
        if not cfg:
            return

        output_path = str(
            Path(cfg["output_dir"]) / f"TPDF-{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        )
        dlg = ProgressDialog(
            self.winfo_toplevel(), "图片 → PDF", maximum=len(cfg["filenames"]) + 1
        )
        run_in_background(lambda: self._run(cfg, output_path, dlg))

    def _run(self, cfg: dict, output_path: str, dlg: ProgressDialog) -> None:
        try:
            img_list: list[Image.Image] = []
            files = cfg["filenames"]
            for i, fname in enumerate(files, 1):
                if dlg.cancelled:
                    raise KeyboardInterrupt("任务已取消")
                dlg.set_progress(i, f"处理中：{fname}  （{i}/{len(files)}）")
                im = Image.open(os.path.join(cfg["dirname"], fname))
                img_list.append(process_image(
                    im,
                    unify_h=cfg["unify_h"], h_val=cfg["h_val"],
                    unify_w=cfg["unify_w"], w_val=cfg["w_val"],
                    pad_ratio=cfg["pad_ratio"],
                    fill_mode=cfg["fill_mode"],
                    fixed_color=cfg["fixed_color"],
                ))

            dlg.set_progress(len(files), "正在写入 PDF…")
            img_list[0].save(
                output_path, "PDF", resolution=100.0,
                save_all=True, append_images=img_list[1:],
            )
            dlg.finish(f"完成！共 {len(files)} 张\n输出：{output_path}")

        except KeyboardInterrupt as e:
            dlg.close()
            messagebox.showinfo("信息", f"任务取消\n({e})")
            self._safe_remove(output_path)
        except FileNotFoundError as e:
            dlg.close()
            messagebox.showerror("错误", f"文件不存在\n({e})")
            self._safe_remove(output_path)
        except Exception as e:
            dlg.close()
            messagebox.showerror("错误", f"任务失败\n({e})")
            self._safe_remove(output_path)

    @staticmethod
    def _safe_remove(path: str) -> None:
        try:
            os.remove(path)
        except OSError:
            pass


# =============================================================================
# PDF → 图片 标签页
# =============================================================================

class Pdf2ImgTab(TabBase):
    def __init__(self, master: ttk.Notebook, desktop: str) -> None:
        super().__init__(master)
        self.desktop = desktop

        self.pdf_var = tk.StringVar(value="")
        self.out_var = tk.StringVar(
            value=normalize_path(str(Path(desktop) / "TPDF提取图片"))
        )
        self.mode_var = tk.StringVar(value="embedded")  # "embedded" | "render"
        self.dpi_var = tk.StringVar(value="200")

        self._build()

    def _build(self) -> None:
        vcmd = (self.register(is_digit_or_empty), "%P")

        # 路径
        paths = ttk.LabelFrame(self, text="路径", padding=PAD_M)
        paths.pack(fill="x", pady=(0, PAD_S))
        paths.columnconfigure(1, weight=1)

        ttk.Label(paths, text="PDF 文件").grid(row=0, column=0, sticky="w", padx=(0, PAD_M))
        pdf_entry = ttk.Entry(paths, textvariable=self.pdf_var)
        pdf_entry.grid(row=0, column=1, sticky="ew")
        ttk.Button(
            paths, text="选择", command=lambda: pick_pdf_into(pdf_entry, self.desktop)
        ).grid(row=0, column=2, padx=(PAD_S, PAD_XS))

        ttk.Label(paths, text="输出文件夹").grid(
            row=1, column=0, sticky="w", padx=(0, PAD_M), pady=(PAD_S, 0)
        )
        out_entry = ttk.Entry(paths, textvariable=self.out_var)
        out_entry.grid(row=1, column=1, sticky="ew", pady=(PAD_S, 0))
        ttk.Button(
            paths, text="选择", command=lambda: pick_folder_into(out_entry, self.desktop)
        ).grid(row=1, column=2, padx=(PAD_S, PAD_XS), pady=(PAD_S, 0))
        ttk.Button(
            paths, text="新建", command=lambda: ensure_folder(self.out_var.get())
        ).grid(row=1, column=3, padx=PAD_XS, pady=(PAD_S, 0))

        # 模式
        mode = ttk.LabelFrame(self, text="提取模式", padding=PAD_M)
        mode.pack(fill="x", pady=PAD_S)

        ttk.Radiobutton(
            mode, text="提取 PDF 中嵌入的原始图片（保持无损）",
            variable=self.mode_var, value="embedded",
        ).pack(anchor="w")

        render_row = ttk.Frame(mode)
        render_row.pack(anchor="w", pady=(PAD_S, 0))
        ttk.Radiobutton(
            render_row, text="逐页整页渲染为 PNG", variable=self.mode_var, value="render",
        ).pack(side="left")
        ttk.Label(render_row, text="    DPI").pack(side="left")
        ttk.Entry(
            render_row, width=6, validate="key", validatecommand=vcmd, textvariable=self.dpi_var,
        ).pack(side="left", padx=PAD_S)
        ttk.Label(
            render_row, text="（推荐 150–300）", font=FONT_SMALL, foreground=COLOR_MUTED,
        ).pack(side="left")

        if not HAS_FITZ:
            ttk.Label(
                self,
                text="⚠ 未检测到 PyMuPDF，使用本页前请先运行：pip install pymupdf",
                foreground=COLOR_DANGER, font=FONT_SMALL,
            ).pack(pady=PAD_S)

        ttk.Button(
            self, text="  开始提取  ", style="Accent.TButton", command=self._on_start
        ).pack(pady=(PAD_L, 0), ipadx=PAD_M)

    # ---- 运行 ----

    def _on_start(self) -> None:
        if not HAS_FITZ:
            messagebox.showerror("错误", "未安装 PyMuPDF。请运行：\npip install pymupdf")
            return

        pdf_path = self.pdf_var.get().strip()
        out_dir = self.out_var.get().strip()
        if not os.path.isfile(pdf_path):
            messagebox.showerror("错误", "PDF 文件不存在")
            return
        if not out_dir:
            messagebox.showerror("错误", "输出文件夹为空")
            return
        try:
            os.makedirs(out_dir, exist_ok=True)
        except OSError as e:
            messagebox.showerror("错误", f"无法创建输出文件夹\n({e})")
            return

        mode = self.mode_var.get()
        try:
            dpi = int(self.dpi_var.get()) if self.dpi_var.get() else 200
        except ValueError:
            dpi = 200
        dpi = max(50, min(600, dpi))

        dlg = ProgressDialog(self.winfo_toplevel(), "PDF → 图片", maximum=100)
        run_in_background(lambda: self._run(pdf_path, out_dir, mode, dpi, dlg))

    def _run(
        self, pdf_path: str, out_dir: str, mode: str, dpi: int, dlg: ProgressDialog
    ) -> None:
        pdf_document = None
        try:
            pdf_document = fitz.open(pdf_path)
            total = len(pdf_document)
            dlg.set_maximum(max(total, 1))
            dlg.set_progress(0, f"共 {total} 页，开始处理…")

            count = 0
            for page_num in range(total):
                if dlg.cancelled:
                    raise KeyboardInterrupt("任务已取消")
                page = pdf_document.load_page(page_num)

                if mode == "embedded":
                    for img_idx, img in enumerate(page.get_images(full=True), start=1):
                        base = pdf_document.extract_image(img[0])
                        filename = re.sub(
                            r'[\\/*?:"<>|]', "_",
                            f"page_{page_num + 1}_img_{img_idx}.{base['ext']}",
                        )
                        with open(os.path.join(out_dir, filename), "wb") as f:
                            f.write(base["image"])
                        count += 1
                else:
                    zoom = dpi / 72.0
                    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
                    pix.save(os.path.join(out_dir, f"page_{page_num + 1}.png"))
                    count += 1

                dlg.set_progress(page_num + 1, f"第 {page_num + 1}/{total} 页")

            dlg.finish(f"完成！共导出 {count} 张图片\n输出：{out_dir}")

        except KeyboardInterrupt as e:
            dlg.close()
            messagebox.showinfo("信息", f"任务取消\n({e})")
        except FileNotFoundError as e:
            dlg.close()
            messagebox.showerror("错误", f"文件不存在\n({e})")
        except Exception as e:
            dlg.close()
            messagebox.showerror("错误", f"任务失败\n({e})")
        finally:
            if pdf_document is not None:
                try:
                    pdf_document.close()
                except Exception:
                    pass


# =============================================================================
# PDF 编辑 标签页
# =============================================================================

class PageRef:
    """工作队列里的一页：仅保存来源文档编号与页码（轻量）。"""

    __slots__ = ("doc_id", "page_index", "source_label")

    def __init__(self, doc_id: int, page_index: int, source_label: str) -> None:
        self.doc_id = doc_id
        self.page_index = page_index
        self.source_label = source_label


class PdfEditTab(TabBase):
    """合并 / 拆分 / 删除 / 重排 / 交换 PDF 页面。

    模型：
    - `loaded_docs`：加载过的 PDF 文件（懒打开，保持打开直到清空/退出）
    - `pages`：有序的 PageRef 队列（缩略图网格所显示的内容）
    - `selected`：选中页在 `pages` 中的 index 集合
    - `split_markers`：位于"第 i 页之后"的切分点集合（i ∈ [0, len-1]）

    所有操作都是对 `pages` 队列的修改。
    """

    # 缩略图尺寸（像素）与间距
    THUMB_W = int(110 * SCALE)
    THUMB_H = int(140 * SCALE)
    CELL_W = THUMB_W + int(18 * SCALE)       # 含边框与文字
    CELL_H = THUMB_H + int(40 * SCALE)
    CELL_PAD = int(6 * SCALE)

    # 颜色
    CLR_ITEM_BG = "#ffffff"
    CLR_ITEM_BD = "#d0d4da"
    CLR_ITEM_SEL = COLOR_ACCENT
    CLR_SEG_BD = "#f59e0b"     # 切分段起始边色
    CLR_DROP = COLOR_ACCENT

    def __init__(self, master: ttk.Notebook, desktop: str) -> None:
        super().__init__(master)
        self.desktop = desktop

        # ── 数据模型 ──
        self.loaded_docs: list[dict] = []
        self.pages: list[PageRef] = []
        self.selected: set[int] = set()
        self.anchor_idx: Optional[int] = None
        self.split_markers: set[int] = set()

        # ── 视图状态 ──
        self.item_widgets: list[tk.Frame] = []
        self.thumb_cache: dict[tuple[int, int], ImageTk.PhotoImage] = {}
        self._placeholder: Optional[ImageTk.PhotoImage] = None
        self._current_cols = 1

        # ── 拖拽状态 ──
        self._press_idx: Optional[int] = None
        self._press_xy: Optional[tuple[int, int]] = None
        self._dragging = False
        self._drop_target: Optional[int] = None
        self._drop_indicator: Optional[tk.Frame] = None

        # ── 渲染线程控制 ──
        self._render_stop = threading.Event()

        # ── UI 变量 ──
        self.page_expr_var = tk.StringVar(value="")
        self.mode_var = tk.StringVar(value="merge")
        self.chunk_size_var = tk.StringVar(value="10")
        self.status_var = tk.StringVar(value="尚未加载 PDF")

        self._build()

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------

    def _build(self) -> None:
        self._build_toolbar()

        body = ttk.Frame(self, style="TFrame")
        body.pack(fill="both", expand=True, pady=(PAD_S, 0))
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        self._build_grid(body)
        self._build_side(body)

        if not HAS_FITZ:
            ttk.Label(
                self,
                text="⚠ 未检测到 PyMuPDF，本页无法工作。请先运行：pip install pymupdf",
                foreground=COLOR_DANGER, font=FONT_SMALL,
            ).pack(pady=(PAD_S, 0))

    def _build_toolbar(self) -> None:
        bar = ttk.Frame(self)
        bar.pack(fill="x")
        ttk.Button(bar, text="＋ 添加 PDF", command=self._on_add_pdf).pack(side="left")
        ttk.Button(bar, text="清空", command=self._on_clear_all).pack(side="left", padx=(PAD_S, 0))
        ttk.Label(
            bar, textvariable=self.status_var,
            font=FONT_SMALL, foreground=COLOR_MUTED,
        ).pack(side="left", padx=PAD_M)

    def _build_grid(self, parent: ttk.Frame) -> None:
        holder = ttk.Frame(parent)
        holder.grid(row=0, column=0, sticky="nsew", padx=(0, PAD_S))
        holder.rowconfigure(0, weight=1)
        holder.columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(
            holder, background="#ffffff", highlightthickness=1,
            highlightbackground=COLOR_BORDER,
        )
        self.canvas.grid(row=0, column=0, sticky="nsew")

        vbar = ttk.Scrollbar(holder, orient="vertical", command=self.canvas.yview)
        vbar.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=vbar.set)

        self.inner = tk.Frame(self.canvas, background="#ffffff")
        self._inner_window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")

        # 滚轮
        self.canvas.bind("<Enter>", lambda e: self.canvas.bind_all("<MouseWheel>", self._on_mousewheel))
        self.canvas.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self.inner.bind("<Configure>",
                        lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

        # 画布空白区点击 → 取消选择
        self.canvas.bind("<Button-1>", self._on_canvas_click)

    def _build_side(self, parent: ttk.Frame) -> None:
        side = ttk.Frame(parent)
        side.grid(row=0, column=1, sticky="ns")

        # — 选择 —
        sel = ttk.LabelFrame(side, text="选择", padding=PAD_S)
        sel.pack(fill="x")
        row = ttk.Frame(sel); row.pack(fill="x")
        ttk.Label(row, text="页码", font=FONT_SMALL).pack(side="left")
        ttk.Entry(row, width=18, textvariable=self.page_expr_var).pack(
            side="left", padx=(PAD_XS, PAD_XS), fill="x", expand=True
        )
        ttk.Button(row, text="应用", command=self._on_apply_expr).pack(side="left")
        ttk.Label(
            sel, text="如 1-5,7,10-12 / all / odd / even",
            font=FONT_SMALL, foreground=COLOR_MUTED,
        ).pack(anchor="w", pady=(PAD_XS, 0))
        row2 = ttk.Frame(sel); row2.pack(fill="x", pady=(PAD_XS, 0))
        ttk.Button(row2, text="全选", command=self._on_select_all, width=6).pack(side="left")
        ttk.Button(row2, text="反选", command=self._on_invert, width=6).pack(side="left", padx=PAD_XS)
        ttk.Button(row2, text="清除", command=self._on_clear_selection, width=6).pack(side="left")

        # — 移动 —
        mv = ttk.LabelFrame(side, text="移动所选", padding=PAD_S)
        mv.pack(fill="x", pady=(PAD_S, 0))
        row = ttk.Frame(mv); row.pack(fill="x")
        ttk.Button(row, text="← 前移", command=lambda: self._on_move(-1), width=8).pack(side="left")
        ttk.Button(row, text="后移 →", command=lambda: self._on_move(+1), width=8).pack(
            side="left", padx=(PAD_XS, 0)
        )
        row2 = ttk.Frame(mv); row2.pack(fill="x", pady=(PAD_XS, 0))
        ttk.Button(row2, text="置顶", command=lambda: self._on_move_edge(True), width=8).pack(side="left")
        ttk.Button(row2, text="置底", command=lambda: self._on_move_edge(False), width=8).pack(
            side="left", padx=(PAD_XS, 0)
        )

        # — 操作 —
        op = ttk.LabelFrame(side, text="操作", padding=PAD_S)
        op.pack(fill="x", pady=(PAD_S, 0))
        ttk.Button(op, text="删除所选", command=self._on_delete).pack(fill="x")
        ttk.Button(op, text="交换所选两页", command=self._on_swap).pack(fill="x", pady=(PAD_XS, 0))
        ttk.Button(
            op, text="在所选后插入/移除切分点", command=self._on_toggle_markers
        ).pack(fill="x", pady=(PAD_XS, 0))
        ttk.Button(op, text="清除所有切分点", command=self._on_clear_markers).pack(
            fill="x", pady=(PAD_XS, 0)
        )

        # — 输出 —
        out = ttk.LabelFrame(side, text="导出", padding=PAD_S)
        out.pack(fill="x", pady=(PAD_S, 0))
        ttk.Radiobutton(out, text="合并为一个 PDF",
                        variable=self.mode_var, value="merge").pack(anchor="w")
        ttk.Radiobutton(out, text="按切分点拆分",
                        variable=self.mode_var, value="marker").pack(anchor="w")
        row = ttk.Frame(out); row.pack(anchor="w")
        ttk.Radiobutton(row, text="每 N 页拆分  N =",
                        variable=self.mode_var, value="chunk").pack(side="left")
        ttk.Entry(
            row, width=5, textvariable=self.chunk_size_var,
            validate="key",
            validatecommand=(self.register(is_digit_or_empty), "%P"),
        ).pack(side="left", padx=PAD_XS)
        ttk.Radiobutton(out, text="按来源文件拆分",
                        variable=self.mode_var, value="source").pack(anchor="w")

        ttk.Button(
            side, text="  导出 PDF  ", style="Accent.TButton", command=self._on_export,
        ).pack(fill="x", pady=(PAD_M, 0), ipady=PAD_XS)

    # ------------------------------------------------------------------
    # 状态显示
    # ------------------------------------------------------------------

    def _update_status(self) -> None:
        n_pages = len(self.pages)
        n_docs = len(self.loaded_docs)
        n_sel = len(self.selected)
        if n_pages == 0:
            self.status_var.set("尚未加载 PDF")
        else:
            msg = f"共 {n_pages} 页 · 来自 {n_docs} 个文件"
            if n_sel:
                msg += f" · 已选 {n_sel}"
            if self.split_markers and self.mode_var.get() == "marker":
                msg += f" · {len(self.split_markers) + 1} 段"
            self.status_var.set(msg)

    # ------------------------------------------------------------------
    # 加载 / 清空
    # ------------------------------------------------------------------

    def _on_add_pdf(self) -> None:
        if not HAS_FITZ:
            messagebox.showerror("错误", "未安装 PyMuPDF。请运行：pip install pymupdf")
            return
        paths = filedialog.askopenfilenames(
            title="选择 PDF（可多选）",
            initialdir=self.desktop,
            filetypes=[("PDF 文件", "*.pdf"), ("所有文件", "*.*")],
        )
        if not paths:
            return
        for p in paths:
            self._add_pdf(p)
        self._update_status()
        self._relayout()
        self._schedule_render_missing()

    def _add_pdf(self, path: str) -> None:
        try:
            doc = fitz.open(path)
        except Exception as e:
            messagebox.showerror("错误", f"无法打开：{path}\n({e})")
            return
        doc_id = len(self.loaded_docs)
        label = os.path.basename(path)
        self.loaded_docs.append({"path": path, "doc": doc, "label": label})
        for i in range(len(doc)):
            self.pages.append(PageRef(doc_id, i, label))

    def _on_clear_all(self) -> None:
        if not self.pages:
            return
        if not messagebox.askyesno("确认", "清空所有已加载的 PDF？"):
            return
        self._render_stop.set()
        self._render_stop = threading.Event()
        for d in self.loaded_docs:
            try:
                d["doc"].close()
            except Exception:
                pass
        self.loaded_docs.clear()
        self.pages.clear()
        self.selected.clear()
        self.split_markers.clear()
        self.thumb_cache.clear()
        self.anchor_idx = None
        self._update_status()
        self._relayout()

    # ------------------------------------------------------------------
    # 选择
    # ------------------------------------------------------------------

    def _set_selection(self, new_sel: set[int]) -> None:
        self.selected = {i for i in new_sel if 0 <= i < len(self.pages)}
        self._refresh_item_styles()
        self._update_status()

    def _on_apply_expr(self) -> None:
        ranges = parse_page_ranges(self.page_expr_var.get(), len(self.pages))
        if ranges is None:
            messagebox.showerror("错误", "无法解析页码表达式")
            return
        self._set_selection(ranges)

    def _on_select_all(self) -> None:
        self._set_selection(set(range(len(self.pages))))

    def _on_invert(self) -> None:
        all_idx = set(range(len(self.pages)))
        self._set_selection(all_idx - self.selected)

    def _on_clear_selection(self) -> None:
        self._set_selection(set())

    def _on_canvas_click(self, event) -> None:
        # 点到画布空白处 → 清除选择
        if self.canvas.find_withtag("current") == (self._inner_window,):
            self._set_selection(set())

    # ------------------------------------------------------------------
    # 增删改排
    # ------------------------------------------------------------------

    def _on_delete(self) -> None:
        if not self.selected:
            return
        if not messagebox.askyesno("确认", f"从队列中移除 {len(self.selected)} 页？（不影响原文件）"):
            return
        keep = [p for i, p in enumerate(self.pages) if i not in self.selected]
        # 调整切分点
        deleted_sorted = sorted(self.selected)
        new_markers: set[int] = set()
        for m in self.split_markers:
            if m in self.selected:
                continue  # 该页被删，其后的切分点无效
            shift = sum(1 for d in deleted_sorted if d <= m)
            new_markers.add(m - shift)
        # 切分点必须 < len(keep) - 1 才有意义
        new_markers = {m for m in new_markers if 0 <= m < len(keep) - 1}
        self.pages = keep
        self.split_markers = new_markers
        self.selected.clear()
        self.anchor_idx = None
        self._update_status()
        self._relayout()

    def _on_swap(self) -> None:
        if len(self.selected) != 2:
            messagebox.showinfo("提示", "请先正好选中 2 页进行交换")
            return
        a, b = sorted(self.selected)
        self.pages[a], self.pages[b] = self.pages[b], self.pages[a]
        self._relayout()

    def _on_move(self, delta: int) -> None:
        if not self.selected:
            return
        order = sorted(self.selected, reverse=(delta > 0))
        new_positions: set[int] = set()
        for i in order:
            target = i + delta
            if target < 0 or target >= len(self.pages):
                new_positions.add(i)
                continue
            if target in new_positions:
                new_positions.add(i)
                continue
            self.pages[i], self.pages[target] = self.pages[target], self.pages[i]
            # 同步交换切分点
            self._swap_markers(i, target)
            new_positions.add(target)
        self.selected = new_positions
        self._refresh_item_styles()
        self._relayout()

    def _swap_markers(self, a: int, b: int) -> None:
        ma, mb = (a in self.split_markers), (b in self.split_markers)
        self.split_markers.discard(a); self.split_markers.discard(b)
        if mb: self.split_markers.add(a)
        if ma: self.split_markers.add(b)

    def _on_move_edge(self, to_top: bool) -> None:
        if not self.selected:
            return
        indices = sorted(self.selected)
        moved = [self.pages[i] for i in indices]
        rest = [p for i, p in enumerate(self.pages) if i not in self.selected]
        if to_top:
            self.pages = moved + rest
            self.selected = set(range(len(moved)))
        else:
            self.pages = rest + moved
            self.selected = set(range(len(rest), len(rest) + len(moved)))
        # 移到边缘时清空切分点（简化处理，提示用户）
        self.split_markers.clear()
        self.anchor_idx = None
        self._relayout()

    def _on_toggle_markers(self) -> None:
        if not self.selected:
            return
        # 在每个选中页"之后"插入切分点；若已存在则移除
        for i in sorted(self.selected):
            if i >= len(self.pages) - 1:
                continue  # 最后一页之后无效
            if i in self.split_markers:
                self.split_markers.discard(i)
            else:
                self.split_markers.add(i)
        self._update_status()
        self._refresh_item_styles()

    def _on_clear_markers(self) -> None:
        if not self.split_markers:
            return
        self.split_markers.clear()
        self._update_status()
        self._refresh_item_styles()

    # ------------------------------------------------------------------
    # 布局与渲染
    # ------------------------------------------------------------------

    def _on_canvas_resize(self, event) -> None:
        # 让 inner 宽度跟上 canvas
        self.canvas.itemconfig(self._inner_window, width=event.width - 2)
        cols = max(1, (event.width - 2 * self.CELL_PAD) // self.CELL_W)
        if cols != self._current_cols:
            self._current_cols = cols
            self._relayout()

    def _on_mousewheel(self, event) -> None:
        self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def _get_placeholder(self) -> ImageTk.PhotoImage:
        if self._placeholder is None:
            img = Image.new("RGB", (self.THUMB_W, self.THUMB_H), "#e5e7eb")
            self._placeholder = ImageTk.PhotoImage(img)
        return self._placeholder

    def _relayout(self) -> None:
        """销毁旧的 item widget，按 self.pages 重建网格。"""
        for w in self.item_widgets:
            w.destroy()
        self.item_widgets.clear()
        if self._drop_indicator is not None:
            self._drop_indicator.place_forget()

        # 预计算段号（用于显示"段 N"徽章）
        seg_no = self._compute_segment_numbers()

        cols = max(1, self._current_cols)
        for i, page in enumerate(self.pages):
            item = self._make_item(i, page, seg_no[i])
            r, c = divmod(i, cols)
            item.grid(row=r, column=c, padx=self.CELL_PAD, pady=self.CELL_PAD, sticky="n")
            self.item_widgets.append(item)

        self._refresh_item_styles()
        self.inner.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _make_item(self, idx: int, page: PageRef, seg: int) -> tk.Frame:
        frame = tk.Frame(
            self.inner, width=self.CELL_W - self.CELL_PAD * 2, height=self.CELL_H,
            background=self.CLR_ITEM_BG,
            highlightthickness=2, highlightbackground=self.CLR_ITEM_BD,
        )
        frame.grid_propagate(False)
        frame.pack_propagate(False)
        frame.idx = idx  # type: ignore[attr-defined]

        thumb_key = (page.doc_id, page.page_index)
        img = self.thumb_cache.get(thumb_key, self._get_placeholder())
        img_label = tk.Label(frame, image=img, background=self.CLR_ITEM_BG, borderwidth=0)
        img_label.pack(pady=(PAD_XS, 0))
        img_label.image = img  # keep ref

        text = f"{idx + 1}. {page.source_label[:12]}{'…' if len(page.source_label) > 12 else ''}  p.{page.page_index + 1}"
        text_label = tk.Label(
            frame, text=text, font=FONT_SMALL, background=self.CLR_ITEM_BG,
            foreground="#374151", anchor="w",
        )
        text_label.pack(fill="x", padx=PAD_XS)

        # 切分段徽章：只在"按切分点"模式下且本段首页显示
        if (self.mode_var.get() == "marker" and idx > 0 and (idx - 1) in self.split_markers) or (
            self.mode_var.get() == "marker" and idx == 0 and self.split_markers
        ):
            tk.Label(
                frame, text=f" 段 {seg} ",
                font=FONT_SMALL, background=self.CLR_SEG_BD, foreground="white",
            ).place(x=PAD_XS, y=PAD_XS)

        # 事件绑定（在框与子 widget 都绑定，避免子 widget 吞掉）
        for w in (frame, img_label, text_label):
            w.bind("<ButtonPress-1>", lambda e, i=idx: self._on_item_press(e, i))
            w.bind("<B1-Motion>", self._on_item_motion)
            w.bind("<ButtonRelease-1>", self._on_item_release)
            w.bind("<Double-Button-1>", lambda e, i=idx: self._on_item_double(i))

        return frame

    def _compute_segment_numbers(self) -> list[int]:
        seg_no: list[int] = []
        cur = 1
        for i in range(len(self.pages)):
            seg_no.append(cur)
            if i in self.split_markers:
                cur += 1
        return seg_no

    def _refresh_item_styles(self) -> None:
        for i, frame in enumerate(self.item_widgets):
            if i in self.selected:
                frame.configure(highlightbackground=self.CLR_ITEM_SEL, highlightcolor=self.CLR_ITEM_SEL)
            elif (i - 1) in self.split_markers:
                frame.configure(highlightbackground=self.CLR_SEG_BD, highlightcolor=self.CLR_SEG_BD)
            elif i == 0 and self.split_markers:
                frame.configure(highlightbackground=self.CLR_SEG_BD, highlightcolor=self.CLR_SEG_BD)
            else:
                frame.configure(highlightbackground=self.CLR_ITEM_BD, highlightcolor=self.CLR_ITEM_BD)

    # ------------------------------------------------------------------
    # 缩略图后台渲染
    # ------------------------------------------------------------------

    def _schedule_render_missing(self) -> None:
        todo: list[tuple[int, int]] = []
        for p in self.pages:
            k = (p.doc_id, p.page_index)
            if k not in self.thumb_cache:
                todo.append(k)
        if not todo:
            return
        stop = self._render_stop
        run_in_background(lambda: self._render_worker(todo, stop))

    def _render_worker(self, keys: list[tuple[int, int]], stop: threading.Event) -> None:
        for doc_id, page_index in keys:
            if stop.is_set():
                return
            if doc_id >= len(self.loaded_docs):
                continue
            try:
                doc = self.loaded_docs[doc_id]["doc"]
                page = doc.load_page(page_index)
                rect = page.rect
                scale = min(self.THUMB_W / max(1, rect.width), self.THUMB_H / max(1, rect.height))
                pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            except Exception:
                continue
            # 居中放到固定画布，便于视觉对齐
            canvas = Image.new("RGB", (self.THUMB_W, self.THUMB_H), "#ffffff")
            ox = (self.THUMB_W - img.width) // 2
            oy = (self.THUMB_H - img.height) // 2
            canvas.paste(img, (ox, oy))

            def apply(key=(doc_id, page_index), im=canvas):
                if stop.is_set():
                    return
                photo = ImageTk.PhotoImage(im)
                self.thumb_cache[key] = photo
                self._apply_thumb_to_items(key)

            try:
                self.after(0, apply)
            except tk.TclError:
                return

    def _apply_thumb_to_items(self, key: tuple[int, int]) -> None:
        photo = self.thumb_cache.get(key)
        if photo is None:
            return
        for i, page in enumerate(self.pages):
            if (page.doc_id, page.page_index) != key:
                continue
            if i >= len(self.item_widgets):
                continue
            frame = self.item_widgets[i]
            for child in frame.winfo_children():
                if isinstance(child, tk.Label) and getattr(child, "image", None) is not None:
                    child.configure(image=photo)
                    child.image = photo  # keep ref
                    break

    # ------------------------------------------------------------------
    # 拖拽与点击
    # ------------------------------------------------------------------

    def _on_item_press(self, event, idx: int) -> None:
        self._press_idx = idx
        self._press_xy = (event.x_root, event.y_root)
        self._dragging = False

    def _on_item_motion(self, event) -> None:
        if self._press_idx is None or self._press_xy is None:
            return
        dx = event.x_root - self._press_xy[0]
        dy = event.y_root - self._press_xy[1]
        if not self._dragging and (dx * dx + dy * dy) > 25:
            self._dragging = True
            if self._press_idx not in self.selected:
                self._set_selection({self._press_idx})
                self.anchor_idx = self._press_idx
        if self._dragging:
            target = self._hit_test(event.x_root, event.y_root)
            self._drop_target = target
            self._show_drop_indicator(target)

    def _on_item_release(self, event) -> None:
        if self._press_idx is None:
            return
        if self._dragging:
            self._hide_drop_indicator()
            target = self._drop_target
            if target is not None:
                self._move_selected_to(target)
        else:
            # 当作点击处理
            self._handle_click(event, self._press_idx)
        self._press_idx = None
        self._press_xy = None
        self._dragging = False
        self._drop_target = None

    def _on_item_double(self, idx: int) -> None:
        # 双击=单选该页（用于在多选后快速回到单选）
        self._set_selection({idx})
        self.anchor_idx = idx

    def _handle_click(self, event, idx: int) -> None:
        ctrl = (event.state & 0x0004) != 0
        shift = (event.state & 0x0001) != 0
        if shift and self.anchor_idx is not None:
            lo, hi = sorted((self.anchor_idx, idx))
            self._set_selection(set(range(lo, hi + 1)))
        elif ctrl:
            new = set(self.selected)
            if idx in new:
                new.remove(idx)
            else:
                new.add(idx)
            self._set_selection(new)
            self.anchor_idx = idx
        else:
            self._set_selection({idx})
            self.anchor_idx = idx

    def _hit_test(self, x_root: int, y_root: int) -> int:
        """根据屏幕坐标判断：应插入到哪一个 index 之前（0..len）。"""
        if not self.item_widgets:
            return 0
        # 转换到 inner frame 坐标
        ix = x_root - self.inner.winfo_rootx()
        iy = y_root - self.inner.winfo_rooty()
        # 按行匹配
        rows: dict[int, list[int]] = {}
        for i, w in enumerate(self.item_widgets):
            y = w.winfo_y()
            rows.setdefault(y, []).append(i)
        row_ys = sorted(rows.keys())
        # 选中最接近的行
        chosen_row = row_ys[0]
        for y in row_ys:
            h = self.item_widgets[rows[y][0]].winfo_height()
            if y <= iy < y + h:
                chosen_row = y
                break
            if iy >= y + h:
                chosen_row = y
        indices = rows[chosen_row]
        # 在该行内按 x 判定
        for i in indices:
            w = self.item_widgets[i]
            wx, ww = w.winfo_x(), w.winfo_width()
            if ix < wx + ww // 2:
                return i
        # 插入到该行末尾（= 下一行首或整体末尾）
        return indices[-1] + 1

    def _show_drop_indicator(self, target: int) -> None:
        if self._drop_indicator is None:
            self._drop_indicator = tk.Frame(self.inner, background=self.CLR_DROP)
        if target < len(self.item_widgets):
            w = self.item_widgets[target]
            x = w.winfo_x() - 3
            y = w.winfo_y()
            h = w.winfo_height()
        else:
            w = self.item_widgets[-1]
            x = w.winfo_x() + w.winfo_width() + 1
            y = w.winfo_y()
            h = w.winfo_height()
        self._drop_indicator.place(x=x, y=y, width=3, height=h)
        self._drop_indicator.lift()

    def _hide_drop_indicator(self) -> None:
        if self._drop_indicator is not None:
            self._drop_indicator.place_forget()

    def _move_selected_to(self, target: int) -> None:
        if not self.selected:
            return
        indices = sorted(self.selected)
        moved_pages = [self.pages[i] for i in indices]
        moved_markers_after = {i for i in indices if i in self.split_markers}
        remaining_pages = [p for i, p in enumerate(self.pages) if i not in self.selected]
        remaining_markers = {m for m in self.split_markers if m not in self.selected}
        # 调整 target（去掉已移除位置）
        shift_before_target = sum(1 for i in indices if i < target)
        insert_at = target - shift_before_target
        insert_at = max(0, min(insert_at, len(remaining_pages)))
        # 修正 remaining_markers：索引 > insert_at-1 的需向后推 len(moved_pages)
        new_markers: set[int] = set()
        for m in remaining_markers:
            # m 当前对应的页在 remaining 中的下标即 m 本身经过同样偏移
            shift_m = sum(1 for i in indices if i <= m)
            m2 = m - shift_m
            if m2 < insert_at:
                new_markers.add(m2)
            else:
                new_markers.add(m2 + len(moved_pages))
        # 加回被移动块内部的切分点（需重新计算相对位置）
        if moved_markers_after:
            idx_of = {orig: k for k, orig in enumerate(indices)}
            for orig in moved_markers_after:
                if idx_of[orig] == len(indices) - 1:
                    continue  # 被移动块最后一页的切分点丢弃（对应位置在块外）
                new_markers.add(insert_at + idx_of[orig])
        self.pages = remaining_pages[:insert_at] + moved_pages + remaining_pages[insert_at:]
        self.split_markers = {m for m in new_markers if 0 <= m < len(self.pages) - 1}
        self.selected = set(range(insert_at, insert_at + len(moved_pages)))
        self.anchor_idx = insert_at
        self._relayout()

    # ------------------------------------------------------------------
    # 导出
    # ------------------------------------------------------------------

    def _on_export(self) -> None:
        if not HAS_FITZ:
            messagebox.showerror("错误", "未安装 PyMuPDF。请运行：pip install pymupdf")
            return
        if not self.pages:
            messagebox.showerror("错误", "队列为空")
            return

        out_dir = filedialog.askdirectory(
            title="选择输出文件夹",
            initialdir=self.desktop,
        )
        if not out_dir:
            return

        mode = self.mode_var.get()
        if mode == "merge":
            segments = [list(self.pages)]
        elif mode == "marker":
            segments = self._segments_by_markers()
        elif mode == "chunk":
            try:
                n = int(self.chunk_size_var.get())
                if n <= 0:
                    raise ValueError
            except Exception:
                messagebox.showerror("错误", "请输入正整数 N")
                return
            segments = [self.pages[i:i + n] for i in range(0, len(self.pages), n)]
        elif mode == "source":
            segments = self._segments_by_source()
        else:
            return

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        outputs: list[str] = []
        if len(segments) == 1:
            outputs.append(os.path.join(out_dir, f"TPDF-merged-{ts}.pdf"))
        else:
            for i in range(len(segments)):
                outputs.append(os.path.join(out_dir, f"TPDF-{ts}-part_{i + 1:02d}.pdf"))

        dlg = ProgressDialog(
            self.winfo_toplevel(), "导出 PDF",
            maximum=sum(len(seg) for seg in segments) + 1,
        )
        run_in_background(lambda: self._export_worker(segments, outputs, dlg))

    def _segments_by_markers(self) -> list[list[PageRef]]:
        segs: list[list[PageRef]] = []
        cur: list[PageRef] = []
        for i, p in enumerate(self.pages):
            cur.append(p)
            if i in self.split_markers:
                segs.append(cur)
                cur = []
        if cur:
            segs.append(cur)
        return segs

    def _segments_by_source(self) -> list[list[PageRef]]:
        segs: list[list[PageRef]] = []
        cur: list[PageRef] = []
        last_doc = -1
        for p in self.pages:
            if p.doc_id != last_doc and cur:
                segs.append(cur)
                cur = []
            cur.append(p)
            last_doc = p.doc_id
        if cur:
            segs.append(cur)
        return segs

    def _export_worker(
        self, segments: list[list[PageRef]], outputs: list[str], dlg: ProgressDialog,
    ) -> None:
        processed = 0
        try:
            for seg, out_path in zip(segments, outputs):
                if dlg.cancelled:
                    raise KeyboardInterrupt("任务已取消")
                out_doc = fitz.open()
                try:
                    for p in seg:
                        if dlg.cancelled:
                            raise KeyboardInterrupt("任务已取消")
                        src = self.loaded_docs[p.doc_id]["doc"]
                        out_doc.insert_pdf(src, from_page=p.page_index, to_page=p.page_index)
                        processed += 1
                        dlg.set_progress(
                            processed,
                            f"写入 {os.path.basename(out_path)}（{processed} 页）",
                        )
                    out_doc.save(out_path)
                finally:
                    out_doc.close()
            dlg.set_progress(processed + 1, "完成写入")
            summary = (
                f"已生成 {len(outputs)} 个 PDF\n输出：{os.path.dirname(outputs[0])}"
                if len(outputs) > 1
                else f"已生成：{outputs[0]}"
            )
            dlg.finish(summary)
        except KeyboardInterrupt as e:
            dlg.close()
            messagebox.showinfo("信息", f"任务取消\n({e})")
        except Exception as e:
            dlg.close()
            messagebox.showerror("错误", f"导出失败\n({e})")


# =============================================================================
# 主应用
# =============================================================================

class TPDFApp:
    def __init__(self) -> None:
        self.desktop = get_desktop_path()
        self.root = tk.Tk()
        self.root.title("TPDF — 图片 ↔ PDF 工具")
        self.root.geometry(WINDOW_SIZE)
        self.root.minsize(*MIN_WINDOW_SIZE)
        self.root.configure(bg=COLOR_BG)
        self._setup_style()
        self._build_ui()

    def _setup_style(self) -> None:
        style = ttk.Style()
        for theme in ("clam", "vista", "default"):
            if theme in style.theme_names():
                style.theme_use(theme)
                break

        self.root.option_add("*Font", FONT_BODY)

        # 全局
        style.configure(".", background=COLOR_BG, foreground="#1f2937")
        style.configure("TFrame", background=COLOR_BG)
        style.configure("TLabel", background=COLOR_BG, font=FONT_BODY)
        style.configure("TLabelframe", background=COLOR_BG, bordercolor=COLOR_BORDER,
                        relief="solid", borderwidth=1)
        style.configure("TLabelframe.Label", background=COLOR_BG, font=FONT_HEAD,
                        foreground="#111827")

        # Entry —— 显式映射 disabled / readonly 背景色，让"只读/禁用"一眼可辨
        style.configure(
            "TEntry", fieldbackground="white", bordercolor=COLOR_BORDER,
            lightcolor=COLOR_BORDER, darkcolor=COLOR_BORDER,
            padding=(PAD_XS, PAD_XS + 1),
        )
        style.map(
            "TEntry",
            fieldbackground=[("readonly", "#e5e7eb"), ("disabled", "#f3f4f6")],
            foreground=[("readonly", "#4b5563"), ("disabled", "#9ca3af")],
            bordercolor=[("readonly", "#cbd5e1"), ("disabled", "#e5e7eb")],
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", "white"), ("disabled", "#f3f4f6")],
            foreground=[("disabled", "#9ca3af")],
        )

        # Checkbutton / Radiobutton —— 用自定义图像指示器
        pil_imgs = make_indicator_images()
        # 强引用保存，避免 PhotoImage 被 Python GC 回收
        self._ind_imgs = {k: ImageTk.PhotoImage(v) for k, v in pil_imgs.items()}
        img = self._ind_imgs

        # 注意：Python 3.14 的 tkinter 要求每个状态映射是"单个 tuple，
        # 最后一项是 image"，不再接受交替的 (statespec, image) 对。
        # 形如 ("selected", "disabled", image) = statespec 取前 N-1 项、最后
        # 一项是 image，这是跨 3.12~3.14 都能工作的写法。
        # Tk 按顺序取第一个匹配的 statespec，所以把"更特殊"的放前面。
        try:
            style.element_create(
                "tpdf.check_indicator", "image",
                img["check_off"],  # 默认：未选中·可用
                ("selected", "disabled", img["check_dis_on"]),
                ("disabled", img["check_dis_off"]),
                ("selected", img["check_on"]),
                border=0, sticky="",
            )
        except tk.TclError:
            pass
        try:
            style.element_create(
                "tpdf.radio_indicator", "image",
                img["radio_off"],
                ("selected", "disabled", img["radio_dis_on"]),
                ("disabled", img["radio_dis_off"]),
                ("selected", img["radio_on"]),
                border=0, sticky="",
            )
        except tk.TclError:
            pass

        # 覆盖默认 layout，让 TCheckbutton / TRadiobutton 使用我们的指示器
        style.layout("TCheckbutton", [
            ("Checkbutton.padding", {"sticky": "nswe", "children": [
                ("tpdf.check_indicator", {"side": "left", "sticky": ""}),
                ("Checkbutton.focus", {"side": "left", "sticky": "", "children": [
                    ("Checkbutton.label", {"sticky": "nswe"}),
                ]}),
            ]}),
        ])
        style.layout("TRadiobutton", [
            ("Radiobutton.padding", {"sticky": "nswe", "children": [
                ("tpdf.radio_indicator", {"side": "left", "sticky": ""}),
                ("Radiobutton.focus", {"side": "left", "sticky": "", "children": [
                    ("Radiobutton.label", {"sticky": "nswe"}),
                ]}),
            ]}),
        ])

        style.configure("TCheckbutton", background=COLOR_BG, font=FONT_BODY,
                        padding=(PAD_XS, PAD_XS))
        style.configure("TRadiobutton", background=COLOR_BG, font=FONT_BODY,
                        padding=(PAD_XS, PAD_XS))
        style.map(
            "TCheckbutton",
            foreground=[("disabled", "#9ca3af"), ("!disabled", "#1f2937")],
            background=[("active", COLOR_BG), ("disabled", COLOR_BG)],
        )
        style.map(
            "TRadiobutton",
            foreground=[("disabled", "#9ca3af"), ("!disabled", "#1f2937")],
            background=[("active", COLOR_BG), ("disabled", COLOR_BG)],
        )

        # 普通按钮
        style.configure("TButton", padding=(PAD_M, PAD_XS + 2), font=FONT_BODY)

        # 主按钮（蓝底白字）
        style.configure(
            "Accent.TButton",
            background=COLOR_ACCENT, foreground="white",
            font=(FONT_BODY[0], FONT_BODY[1], "bold"),
            padding=(PAD_L, PAD_S + 1),
            borderwidth=0,
        )
        style.map(
            "Accent.TButton",
            background=[("active", COLOR_ACCENT_HOVER), ("pressed", COLOR_ACCENT_HOVER)],
            foreground=[("disabled", "#e5e7eb")],
        )

        # Combobox
        style.configure("TCombobox", padding=(PAD_XS, PAD_XS))

        # Notebook —— 选中 / 未选同样大小，只用底色与文字色区分
        # 关键点：clam 主题默认给 TNotebook.Tab 的 -padding 和 -expand 都挂了
        # selected 状态下的特殊值（会让选中 tab 比未选中的略大或略小）。我们
        # 必须把这两个状态映射同时设为固定值，才能得到完全一致的尺寸。
        tab_pad = (PAD_L + PAD_XS, PAD_S + 2)
        style.configure("TNotebook", background=COLOR_BG, borderwidth=0,
                        tabmargins=(PAD_S, PAD_S, PAD_S, 0))
        style.configure(
            "TNotebook.Tab",
            font=(FONT_BODY[0], FONT_BODY[1], "bold"),
            padding=tab_pad,
            background="#e7e9ee",
            foreground="#4b5563",
            borderwidth=0,
            focuscolor=COLOR_BG,
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", COLOR_BG), ("active", "#eceef3")],
            foreground=[("selected", COLOR_ACCENT), ("active", "#1f2937")],
            padding=[("selected", tab_pad), ("!selected", tab_pad)],
            expand=[("selected", [0, 0, 0, 0]), ("!selected", [0, 0, 0, 0])],
        )

        # Progressbar
        style.configure(
            "TProgressbar",
            troughcolor="#e5e7eb", background=COLOR_ACCENT,
            bordercolor=COLOR_BG, lightcolor=COLOR_ACCENT, darkcolor=COLOR_ACCENT,
            thickness=int(14 * SCALE),
        )

    def _build_ui(self) -> None:
        header = ttk.Frame(self.root, padding=(PAD_L + PAD_S, PAD_M, PAD_L, 0))
        header.pack(fill="x")
        ttk.Label(header, text="TPDF", font=FONT_TITLE, foreground="#111827").pack(side="left")
        ttk.Label(
            header, text="   图片 ↔ PDF 工具",
            font=FONT_BODY, foreground=COLOR_MUTED,
        ).pack(side="left", pady=(PAD_S, 0))

        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=PAD_L, pady=(PAD_S, PAD_S))
        notebook.add(Img2PdfTab(notebook, self.desktop), text="  图片 → PDF  ")
        notebook.add(Pdf2ImgTab(notebook, self.desktop), text="  PDF → 图片  ")
        notebook.add(PdfEditTab(notebook, self.desktop), text="  PDF 编辑  ")

        footer = ttk.Frame(self.root, padding=(PAD_L + PAD_S, 0, PAD_L, PAD_M))
        footer.pack(fill="x")
        ttk.Label(
            footer,
            text="任务在后台线程执行；大图会消耗较多内存。",
            font=FONT_SMALL, foreground=COLOR_MUTED,
        ).pack(side="left")

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    TPDFApp().run()


if __name__ == "__main__":
    main()
