import os
import sys
import subprocess
import threading
import tkinter as tk
from PIL import Image
from datetime import datetime
from tkinter import filedialog, messagebox, ttk, colorchooser

# 设置放大比例
scale_factor = 1.2

size = f"{int(750 * scale_factor)}x{int(256 * scale_factor)}"

font_icon = ("微软雅黑", int(40 * scale_factor))
font_entry = ("等线", int(10 * scale_factor))
font_normal = ("华文中宋", int(12 * scale_factor))
font_button = ("华文中宋", int(10 * scale_factor))

small_label_spacer_width = 2  # times of character width
label_spacer_width = 3  # times of character width

small_entry_width = 10  # times of character width
entry_width = 30  # times of character width
large_entry_width = 40  # times of character width

button_width = int(10 * scale_factor)
button_height = int(1 * scale_factor)

small_pad_x = int(5 * scale_factor)
large_pad_x = int(10 * scale_factor)
small_pad_y = int(5 * scale_factor)
large_pad_y = int(10 * scale_factor)

path = None
Image.MAX_IMAGE_PIXELS = 933120000
color_code = ((255, 255, 255), '#ffffff')

def get_desktop_path():
    global path
    if path is not None:
        return path
    if sys.platform == "win32":
        CREATE_NO_WINDOW = 0x08000000
        command = r'reg query "HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders" /v "Desktop"'
        result = subprocess.run(command, stdout=subprocess.PIPE, text=True, creationflags=CREATE_NO_WINDOW)
        desktop = result.stdout.splitlines()[2].split()[2]
    else:
        desktop = os.path.expanduser("~/Desktop")
    path = desktop
    return desktop

def select_folder(entry):
    folder_path = filedialog.askdirectory(initialdir=os.path.expanduser(get_desktop_path()))
    if folder_path:
        entry.delete(0, tk.END)
        if sys.platform == "win32":
            entry.insert(0, folder_path.replace("/", "\\"))
        else:
            entry.insert(0, folder_path)

def create_folder(folder_path):
    if os.path.exists(folder_path):
        messagebox.showinfo("信息", "无需处理，文件夹已存在")
    else:
        if messagebox.askyesno("确认", "文件夹不存在，是否创建该文件夹？"):
            os.makedirs(folder_path)
            messagebox.showinfo("信息", "文件夹创建成功！")

def choose_color(label):
    global color_code
    color_code = colorchooser.askcolor(title="选择颜色")
    if color_code[1]:  # 如果用户选择了颜色
        label.config(bg=color_code[1])  # 更改标签背景颜色
    print(color_code)

def select_output_file(entry):
    output_file = filedialog.askdirectory(initialdir=os.path.expanduser(get_desktop_path()))
    if output_file:
        entry.delete(0, tk.END)
        if sys.platform == "win32":
            entry.insert(0, output_file.replace("/", "\\"))
        else:
            entry.insert(0, folder_path)
    # output_file = filedialog.asksaveasfilename(
    #     defaultextension=".pdf",
    #     initialfile=f"TPDF-{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
    #     initialdir=os.path.expanduser(get_desktop_path()),
    #     filetypes=[("PDF files", "*.pdf")]
    # )
    # if output_file:
    #     entry.delete(0, tk.END)
    #     if sys.platform == "win32":
    #         entry.insert(0, output_file.replace("/", "\\"))
    #     else:
    #         entry.insert(0, output_file)

def toggle_height():
    if width_check_var.get() and height_check_var.get():
        color_choose.pack(side=tk.LEFT, padx=small_pad_x)
        color_label.pack(side=tk.LEFT, padx=small_pad_x)
    else:
        color_choose.pack_forget()
        color_label.pack_forget()

def toggle_width():
    if width_check_var.get() and height_check_var.get():
        color_choose.pack(side=tk.LEFT, padx=small_pad_x)
        color_label.pack(side=tk.LEFT, padx=small_pad_x)
    else:
        color_choose.pack_forget()
        color_label.pack_forget()

def validate_input(new_value):
    return new_value.isdigit() or new_value == ""

# 创建主窗口
root = tk.Tk()
root.title("TPDF 工具")
root.geometry(size)

# 居中图标
icon_label = tk.Label(root, text="📁🖼→📄", font=font_icon)
icon_label.pack(pady=large_pad_y)

folder_frame = tk.Frame(root)
folder_frame.pack(pady=small_pad_y)

folder_label = tk.Label(folder_frame, text="图片文件夹路径", font=font_normal)
folder_label.pack(side=tk.LEFT)

