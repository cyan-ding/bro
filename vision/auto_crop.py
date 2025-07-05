from ultralytics import YOLO
from PIL import Image
import os
from pathlib import Path


def main():
    # === CONFIGURATION ===
    model_path = "runs/detect/train11/weights/best.pt"    # path to your YOLOv8 model
    input_root = Path("unlabeled")       # root folder containing subfolders with images
    output_root = Path("vision/crops")   # where cropped icons go
    conf_threshold = 0.25                          # YOLO confidence threshold
    excluded_classes = {"text"}                   # class(es) to ignore

    # === SETUP ===
    model = YOLO(model_path)
    os.makedirs(output_root, exist_ok=True)

    # === FIND ALL IMAGE FILES IN SUBFOLDERS ===
    image_paths = list(input_root.rglob("*.[pj][pn]g"))  # .png and .jpg
    print(f"Found {len(image_paths)} images to process.")
    for img_path in image_paths:
        image = Image.open(img_path).convert("RGB")
        results = model.predict(source=str(img_path), conf=conf_threshold, save=False)

        boxes = results[0].boxes
        if boxes is None or boxes.xyxy is None or len(boxes.xyxy) == 0:
            continue

        boxes_xyxy = boxes.xyxy
        class_ids = boxes.cls

        for i in range(len(boxes_xyxy)):
            x1, y1, x2, y2 = map(int, boxes_xyxy[i].tolist())
            cls_id = int(class_ids[i])
            cls_name = model.names[cls_id]

            if cls_name in excluded_classes:
                continue

            crop = image.crop((x1, y1, x2, y2))

            # Build flattened filename: parentfolder_filename_crop_i.png
            parent_name = img_path.parent.name
            base_name = img_path.stem
            crop_filename = f"{parent_name}_{base_name}_crop_{i}.png"
            crop_path = output_root / crop_filename

            crop.save(crop_path)

    print("✅ Done. All valid UI crops saved.")

if __name__ == "__main__":
    main()
