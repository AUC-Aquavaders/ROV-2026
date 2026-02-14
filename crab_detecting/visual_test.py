import os
from ultralytics import YOLO
from pathlib import Path
import cv2
import numpy as np

def run_visual_tests():
    print("=" * 70)
    print("Visual Model Testing - Labeled Images with Confidence %")
    print("=" * 70)
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    model_path = os.path.join(script_dir, 'runs', 'detect', 'green_crab_detector', 'weights', 'best.pt')
    
    if not os.path.exists(model_path):
        print(f"ERROR: Model not found at {model_path}")
        return
    
    print(f"\nLoading model: {model_path}\n")
    model = YOLO(model_path)
    
    test_dir = Path(script_dir) / 'training_dataset' / 'images'
    all_images = sorted(list(test_dir.glob('*.jpg')))
    test_images = all_images[500:700]
    
    print(f"Running predictions on {len(test_images)} images...")
    print("Saving labeled images with bounding boxes and confidence %...\n")
    
    results = model.predict(
        source=test_images,
        conf=0.25,
        iou=0.45,
        device=0,
        save=True,
        save_txt=True,
        save_conf=True,
        show_labels=True,
        show_conf=True,
        line_width=2,
        project='runs/detect',
        name='visual_test',
        exist_ok=True
    )
    
    stats = {
        'total': len(results),
        'with_detections': 0,
        'no_detections': 0,
        'avg_confidence': [],
        'detection_counts': {}
    }
    
    print("\nDetailed Results:")
    print("-" * 70)
    
    for idx, (img_path, result) in enumerate(zip(test_images, results)):
        num_detections = len(result.boxes)
        
        if num_detections > 0:
            stats['with_detections'] += 1
            stats['detection_counts'][num_detections] = stats['detection_counts'].get(num_detections, 0) + 1
            
            confidences = result.boxes.conf.cpu().numpy()
            stats['avg_confidence'].extend(confidences.tolist())
            
            conf_str = ', '.join([f'{c*100:.1f}%' for c in confidences])
            print(f"{idx+1}. {img_path.name}: {num_detections} crabs [{conf_str}]")
        else:
            stats['no_detections'] += 1
    
    avg_conf = np.mean(stats['avg_confidence']) * 100 if stats['avg_confidence'] else 0
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total images tested: {stats['total']}")
    print(f"Images with detections: {stats['with_detections']} ({stats['with_detections']/stats['total']*100:.1f}%)")
    print(f"Images without detections: {stats['no_detections']} ({stats['no_detections']/stats['total']*100:.1f}%)")
    print(f"Average confidence: {avg_conf:.1f}%")
    
    print("\nDetection distribution:")
    for count in sorted(stats['detection_counts'].keys()):
        num = stats['detection_counts'][count]
        print(f"  {count} crab(s): {num} images ({num/stats['total']*100:.1f}%)")
    
    print("\n" + "=" * 70)
    print("Labeled images saved to: runs/detect/visual_test/")
    print("Each image shows bounding boxes with confidence percentages")
    print("=" * 70)

if __name__ == '__main__':
    run_visual_tests()
