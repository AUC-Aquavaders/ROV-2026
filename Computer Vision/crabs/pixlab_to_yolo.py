import json
import os

input_folder = "json"      # folder with all PixLab JSONs
output_folder = "labels"   # where YOLO .txt files will be saved
image_ext = ".jpg"         # extension of your images

os.makedirs(output_folder, exist_ok=True)

# class mapping
classes = {"Crab": 0}

for file in os.listdir(input_folder):
    if not file.endswith(".json"):
        continue

    json_path = os.path.join(input_folder, file)
    with open(json_path, "r") as f:
        annotations = json.load(f)

    # derive image filename from JSON filename
    img_name = os.path.splitext(file)[0] + image_ext

    # TODO: you must provide image width/height manually or via PIL
    from PIL import Image
    img_path = os.path.join("images", img_name)  # folder with your images
    if not os.path.exists(img_path):
        print(f"⚠ Image {img_name} not found, skipping")
        continue

    with Image.open(img_path) as img:
        img_w, img_h = img.size

    label_filename = os.path.splitext(img_name)[0] + ".txt"
    label_path = os.path.join(output_folder, label_filename)

    with open(label_path, "w") as out:
        for ann in annotations:
            rect = ann["rectMask"]
            cls = classes[ann["labels"]["labelName"]]

            x_min = rect["xMin"]
            y_min = rect["yMin"]
            w = rect["width"]
            h = rect["height"]

            # convert to YOLO format
            x_center = (x_min + w / 2) / img_w
            y_center = (y_min + h / 2) / img_h
            w_norm = w / img_w
            h_norm = h / img_h

            out.write(f"{cls} {x_center} {y_center} {w_norm} {h_norm}\n")

print("✅ DONE! YOLO labels exported to 'labels/'")
