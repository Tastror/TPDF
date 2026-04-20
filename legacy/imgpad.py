from PIL import Image
from pathlib import Path
import os
import sys

# usage: python imgpad.py inputdir outputdir [color (default black)] [hdw (default a4)]
# example:
#   python imgpad.py in/ out/
#   # == python imgpad.py in/ out2/ black a4
#   python imgpad.py in/ out2/ white b5
#   python imgpad.py in/ out3/ red a3
#   python imgpad.py in/ out3/ (0,128,128) 1

color_dict = {
    "white": (255, 255, 255), "black": (0, 0, 0), "red": (255, 0, 0), "green": (0, 255, 0), "blue": (0, 0, 255), "yellow": (255, 255, 0), "cyan": (0, 255, 255), "magenta": (255, 0, 255)
}
hdw_dict = {
    "a4": 297 / 210, "a3": 420 / 297, "a2": 594 / 420, "a1": 841 / 594, "a0": 1189 / 841, "a5": 210 / 148, "a6": 148 / 105, "a7": 105 / 74, "a8": 74 / 52, "a9": 52 / 37, "a10": 37 / 26,
    "b1": 1000 / 707, "b2": 707 / 500, "b3": 500 / 353, "b4": 353 / 250, "b5": 250 / 176, "b6": 176 / 125, "b7": 125 / 88, "b8": 88 / 62, "b9": 62 / 44, "b10": 44 / 31,
}

dirname = sys.argv[1]
outputdir = sys.argv[2]
if len(sys.argv) > 3:
    try:
        color = color_dict[sys.argv[3].lower()]
    except KeyError:
        print("Invalid color, parsing as RGB tuple")
        try:
            color = tuple(eval(sys.argv[3]))
        except ValueError:
            print("Invalid color, using black")
            color = color_dict["black"]
else:
    color = color_dict["black"]
if len(sys.argv) > 4:
    try:
        hdw = hdw_dict[sys.argv[4].lower()]
    except KeyError:
        print("Invalid hdw, parsing as float")
        try:
            hdw = float(eval(sys.argv[4]))
        except ValueError:
            print("Invalid hdw, using A4")
            hdw = hdw_dict["a4"]
else:
    hdw = hdw_dict["a4"]

print(f"Input directory: {dirname}")
print(f"Output directory: {outputdir}")
print(f"Background color: {color}")
print(f"Height/width ratio: {hdw}")

os.makedirs(outputdir, exist_ok=True)

for filename in os.listdir(dirname):
    my_image_file = os.path.join(dirname, filename)
    png_filename = Path(filename).stem + '.png'
    outputfile = os.path.join(outputdir, png_filename)
    im = Image.open(my_image_file)
    width, height = im.size
    # make it A4 size
    if height / width > hdw:
        new_height = height
        new_width = int(height / hdw)
    else:
        new_width = width
        new_height = int(width * hdw)
    print(f"Resizing {filename} to {new_width}x{new_height}")
    new_im = Image.new(im.mode, size=(new_width, new_height), color=color)
    new_im.paste(im, ((new_width - width) // 2, (new_height - height) // 2))
    new_im.save(outputfile, 'PNG', quality=100)
    print(f"Saved {outputfile}")
