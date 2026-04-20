conda activate tpdf

非 a4 转 a4：安全做法
1，复制需要的图片到 imgnew
2，python imgpad.py imgnew/ imgnew/ black a4
3，移出 imgnew 新图片

合成 pdf
python img2pdf.py img-done/ out.pdf 1500
限制高为 1500
或者用 UI