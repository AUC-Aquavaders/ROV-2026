import sys
import os
import warnings
warnings.filterwarnings('ignore')
os.environ['OPENCV_IO_MAX_IMAGE_PIXELS'] = str(pow(2,40))
os.environ['PYTHONWARNINGS'] = 'ignore'

import io
old_stderr = sys.stderr
sys.stderr = io.StringIO()

try:
    import numpy as np
    import cv2
except Exception as e:
    sys.stderr = old_stderr
    print(f"ERROR: {e}")
    sys.exit(1)
finally:
    sys.stderr = old_stderr

import random
from pathlib import Path
from PIL import Image, ImageEnhance
import argparse


class SyntheticDatasetGenerator:
    def __init__(self, 
                 crab_image_path,
                 background_folder,
                 output_folder,
                 num_images=1000,
                 distractor_crabs_folder='crabs'):
        """
        Initialize the synthetic dataset generator.
        
        Args:
            crab_image_path: Path to transparent PNG of European green crab
            background_folder: Folder containing underwater/pool background images
            output_folder: Output directory for synthetic dataset
            num_images: Number of synthetic images to generate (500-2000 recommended)
            distractor_crabs_folder: Folder containing other crab species (not labeled)
        """
        self.crab_image_path = crab_image_path
        self.background_folder = background_folder
        self.output_folder = output_folder
        self.num_images = num_images
        
        # Load the green crab image with alpha channel
        self.crab_img = cv2.imread(crab_image_path, cv2.IMREAD_UNCHANGED)
        if self.crab_img is None:
            raise ValueError(f"Failed to load crab image from {crab_image_path}")
        
        # Load distractor crabs (other species - NOT to be labeled)
        self.distractor_crabs = []
        distractor_path = Path(distractor_crabs_folder)
        for img_file in distractor_path.glob('*.png'):
            if 'Bad_Crab' in img_file.name or 'bad' in img_file.name.lower():
                distractor_img = cv2.imread(str(img_file), cv2.IMREAD_UNCHANGED)
                if distractor_img is not None:
                    self.distractor_crabs.append(distractor_img)
                    print(f"Loaded distractor crab: {img_file.name}")
        
        print(f"Loaded {len(self.distractor_crabs)} distractor crab species (will NOT be labeled)")
        
        # Load all background images
        self.backgrounds = []
        bg_extensions = ['.jpg', '.jpeg', '.png', '.JPG', '.JPEG', '.PNG']
        for ext in bg_extensions:
            self.backgrounds.extend(list(Path(background_folder).glob(f'*{ext}')))
        
        if not self.backgrounds:
            raise ValueError(f"No background images found in {background_folder}")
        
        print(f"Loaded crab image: {crab_image_path}")
        print(f"Found {len(self.backgrounds)} background images")
        
        # Create output directories
        self.images_dir = Path(output_folder) / 'images'
        self.labels_dir = Path(output_folder) / 'labels'
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.labels_dir.mkdir(parents=True, exist_ok=True)
        
    def apply_underwater_color_shift(self, img):
        """Apply subtle blue/green color shift for underwater effect."""
        # Convert to float for processing
        img_float = img.astype(np.float32)
        
        # Increase blue and green channels slightly
        blue_shift = random.uniform(1.0, 1.15)
        green_shift = random.uniform(1.0, 1.1)
        red_shift = random.uniform(0.9, 1.0)
        
        if len(img_float.shape) == 3 and img_float.shape[2] >= 3:
            img_float[:, :, 0] *= blue_shift  # Blue
            img_float[:, :, 1] *= green_shift  # Green
            img_float[:, :, 2] *= red_shift    # Red
        
        return np.clip(img_float, 0, 255).astype(np.uint8)
    
    def apply_brightness_contrast(self, img, brightness_range=(-30, 30), 
                                  contrast_range=(0.8, 1.2)):
        """Apply random brightness and contrast adjustments."""
        brightness = random.randint(*brightness_range)
        contrast = random.uniform(*contrast_range)
        
        img = img.astype(np.float32)
        img = img * contrast + brightness
        return np.clip(img, 0, 255).astype(np.uint8)
    
    def apply_blur(self, img):
        """Apply random Gaussian or motion blur."""
        blur_type = random.choice(['gaussian', 'motion', 'none'])
        
        if blur_type == 'gaussian':
            kernel_size = random.choice([3, 5])
            return cv2.GaussianBlur(img, (kernel_size, kernel_size), 0)
        elif blur_type == 'motion':
            # Simple motion blur
            size = random.randint(3, 7)
            kernel = np.zeros((size, size))
            kernel[int((size-1)/2), :] = np.ones(size)
            kernel = kernel / size
            return cv2.filter2D(img, -1, kernel)
        else:
            return img
    
    def apply_noise(self, img):
        """Add subtle Gaussian noise."""
        if random.random() < 0.5:  # 50% chance to apply noise
            noise = np.random.normal(0, random.uniform(3, 8), img.shape)
            img = img.astype(np.float32) + noise
            return np.clip(img, 0, 255).astype(np.uint8)
        return img
    
    def rotate_image(self, image, angle):
        """Rotate image with alpha channel preservation."""
        height, width = image.shape[:2]
        center = (width // 2, height // 2)
        
        # Get rotation matrix
        matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
        
        # Calculate new bounding dimensions
        cos = np.abs(matrix[0, 0])
        sin = np.abs(matrix[0, 1])
        new_width = int((height * sin) + (width * cos))
        new_height = int((height * cos) + (width * sin))
        
        # Adjust rotation matrix for new center
        matrix[0, 2] += (new_width / 2) - center[0]
        matrix[1, 2] += (new_height / 2) - center[1]
        
        # Perform rotation
        rotated = cv2.warpAffine(image, matrix, (new_width, new_height),
                                 flags=cv2.INTER_LINEAR,
                                 borderMode=cv2.BORDER_CONSTANT,
                                 borderValue=(0, 0, 0, 0))
        
        return rotated
    
    def get_bbox_from_mask(self, alpha_channel):
        """Extract bounding box from alpha channel mask."""
        # Find all non-zero pixels
        coords = cv2.findNonZero(alpha_channel)
        if coords is None:
            return None
        
        x, y, w, h = cv2.boundingRect(coords)
        return (x, y, w, h)
    
    def composite_crab_on_background(self, background, crab_img, position, scale):
        """Composite crab onto background at specified position and scale."""
        # Resize crab
        new_width = int(crab_img.shape[1] * scale)
        new_height = int(crab_img.shape[0] * scale)
        resized_crab = cv2.resize(crab_img, (new_width, new_height), 
                                  interpolation=cv2.INTER_AREA)
        
        x, y = position
        
        # Ensure the crab fits within the background
        if x + new_width > background.shape[1]:
            new_width = background.shape[1] - x
        if y + new_height > background.shape[0]:
            new_height = background.shape[0] - y
        
        if new_width <= 0 or new_height <= 0:
            return background, None
        
        resized_crab = resized_crab[:new_height, :new_width]
        
        # Separate alpha channel
        if resized_crab.shape[2] == 4:
            alpha = resized_crab[:, :, 3] / 255.0
            crab_rgb = resized_crab[:, :, :3]
        else:
            # If no alpha, create a simple mask
            gray = cv2.cvtColor(resized_crab, cv2.COLOR_BGR2GRAY)
            _, alpha = cv2.threshold(gray, 10, 1, cv2.THRESH_BINARY)
            alpha = alpha.astype(np.float32)
            crab_rgb = resized_crab
        
        # Get the region of interest from background
        roi = background[y:y+new_height, x:x+new_width]
        
        # Blend crab onto background
        for c in range(3):
            roi[:, :, c] = (alpha * crab_rgb[:, :, c] + 
                           (1 - alpha) * roi[:, :, c])
        
        background[y:y+new_height, x:x+new_width] = roi
        
        # Get bounding box from alpha channel
        alpha_uint8 = (alpha * 255).astype(np.uint8)
        bbox = self.get_bbox_from_mask(alpha_uint8)
        
        if bbox:
            bbox_x, bbox_y, bbox_w, bbox_h = bbox
            # Adjust bbox to absolute coordinates
            abs_bbox = (x + bbox_x, y + bbox_y, bbox_w, bbox_h)
            return background, abs_bbox
        
        return background, None
    
    def generate_image_with_distractors(self, num_green_crabs=1, num_distractor_crabs=0, 
                                       image_size=(640, 640)):
        """
        Generate a single image with specified numbers of green and distractor crabs
        Returns: (image, list_of_yolo_labels)
        """
        # Load random background
        bg_path = random.choice(self.backgrounds)
        background = cv2.imread(str(bg_path))
        
        if background is None:
            return None, []
        
        background = cv2.resize(background, image_size)
        bg_height, bg_width = background.shape[:2]
        
        all_labels = []
        
        # First, add distractor crabs (NOT labeled)
        for _ in range(num_distractor_crabs):
            if self.distractor_crabs:
                distractor = random.choice(self.distractor_crabs).copy()
                distractor_angle = random.uniform(0, 360)
                distractor_rotated = self.rotate_image(distractor, distractor_angle)
                distractor_scale = random.uniform(0.1, 0.4)
                
                # Random position for distractor
                dist_w = int(distractor_rotated.shape[1] * distractor_scale)
                dist_h = int(distractor_rotated.shape[0] * distractor_scale)
                dist_max_x = max(0, bg_width - dist_w)
                dist_max_y = max(0, bg_height - dist_h)
                dist_x = random.randint(0, dist_max_x) if dist_max_x > 0 else 0
                dist_y = random.randint(0, dist_max_y) if dist_max_y > 0 else 0
                
                # Composite distractor (no bbox saved - not labeled!)
                background, _ = self.composite_crab_on_background(
                    background, distractor_rotated, (dist_x, dist_y), distractor_scale
                )
        
        # Now add green crabs (LABELED)
        for _ in range(num_green_crabs):
            # Random transformations for green crab
            angle = random.uniform(0, 360)
            rotated_crab = self.rotate_image(self.crab_img.copy(), angle)
            scale = random.uniform(0.1, 0.45)
            
            # Random position
            crab_w = int(rotated_crab.shape[1] * scale)
            crab_h = int(rotated_crab.shape[0] * scale)
            max_x = max(0, bg_width - crab_w)
            max_y = max(0, bg_height - crab_h)
            x = random.randint(0, max_x) if max_x > 0 else 0
            y = random.randint(0, max_y) if max_y > 0 else 0
            
            # Composite green crab
            background, bbox = self.composite_crab_on_background(
                background, rotated_crab, (x, y), scale
            )
            
            if bbox:
                # Convert to YOLO format
                yolo_bbox = self.bbox_to_yolo_format(bbox, bg_width, bg_height)
                all_labels.append(f"0 {yolo_bbox[0]} {yolo_bbox[1]} {yolo_bbox[2]} {yolo_bbox[3]}")
        
        # Apply post-processing
        background = self.apply_blur(background)
        background = self.apply_noise(background)
        
        return background, all_labels
    
    def save_image_and_label(self, image, labels, index, output_dir):
        """Save image and corresponding label file"""
        from pathlib import Path
        
        images_dir = Path(output_dir) / 'images'
        labels_dir = Path(output_dir) / 'labels'
        images_dir.mkdir(parents=True, exist_ok=True)
        labels_dir.mkdir(parents=True, exist_ok=True)
        
        # Handle both int and string index
        if isinstance(index, int):
            image_filename = f"synthetic_{index:06d}.jpg"
            label_filename = f"synthetic_{index:06d}.txt"
        else:
            image_filename = f"{index}.jpg"
            label_filename = f"{index}.txt"
        
        # Save image
        image_path = images_dir / image_filename
        cv2.imwrite(str(image_path), image)
        
        # Save label
        label_path = labels_dir / label_filename
        
        with open(label_path, 'w') as f:
            for label in labels:
                f.write(label + '\n')
    
    def apply_partial_occlusion(self, img, bbox):
        """Apply random partial occlusion to simulate real-world conditions."""
        if random.random() > 0.2:  # 20% chance of occlusion
            return img
        
        x, y, w, h = bbox
        
        # Create a random rectangular occlusion
        occlusion_type = random.choice(['corner', 'edge'])
        
        if occlusion_type == 'corner':
            # Occlude a corner
            occ_w = int(w * random.uniform(0.1, 0.3))
            occ_h = int(h * random.uniform(0.1, 0.3))
            corner = random.choice(['tl', 'tr', 'bl', 'br'])
            
            if corner == 'tl':
                cv2.rectangle(img, (x, y), (x + occ_w, y + occ_h), 
                            (0, 0, 0), -1)
            elif corner == 'tr':
                cv2.rectangle(img, (x + w - occ_w, y), (x + w, y + occ_h), 
                            (0, 0, 0), -1)
            elif corner == 'bl':
                cv2.rectangle(img, (x, y + h - occ_h), (x + occ_w, y + h), 
                            (0, 0, 0), -1)
            else:  # br
                cv2.rectangle(img, (x + w - occ_w, y + h - occ_h), 
                            (x + w, y + h), (0, 0, 0), -1)
        
        return img
    
    def bbox_to_yolo_format(self, bbox, img_width, img_height):
        """Convert bbox to YOLO format (normalized x_center, y_center, width, height)."""
        x, y, w, h = bbox
        
        x_center = (x + w / 2) / img_width
        y_center = (y + h / 2) / img_height
        width = w / img_width
        height = h / img_height
        
        # Clamp values to [0, 1]
        x_center = max(0, min(1, x_center))
        y_center = max(0, min(1, y_center))
        width = max(0, min(1, width))
        height = max(0, min(1, height))
        
        return x_center, y_center, width, height
    
    def generate_image(self, index):
        """Generate a single synthetic image with annotations."""
        # Load random background
        bg_path = random.choice(self.backgrounds)
        background = cv2.imread(str(bg_path))
        
        if background is None:
            print(f"Warning: Failed to load background {bg_path}")
            return False
        
        bg_height, bg_width = background.shape[:2]
        
        # 30% chance to add distractor crabs (other species - NOT labeled)
        if self.distractor_crabs and random.random() < 0.3:
            num_distractors = random.randint(1, 2)  # Add 1-2 distractor crabs
            for _ in range(num_distractors):
                distractor = random.choice(self.distractor_crabs).copy()
                distractor_angle = random.uniform(0, 360)
                distractor_rotated = self.rotate_image(distractor, distractor_angle)
                distractor_scale = random.uniform(0.08, 0.4)  # Slightly smaller
                
                # Random position for distractor
                dist_w = int(distractor_rotated.shape[1] * distractor_scale)
                dist_h = int(distractor_rotated.shape[0] * distractor_scale)
                dist_max_x = max(0, bg_width - dist_w)
                dist_max_y = max(0, bg_height - dist_h)
                dist_x = random.randint(0, dist_max_x) if dist_max_x > 0 else 0
                dist_y = random.randint(0, dist_max_y) if dist_max_y > 0 else 0
                
                # Composite distractor (no bbox saved - not labeled!)
                background, _ = self.composite_crab_on_background(
                    background, distractor_rotated, (dist_x, dist_y), distractor_scale
                )
        
        # Random scale (0.1 to 0.5 of background size)
        scale = random.uniform(0.1, 0.5)
        
        # Random rotation
        angle = random.uniform(0, 360)
        rotated_crab = self.rotate_image(self.crab_img.copy(), angle)
        
        # Apply augmentations to crab before compositing
        if rotated_crab.shape[2] == 4:
            # Apply color adjustments to RGB channels only
            rgb_crab = rotated_crab[:, :, :3]
            rgb_crab = self.apply_underwater_color_shift(rgb_crab)
            rgb_crab = self.apply_brightness_contrast(rgb_crab)
            rotated_crab[:, :, :3] = rgb_crab
        
        # Random position (ensure crab fits in image)
        crab_scaled_width = int(rotated_crab.shape[1] * scale)
        crab_scaled_height = int(rotated_crab.shape[0] * scale)
        
        max_x = max(0, bg_width - crab_scaled_width)
        max_y = max(0, bg_height - crab_scaled_height)
        
        position_x = random.randint(0, max_x) if max_x > 0 else 0
        position_y = random.randint(0, max_y) if max_y > 0 else 0
        
        # Composite crab onto background
        composite, bbox = self.composite_crab_on_background(
            background, rotated_crab, (position_x, position_y), scale
        )
        
        if bbox is None:
            print(f"Warning: Failed to generate bbox for image {index}")
            return False
        
        # Apply post-composite augmentations
        composite = self.apply_blur(composite)
        composite = self.apply_noise(composite)
        
        # Optional partial occlusion
        composite = self.apply_partial_occlusion(composite, bbox)
        
        # Save image
        image_filename = f"synthetic_{index:06d}.jpg"
        image_path = self.images_dir / image_filename
        cv2.imwrite(str(image_path), composite)
        
        # Convert bbox to YOLO format and save label
        yolo_bbox = self.bbox_to_yolo_format(bbox, bg_width, bg_height)
        label_filename = f"synthetic_{index:06d}.txt"
        label_path = self.labels_dir / label_filename
        
        # class_id = 0 for European green crab
        with open(label_path, 'w') as f:
            f.write(f"0 {yolo_bbox[0]:.6f} {yolo_bbox[1]:.6f} "
                   f"{yolo_bbox[2]:.6f} {yolo_bbox[3]:.6f}\n")
        
        return True
    
    def generate_dataset(self):
        """Generate the complete synthetic dataset."""
        print(f"\nGenerating {self.num_images} synthetic images...")
        print(f"Output directory: {self.output_folder}")
        
        success_count = 0
        for i in range(self.num_images):
            if self.generate_image(i):
                success_count += 1
            
            # Progress update
            if (i + 1) % 100 == 0:
                print(f"Progress: {i + 1}/{self.num_images} images generated "
                      f"({success_count} successful)")
        
        print(f"\nDataset generation complete!")
        print(f"Successfully generated: {success_count}/{self.num_images} images")
        print(f"Images saved to: {self.images_dir}")
        print(f"Labels saved to: {self.labels_dir}")
        
        # Create dataset.yaml for YOLOv8
        self.create_dataset_yaml()
    
    def create_dataset_yaml(self):
        """Create dataset.yaml file for YOLOv8 training."""
        yaml_content = f"""# YOLOv8 Dataset Configuration
# European Green Crab Detection - Synthetic Dataset

path: {self.output_folder}  # dataset root dir
train: images  # train images (relative to 'path')
val: images    # val images (relative to 'path')

# Classes
names:
  0: green_crab

# Number of classes
nc: 1

# Notes:
# - This is a synthetic dataset generated for European green crab detection
# - Other crab species visible in backgrounds are NOT labeled
# - Recommended: Split this dataset into train/val sets (80/20 or 90/10)
# - Consider adding real images to improve generalization
"""
        
        yaml_path = Path(self.output_folder) / 'dataset.yaml'
        with open(yaml_path, 'w') as f:
            f.write(yaml_content)
        
        print(f"Dataset config saved to: {yaml_path}")
        print("\nNext steps:")
        print("1. Review generated images in the 'images' folder")
        print("2. Split dataset into train/val sets if needed")
        print("3. Train YOLOv8: yolo train model=yolov8n.pt data=dataset.yaml epochs=100")


def main():
    print("=" * 70, flush=True)
    print("Synthetic Dataset Generator - European Green Crab Detection", flush=True)
    print("=" * 70, flush=True)
    
    try:
        parser = argparse.ArgumentParser(
            description='Generate synthetic dataset for YOLOv8 green crab detection'
        )
    except Exception as e:
        print(f"Error in main: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return
    parser.add_argument('--crab', type=str, 
                       default='crabs/European_crab.png',
                       help='Path to European green crab PNG (transparent)')
    parser.add_argument('--backgrounds', type=str,
                       default='backgrounds',
                       help='Path to folder containing background images')
    parser.add_argument('--output', type=str,
                       default='synthetic_dataset',
                       help='Output folder for synthetic dataset')
    parser.add_argument('--num_images', type=int,
                       default=1000,
                       help='Number of synthetic images to generate (500-2000)')
    
    args = parser.parse_args()
    
    # Validate inputs
    if not os.path.exists(args.crab):
        print(f"Error: Crab image not found: {args.crab}")
        return
    
    if not os.path.exists(args.backgrounds):
        print(f"Error: Backgrounds folder not found: {args.backgrounds}")
        return
    
    # Generate dataset
    generator = SyntheticDatasetGenerator(
        crab_image_path=args.crab,
        background_folder=args.backgrounds,
        output_folder=args.output,
        num_images=args.num_images
    )
    
    generator.generate_dataset()


if __name__ == '__main__':
    main()
