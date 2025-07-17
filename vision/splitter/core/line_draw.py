from PIL import Image, ImageDraw

def draw_grid(image, rows, cols):
    img = image.copy()
    draw = ImageDraw.Draw(img)
    w, h = img.size
    for i in range(1, cols):
        x = i * w // cols
        draw.line([(x, 0), (x, h)], fill="red", width=2)
    for j in range(1, rows):
        y = j * h // rows
        draw.line([(0, y), (w, y)], fill="red", width=2)
    return img

def generate_split_guided_images(image: Image.Image):
    split_variants = []
    configs = [
        {"rows": 3, "cols": 3, "label": "3x3"},
        {"rows": 2, "cols": 2, "label": "2x2"},
        {"rows": 1, "cols": 2, "label": "1x2-vertical"},
        {"rows": 2, "cols": 1, "label": "2x1-horizontal"},
    ]
    
    for config in configs:
        img_with_grid = draw_grid(image, config["rows"], config["cols"])
        split_variants.append({
            "label": config["label"],
            "rows": config["rows"],
            "cols": config["cols"],
            "image": img_with_grid
        })

    return split_variants