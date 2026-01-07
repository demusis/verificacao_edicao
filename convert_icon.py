from PIL import Image
import os

def convert_to_ico(source_path, target_path):
    img = Image.open(source_path)
    # PyInstaller recommends offering multiple sizes in the .ico
    icon_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(target_path, sizes=icon_sizes)
    print(f"Icon saved to {target_path}")

if __name__ == "__main__":
    convert_to_ico("icon.png", "icon.ico")
