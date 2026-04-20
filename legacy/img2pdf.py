from PIL import Image
import sys
import os

# usage: python img2pdf.py inputdir output [same_size (give size (just height), default False)]
# example:
#   python img2pdf.py in/ out.pdf
#   python img2pdf.py in/ out.pdf 2100

dirname = sys.argv[1]
output = sys.argv[2]
if len(sys.argv) > 3:
    same_size = int(sys.argv[3])
else:
    same_size = False

filename_list = []
for filename in os.listdir(dirname):
    filename_list.append(filename)
filename_list.sort()

img_list = []
for filename in filename_list:
    my_image_file = os.path.join(dirname, filename)
    im = Image.open(my_image_file)
    width, height = im.size
    if same_size:
        new_height = same_size
        new_width = int(width * same_size / height)
        im = im.resize((new_width, new_height))
        print(f"Resized {filename} to {new_width}x{new_height}")
    img_list.append(im)

img_list[0].save(
    output, "PDF", resolution=100.0, save_all=True, append_images=img_list[1:]
)