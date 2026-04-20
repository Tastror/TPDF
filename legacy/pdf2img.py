import fitz  # PyMuPDF
import os
import re

def extract_images_from_pdf(pdf_path, output_folder):
    """
    从 PDF 文件中提取所有图片并保存到指定文件夹
    
    参数:
        pdf_path (str): PDF 文件路径
        output_folder (str): 图片输出文件夹路径
    """
    # 创建输出文件夹
    os.makedirs(output_folder, exist_ok=True)
    
    # 打开 PDF 文件
    pdf_document = fitz.open(pdf_path)
    
    print(f"正在处理 PDF 文件: {os.path.basename(pdf_path)}")
    print(f"总页数: {len(pdf_document)}")
    
    total_images = 0
    
    # 遍历每一页
    for page_num in range(len(pdf_document)):
        page = pdf_document.load_page(page_num)
        
        # 获取图片列表
        image_list = page.get_images(full=True)
        
        if image_list:
            print(f"第 {page_num + 1} 页发现 {len(image_list)} 张图片")
            
            # 遍历当前页的所有图片
            for img_index, img in enumerate(image_list, start=1):
                xref = img[0]  # 图片引用 ID
                base_image = pdf_document.extract_image(xref)
                image_bytes = base_image["image"]
                image_ext = base_image["ext"]
                
                # 生成合法文件名
                filename = f"page_{page_num + 1}_img_{img_index}.{image_ext}"
                filename = re.sub(r'[\\/*?:"<>|]', "_", filename)  # 替换非法字符
                image_path = os.path.join(output_folder, filename)
                
                # 保存图片
                with open(image_path, "wb") as img_file:
                    img_file.write(image_bytes)
                    total_images += 1
                    print(f"保存图片: {filename}")
    
    print(f"\n提取完成! 共提取 {total_images} 张图片到文件夹: {output_folder}")
    pdf_document.close()

if __name__ == "__main__":
    import sys
    # 检查命令行参数
    if len(sys.argv) != 3:
        print("用法: python pdf2img.py <pdf_file> <output_dir>")
        sys.exit(1)
    
    pdf_file = sys.argv[1]
    output_dir = sys.argv[2]
    
    # 执行提取
    extract_images_from_pdf(pdf_file, output_dir)