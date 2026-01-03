import os
os.environ['YOLO_VERBOSE'] = 'False'
from ultralytics import YOLO

def train_yolo():
    print("=" * 70)
    print("YOLOv8 Training - European Green Crab Detection")
    print("=" * 70)
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    dataset_path = os.path.join(script_dir, 'training_dataset', 'dataset.yaml')
    if not os.path.exists(dataset_path):
        print(f"ERROR: Dataset not found at {dataset_path}")
        print("Please generate the dataset first!")
        return
    
    # Create a YOLOv8 model
    # Using yolov8n (nano) for fastest training and inference
    model = YOLO('yolov8n.pt')  # Load pretrained weights
    
    print("\nStarting training...")
    print(f"Dataset: {dataset_path}")
    print("Model: YOLOv8n (nano)")
    print("This may take 30-60 minutes depending on your hardware...\n")
    
    results = model.train(
        data=dataset_path,
        epochs=100,
        imgsz=640,
        batch=16,
        name='green_crab_detector',
        patience=20,
        save=True,
        device=0,
        workers=8,
        project='runs/detect',
        exist_ok=True,
        pretrained=True,
        optimizer='auto',
        verbose=True,
        seed=42,
        deterministic=True,
        single_cls=True,
        rect=False,
        cos_lr=False,
        close_mosaic=10,
        amp=True,
        fraction=1.0,
        profile=False,
        freeze=None,
        lr0=0.01,
        lrf=0.01,
        momentum=0.937,
        weight_decay=0.0005,
        warmup_epochs=3.0,
        warmup_momentum=0.8,
        warmup_bias_lr=0.1,
        box=7.5,
        cls=0.5,
        dfl=1.5,
        pose=12.0,
        kobj=2.0,
        label_smoothing=0.0,
        nbs=64,
        hsv_h=0.015,
        hsv_s=0.7,
        hsv_v=0.4,
        degrees=0.0,
        translate=0.1,
        scale=0.5,
        shear=0.0,
        perspective=0.0,
        flipud=0.0,
        fliplr=0.5,
        mosaic=1.0,
        mixup=0.0,
        copy_paste=0.0
    )
    
    print("\n" + "=" * 70)
    print("Training Complete!")
    print("=" * 70)
    print(f"\nBest model saved to: runs/detect/green_crab_detector/weights/best.pt")
    print(f"Last model saved to: runs/detect/green_crab_detector/weights/last.pt")
    print(f"\nTraining results: runs/detect/green_crab_detector/")
    
    # Validate the model
    print("\nValidating model...")
    metrics = model.val()
    
    print(f"\nValidation Results:")
    print(f"  mAP50: {metrics.box.map50:.4f}")
    print(f"  mAP50-95: {metrics.box.map:.4f}")
    print(f"  Precision: {metrics.box.mp:.4f}")
    print(f"  Recall: {metrics.box.mr:.4f}")
    
    return model, results


if __name__ == '__main__':
    model, results = train_yolo()
    
    print("\n" + "=" * 70)
    print("Next Steps:")
    print("=" * 70)
    print("1. Check training metrics in: runs/detect/green_crab_detector/")
    print("2. Test on images: yolo predict model=runs/detect/green_crab_detector/weights/best.pt source=path/to/images")
    print("3. Export model: yolo export model=runs/detect/green_crab_detector/weights/best.pt format=onnx")
    print("=" * 70)
