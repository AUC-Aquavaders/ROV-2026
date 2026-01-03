import os
from ultralytics import YOLO
from pathlib import Path
import numpy as np

def test_all_dataset():
    print("=" * 70)
    print("Comprehensive Model Testing - All Dataset Images")
    print("=" * 70)
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    model_path = os.path.join(script_dir, 'runs', 'detect', 'green_crab_detector', 'weights', 'best.pt')
    if not os.path.exists(model_path):
        print(f"ERROR: Model not found at {model_path}")
        print("Please train the model first!")
        return
    
    print(f"\nLoading model from: {model_path}")
    model = YOLO(model_path)
    
    test_images_dir = os.path.join(script_dir, 'training_dataset', 'images')
    
    if not os.path.exists(test_images_dir):
        print(f"ERROR: Test images directory not found: {test_images_dir}")
        return
    
    # Get all images
    image_files = sorted(list(Path(test_images_dir).glob('*.jpg')))
    
    if not image_files:
        print(f"ERROR: No images found in {test_images_dir}")
        return
    
    print(f"\nTesting on {len(image_files)} images...")
    print("This will take a few minutes...\n")
    
    # Run prediction on all images
    results = model.predict(
        source=test_images_dir,
        save=False,             # Don't save all images (too many)
        conf=0.25,              # Confidence threshold
        verbose=False           # Reduce output
    )
    
    # Analyze results
    total_images = len(results)
    images_with_detections = 0
    total_detections = 0
    confidences = []
    no_detection_images = []
    multiple_detection_images = []
    
    for i, result in enumerate(results):
        boxes = result.boxes
        num_detections = len(boxes)
        
        if num_detections > 0:
            images_with_detections += 1
            total_detections += num_detections
            
            for box in boxes:
                conf = box.conf[0].item()
                confidences.append(conf)
            
            if num_detections > 1:
                multiple_detection_images.append((image_files[i].name, num_detections))
        else:
            no_detection_images.append(image_files[i].name)
    
    # Calculate statistics
    detection_rate = (images_with_detections / total_images) * 100
    avg_confidence = np.mean(confidences) if confidences else 0
    min_confidence = np.min(confidences) if confidences else 0
    max_confidence = np.max(confidences) if confidences else 0
    
    # Print comprehensive results
    print("\n" + "=" * 70)
    print("TEST RESULTS - COMPREHENSIVE ANALYSIS")
    print("=" * 70)
    
    print(f"\nDataset Statistics:")
    print(f"  Total images tested: {total_images}")
    print(f"  Images with detections: {images_with_detections}")
    print(f"  Images without detections: {len(no_detection_images)}")
    print(f"  Detection rate: {detection_rate:.2f}%")
    
    print(f"\nDetection Statistics:")
    print(f"  Total detections: {total_detections}")
    print(f"  Average detections per image: {total_detections/total_images:.2f}")
    print(f"  Images with multiple detections: {len(multiple_detection_images)}")
    
    print(f"\nConfidence Statistics:")
    print(f"  Average confidence: {avg_confidence:.4f}")
    print(f"  Minimum confidence: {min_confidence:.4f}")
    print(f"  Maximum confidence: {max_confidence:.4f}")
    
    # Show problematic cases
    if no_detection_images:
        print(f"\n⚠ WARNING: {len(no_detection_images)} images with NO detections:")
        for img_name in no_detection_images[:10]:  # Show first 10
            print(f"  - {img_name}")
        if len(no_detection_images) > 10:
            print(f"  ... and {len(no_detection_images) - 10} more")
    
    if multiple_detection_images:
        print(f"\n⚠ WARNING: {len(multiple_detection_images)} images with MULTIPLE detections:")
        for img_name, count in multiple_detection_images[:10]:  # Show first 10
            print(f"  - {img_name}: {count} detections")
        if len(multiple_detection_images) > 10:
            print(f"  ... and {len(multiple_detection_images) - 10} more")
    
    # Overall assessment
    print("\n" + "=" * 70)
    print("OVERALL ASSESSMENT:")
    print("=" * 70)
    
    if detection_rate >= 95 and avg_confidence >= 0.7:
        print("✓ EXCELLENT: Model is performing very well!")
    elif detection_rate >= 85 and avg_confidence >= 0.6:
        print("✓ GOOD: Model is performing well with minor issues.")
    elif detection_rate >= 70:
        print("⚠ FAIR: Model works but needs improvement.")
    else:
        print("✗ POOR: Model needs retraining or parameter adjustment.")
    
    print("\n" + "=" * 70)
    return results


