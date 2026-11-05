"""Generate assets/icon.ico with the SumarteRed brand icon.

Orange rounded square with three diagonal white stripes.
Run before building:
    python generate_icon.py
"""

import os
from PIL import Image, ImageDraw


def make_icon_image(size: int) -> Image.Image:
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    orange = (255, 107, 53, 255)
    white = (255, 255, 255, 255)

    # Rounded-square background
    radius = max(2, size // 6)
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=orange)

    # Three diagonal white stripes (bottom-left → top-right, 45°)
    # Stripe width proportional to icon size
    sw = max(1, size // 8)       # stripe width
    gap = max(2, size // 5)      # gap between stripe centres

    # Draw stripes as thin rotated rectangles using polygon
    # Each stripe is a parallelogram: bottom-left to top-right diagonal
    offsets = [-gap, 0, gap]
    for off in offsets:
        # Stripe runs from (x0, size) to (size, y0) shifted by offset
        x0 = off
        # Four corners of the stripe parallelogram
        pts = [
            (x0 - sw, size),
            (x0 + sw, size),
            (x0 + size + sw, 0),
            (x0 + size - sw, 0),
        ]
        # Clip by redrawing the rounded square on a mask
        draw.polygon(pts, fill=white)

    # Re-apply rounded-square mask so stripes don't bleed outside
    mask = Image.new('L', (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)

    result = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    result.paste(img, mask=mask)
    return result


def main() -> None:
    os.makedirs('assets', exist_ok=True)
    ico_path = os.path.join('assets', 'icon.ico')

    sizes = [256, 128, 64, 48, 32, 16]  # largest first
    images = [make_icon_image(s) for s in sizes]

    # Pillow's ICO writer needs all images passed as append_images
    # and the first image drives the file; use largest as primary.
    images[0].save(
        ico_path,
        format='ICO',
        append_images=images[1:],
    )

    file_size = os.path.getsize(ico_path)
    print(f"Icon written to {ico_path} ({file_size:,} bytes)")
    if file_size < 1000:
        raise RuntimeError(f"ICO too small ({file_size} bytes) — save failed")


if __name__ == '__main__':
    main()
