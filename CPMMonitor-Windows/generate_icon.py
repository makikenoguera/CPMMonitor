"""Utility script to generate assets/icon.ico from PIL.

Run once on any platform (Mac or Windows) before building:
    python generate_icon.py
"""

import os
from PIL import Image, ImageDraw


def make_icon_image(size: int, active: bool = True) -> Image.Image:
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    color = (255, 107, 53, 255) if active else (128, 128, 128, 255)
    margin = max(2, size // 16)
    draw.ellipse([margin, margin, size - margin, size - margin], fill=color)
    return img


def main() -> None:
    os.makedirs('assets', exist_ok=True)
    ico_path = os.path.join('assets', 'icon.ico')

    # ICO files can contain multiple sizes
    sizes = [16, 32, 48, 64, 128, 256]
    images = [make_icon_image(s) for s in sizes]

    # Save as .ico (Pillow writes multi-size .ico)
    images[0].save(
        ico_path,
        format='ICO',
        sizes=[(s, s) for s in sizes],
        append_images=images[1:],
    )
    print(f"Icon written to {ico_path}")


if __name__ == '__main__':
    main()