def test_sample_images():
    """Test model on a few sample images"""
    print("=" * 70)
    print("Testing YOLOv8 Green Crab Detector")
    print("=" * 70)
    
    # Get script directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Load the best trained model
    model_path = os.path.join(script_dir, 'runs', 'detect', 'green_crab_detector', 'weights', 'best.pt')
    if not os.path.exists(model_path):
        print(f"ERROR: Model not found at {model_path}")
        print("Please train the model first!")
        return
    
    print(f"\nLoading model from: {model_path}")
    model = YOLO(model_path)
    
    # Test on some training images to verify the model works
    test_images_dir = os.path.join(script_dir, 'training_dataset', 'images')
    
    if not os.path.exists(test_images_dir):
        print(f"ERROR: Test images directory not found: {test_images_dir}")
        return
    
    # Get first 5 images from training dataset as test samples
    image_files = list(Path(test_images_dir).glob('*.jpg'))[:5]
    
    if not image_files:
        print(f"ERROR: No images found in {test_images_dir}")
        return
    
    print(f"\nTesting on {len(image_files)} sample images...")
    print("Images will be saved to: runs/detect/predict/\n")
    
    # Run prediction
    results = model.predict(
        source=image_files,
        save=True,              # Save annotated images
        conf=0.25,              # Confidence threshold
        save_txt=True,          # Save detection results as txt
        save_conf=True,         # Save confidences in txt
        project='runs/detect',
        name='predict',
        exist_ok=True
    )
    
    # Print results for each image
    print("\n" + "=" * 70)
    print("Detection Results:")
    print("=" * 70)
    
    for i, result in enumerate(results):
        img_name = image_files[i].name
        boxes = result.boxes
        
        print(f"\n{img_name}:")
        if len(boxes) > 0:
            for j, box in enumerate(boxes):
                conf = box.conf[0].item()
                cls = int(box.cls[0].item())
                class_name = result.names[cls]
                print(f"  Detection {j+1}: {class_name} (confidence: {conf:.4f})")
        else:
            print("  No detections")
    
    print("\n" + "=" * 70)
    print("Test Complete!")
    print("=" * 70)
    print(f"\nAnnotated images saved to: runs/detect/predict/")
    print("\nTo test on your own images:")
    print(f"  python test_model.py --source path/to/your/images")
    print("\nOr use YOLO CLI:")
    print(f"  yolo predict model={model_path} source=path/to/images")
    

if __name__ == '__main__':
    import sys
    
    # Check for --all flag for comprehensive testing
    if len(sys.argv) > 1 and sys.argv[1] == '--all':
        test_all_dataset()
    # Check if user provided custom source
    elif len(sys.argv) > 1 and sys.argv[1] == '--source' and len(sys.argv) > 2:
        source = sys.argv[2]
        print(f"Testing on custom source: {source}")
        
        script_dir = os.path.dirname(os.path.abspath(__file__))
        model_path = os.path.join(script_dir, 'runs', 'detect', 'green_crab_detector', 'weights', 'best.pt')
        
        if os.path.exists(model_path):
            model = YOLO(model_path)
            results = model.predict(
                source=source,
                save=True,
                conf=0.25,
                project='runs/detect',
                name='predict',
                exist_ok=True
            )
            print(f"\nResults saved to: runs/detect/predict/")
        else:
            print(f"ERROR: Model not found at {model_path}")
    else:
        test_sample_images()