folder_spacer = tk.Label(folder_frame, text="", font=font_normal, width=small_label_spacer_width)
folder_spacer.pack(side=tk.LEFT)

folder_path = tk.StringVar(value=os.path.expanduser(get_desktop_path() + r"\TPDF输入图片"))
folder_entry = tk.Entry(folder_frame, textvariable=folder_path, width=large_entry_width, font=font_entry)
folder_entry.pack(side=tk.LEFT)

folder_spacer = tk.Label(folder_frame, text="", font=font_normal, width=small_label_spacer_width)
folder_spacer.pack(side=tk.LEFT)

folder_button = tk.Button(folder_frame, text="选择文件夹", width=button_width, height=button_height, font=font_button, command=lambda: select_folder(folder_entry))
folder_button.pack(side=tk.LEFT)

folder_spacer = tk.Label(folder_frame, text="", font=font_normal, width=small_label_spacer_width)
folder_spacer.pack(side=tk.LEFT)

create_button = tk.Button(folder_frame, text="创建文件夹", width=button_width, height=button_height, font=font_button, command=lambda: create_folder(folder_entry.get()))
create_button.pack(side=tk.LEFT)

# 输出文件路径输入框及按钮
output_frame = tk.Frame(root)
output_frame.pack(pady=small_pad_y)

output_label = tk.Label(output_frame, text="输出 PDF 路径", font=font_normal)
output_label.pack(side=tk.LEFT)

output_spacer = tk.Label(output_frame, text="", font=font_normal, width=small_label_spacer_width)
output_spacer.pack(side=tk.LEFT)

output_path = tk.StringVar(value=os.path.expanduser(get_desktop_path()))
output_entry = tk.Entry(output_frame, textvariable=output_path, width=entry_width, font=font_entry)
output_entry.pack(side=tk.LEFT)

output_spacer = tk.Label(output_frame, text="", font=font_normal, width=small_label_spacer_width)
output_spacer.pack(side=tk.LEFT)

output_button = tk.Button(output_frame, text="选择输出位置", width=button_width, height=button_height, font=font_button, command=lambda: select_output_file(output_entry))
output_button.pack(side=tk.LEFT)

output_label = tk.Label(output_frame, text="（文件名自动生成）", font=font_normal)
output_label.pack(side=tk.LEFT)

# 选框
options_frame = tk.Frame(root)
options_frame.pack(pady=small_pad_y)

height_check_var = tk.IntVar(value=1)
width_check_var = tk.IntVar()

vcmd = (root.register(validate_input), '%P')

default_height = tk.StringVar(value="1754")
default_width = tk.StringVar(value="1240")

height_check = tk.Checkbutton(options_frame, text="统一高度", font=font_normal, variable=height_check_var, command=toggle_height)
height_check.pack(side=tk.LEFT, padx=small_pad_x)
height_entry = tk.Entry(options_frame, width=small_entry_width, font=font_entry, validate='key', validatecommand=vcmd, textvariable=default_height)
height_entry.pack(side=tk.LEFT, padx=small_pad_x)

hw_spacer = tk.Label(options_frame, text="", font=font_normal, width=small_label_spacer_width)
hw_spacer.pack(side=tk.LEFT)

width_check = tk.Checkbutton(options_frame, text="统一宽度", font=font_normal, variable=width_check_var, command=toggle_width)
width_check.pack(side=tk.LEFT, padx=small_pad_x)
width_entry = tk.Entry(options_frame, width=small_entry_width, font=font_entry, validate='key', validatecommand=vcmd, textvariable=default_width)
width_entry.pack(side=tk.LEFT, padx=small_pad_x)

hw_spacer = tk.Label(options_frame, text="", font=font_normal, width=small_label_spacer_width)
hw_spacer.pack(side=tk.LEFT)

color_label = tk.Label(options_frame, text="　", font=font_normal, bg=color_code[1])
color_choose = tk.Button(options_frame, text="选择填充颜色", width=button_width, height=button_height, font=font_button, command=lambda:choose_color(color_label))

# color_choose.pack(side=tk.LEFT, padx=small_pad_x)
# color_label.pack(side=tk.LEFT, padx=small_pad_x)


# 启动按钮
start_button = tk.Button(root, text="转为 PDF", width=button_width, height=button_height, font=font_normal, command=lambda: start_task())
start_button.pack(pady=large_pad_y)

progress_var = tk.IntVar()
to_run = True

