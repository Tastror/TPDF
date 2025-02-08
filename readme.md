# TPDF

a converter merges images to a PDF. (Chinese)

## Build

```shell
conda create --name tpdf python=3.12
pip install pillow pyinstaller
pyinstaller -F -w TPDF.py
```

executable file will be generated in `dist/`.
