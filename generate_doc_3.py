import os
import datetime

# -------------------------------------------------------------
# CONFIG
# -------------------------------------------------------------
OUTPUT_NAME = None  # None -> tự đặt tên theo thư mục module

# Thư mục bị loại trừ ở mọi cấp
EXCLUDED_DIRS = {"__pycache__"}


# -------------------------------------------------------------
# HÀM TẠO BANNER
# -------------------------------------------------------------
def make_banner(module_name):
    banner = f"""
################################################################################
#                      {module_name.upper():<50}#
#                   ODOO MODULE DOCUMENTATION GENERATOR                     #
#                           Version 1.2.0 - Enterprise Style                #
################################################################################
"""
    return banner


# -------------------------------------------------------------
# HÀM QUÉT FILES (BỎ QUA __pycache__)
# -------------------------------------------------------------
def scan_files(root):
    file_list = []

    for base, dirs, files in os.walk(root):
        # 🔥 CHẶN __pycache__ Ở MỌI CẤP
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]

        dirs.sort()
        files.sort()

        for f in files:
            full_path = os.path.join(base, f)
            rel = os.path.relpath(full_path, root).replace("\\", "/")
            file_list.append(rel)

    return file_list


# -------------------------------------------------------------
# HÀM XÁC ĐỊNH LOẠI FILE
# -------------------------------------------------------------
def detect_type(file):
    ext = file.lower().split(".")[-1]
    if ext == "py":
        return "Python"
    if ext == "xml":
        return "XML"
    if ext == "csv":
        return "CSV"
    if ext == "js":
        return "JS"
    if ext == "css":
        return "CSS"
    if ext in ["png", "jpg", "jpeg", "svg"]:
        return "Image"
    return "Other"


# -------------------------------------------------------------
# HÀM SINH CÂY THƯ MỤC DẠNG TREE (ASCII)
# -------------------------------------------------------------
def generate_directory_tree(files):
    """
    Sinh cây thư mục dạng ASCII từ danh sách file path
    """
    if not files:
        return ""

    # Xây dựng cấu trúc cây dạng dict
    tree = {}
    for path in files:
        parts = path.split("/")
        current = tree
        for part in parts:
            current = current.setdefault(part, {})

    lines = []

    def render(node, prefix="", is_root=True):
        items = list(node.items())
        for i, (name, children) in enumerate(items):
            is_last = (i == len(items) - 1)

            if is_root:
                connector = ""
                new_prefix = ""
            else:
                connector = "└── " if is_last else "├── "
                new_prefix = prefix + ("    " if is_last else "│   ")

            icon = "📁" if children else "📄"
            lines.append(f"{prefix}{connector}{icon} {name}")

            if children:
                render(children, new_prefix, is_root=False)

    render(tree)

    output = []
    output.append("================================================================================")
    output.append("                                📂 DIRECTORY TREE")
    output.append("================================================================================")
    output.append("\n".join(lines))
    output.append("\n")

    return "\n".join(output)


# -------------------------------------------------------------
# HÀM SINH CẤU TRÚC THƯ MỤC DẠNG STT (GIỮ NGUYÊN)
# -------------------------------------------------------------
def generate_tree(files, root):
    lines = []
    counter = 1

    lines.append("================================================================================")
    lines.append(f"                              CẤU TRÚC THƯ MỤC - {len(files)} FILES")
    lines.append("================================================================================\n")

    for f in files:
        lines.append(f"{counter:>3}.  {f}")
        counter += 1

    lines.append("\n")
    return "\n".join(lines)


# -------------------------------------------------------------
# HÀM SINH BẢNG TỔNG KẾT FILES
# -------------------------------------------------------------
def generate_summary(files):
    lines = []

    lines.append("================================================================================")
    lines.append(f"                         BẢNG TỔNG KẾT {len(files)} FILES")
    lines.append("================================================================================")
    lines.append("│  #  │ Đường dẫn file                                     │ Loại     │")
    lines.append("├─────┼────────────────────────────────────────────────────┼──────────┤")

    idx = 1
    for f in files:
        ftype = detect_type(f)
        lines.append(f"│ {idx:<3} │ {f:<50} │ {ftype:<8} │")
        idx += 1

    lines.append("\n")
    return "\n".join(lines)


# -------------------------------------------------------------
# HÀM ĐỌC NỘI DUNG FILE
# -------------------------------------------------------------
def read_file(fullpath):
    try:
        with open(fullpath, "r", encoding="utf-8") as f:
            return f.read()
    except:
        return "[Không đọc được file – có thể là binary hoặc lỗi mã hóa]"


# -------------------------------------------------------------
# HÀM SINH NỘI DUNG CÁC FILE
# -------------------------------------------------------------
def generate_file_contents(files, root):
    lines = []

    lines.append("\n================================================================================")
    lines.append("                              NỘI DUNG CÁC FILES")
    lines.append("================================================================================\n")

    idx = 1
    for f in files:
        fullpath = os.path.join(root, f)

        lines.append("################################################################################")
        lines.append(f"## FILE {idx}: {os.path.basename(f)}")
        lines.append(f"## Đường dẫn: {f}")
        lines.append("################################################################################\n")

        content = read_file(fullpath)
        lines.append(content)
        lines.append("\n\n")

        idx += 1

    return "\n".join(lines)


# -------------------------------------------------------------
# MAIN
# -------------------------------------------------------------
def main():
    root = os.path.dirname(os.path.abspath(__file__))
    module_name = os.path.basename(root)

    now = datetime.datetime.now().strftime("%Y-%m-%d_%Hh%M")
    output_file = OUTPUT_NAME or f"{module_name}_DOCUMENTATION_{now}.txt"

    files = scan_files(root)
    files = sorted(files)

    output = []
    output.append(make_banner(module_name))
    output.append(generate_directory_tree(files))   # 🌳 CÂY THƯ MỤC (MỚI)
    output.append(generate_tree(files, root))       # 📄 DANH SÁCH FILE
    output.append(generate_summary(files))           # 📊 BẢNG TỔNG KẾT
    output.append(generate_file_contents(files, root))

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(output))

    print(f"\nDONE! File generated: {output_file}")


if __name__ == "__main__":
    main()