def start_task():
    global progress_window, max_value, cancel_button, to_run

    to_run = True

    dirname = folder_entry.get()
    output = output_entry.get() + r"\TPDF-{}.pdf".format(datetime.now().strftime('%Y%m%d_%H%M%S'))
    same_height_flag = bool(height_check_var.get())
    same_height = height_entry.get()
    same_width_flag = bool(width_check_var.get())
    same_width = width_entry.get()

    if same_height == "": same_height_flag = False
    else: same_height = int(same_height)
    if same_width == "": same_width_flag = False
    else: same_width = int(same_width)

    if not os.path.exists(dirname):
        messagebox.showerror("错误", "图片输入文件夹不存在")
        return

    filename_list = []
    for filename in os.listdir(dirname):
        filename_list.append(filename)
    filename_list.sort()

    max_value = len(filename_list) + 10
    progress_var.set(0)

    progress_window = tk.Toplevel(root)
    progress_window.geometry("400x120")
    progress_window.title("进度")

    progress_bar = ttk.Progressbar(progress_window, variable=progress_var, maximum=max_value)
    progress_bar.pack(pady=20, padx=20, fill='x')

    cancel_button = ttk.Button(progress_window, text="取消", command=lambda: cancel_task())
    cancel_button.pack(pady=10)

    thread = threading.Thread(target=img_to_pdf, args=(dirname, filename_list, output, same_height_flag, same_height, same_width_flag, same_width))
    thread.start()

def close_window():
    progress_window.destroy()

def cancel_task():
    global to_run
    to_run = False

def img_to_pdf(dirname, filename_list, output, same_height_flag, same_height, same_width_flag, same_width):
    try:
        timer = 0

        img_list = []
        for filename in filename_list:

            if not to_run:
                raise KeyboardInterrupt("任务手动取消")

            my_image_file = os.path.join(dirname, filename)
            im = Image.open(my_image_file)
            width, height = im.size
            if same_height_flag and same_width_flag:
                new_im = Image.new(im.mode, size=(same_width, same_height), color=color_code[0])
                if width / height < same_width / same_height:
                    new_height = same_height
                    new_width = int(width * same_height / height)
                else:
                    new_width = same_width
                    new_height = int(height * same_width / width)
                print(f"{height=}, {width=}")
                print(f"{new_height=}, {new_width=}")
                print(f"{same_height=}, {same_width=}")
                im = im.resize((new_width, new_height))
                new_im.paste(im, ((same_width - new_width) // 2, (same_height - new_height) // 2))
                im = new_im
                print(f"Resized {filename} to {same_width}x{same_height}, padding with {color_code[0]}")
            elif same_height_flag:
                new_height = same_height
                new_width = int(width * same_height / height)
                im = im.resize((new_width, new_height))
                print(f"Resized {filename} to {new_width}x{new_height}")
            elif same_width_flag:
                new_width = same_width
                new_height = int(height * same_width / width)
                im = im.resize((new_width, new_height))
                print(f"Resized {filename} to {new_width}x{new_height}")
            else:
                print(f"{filename}: {width}x{height}")
            img_list.append(im)

            progress_var.set(timer + 1)
            root.update_idletasks()
            timer += 1

        cancel_button.config(text="请等待", command=lambda:None)

        img_list[0].save(
            output, "PDF", resolution=100.0, save_all=True, append_images=img_list[1:]
        )
            
        progress_var.set(max_value)
        root.update_idletasks()

        progress_window.geometry("400x160")
        file_label = tk.Label(progress_window, text=f"输出位置: {output}")
        file_label.pack(pady=10)

        cancel_button.config(text="完成", command=close_window)

    except IndexError as e:
        progress_window.destroy()
        messagebox.showerror("错误", f"文件夹没有内容\n(错误信息：{e})")
        try: os.remove(output)
        except FileNotFoundError:  pass
    
    except FileNotFoundError as e:
        progress_window.destroy()
        messagebox.showerror("错误", f"部分文件不存在\n(错误信息：{e})")
        try: os.remove(output)
        except FileNotFoundError:  pass
    
    except KeyboardInterrupt as e:
        progress_window.destroy()
        messagebox.showinfo("信息", f"任务取消\n(错误信息：{e})")
        try: os.remove(output)
        except FileNotFoundError:  pass

    except Exception as e:
        print(f"{e}")
        progress_window.destroy()
        messagebox.showerror("错误", f"任务失败\n(错误信息：{e})")
        try: os.remove(output)
        except FileNotFoundError:  pass


# 启动主循环
root.mainloop()
