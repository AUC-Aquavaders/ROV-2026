import cv2
import depthai as dai
import time
import numpy as np
from collections import deque

class CrabDetector:
    def __init__(self):
        # Adjust these HSV ranges based on your actual crab color
        self.color_ranges = [
            # Brown/red crabs
            (np.array([0, 50, 50]), np.array([20, 255, 255])),
            # Green crabs  
            (np.array([30, 40, 40]), np.array([70, 255, 255])),
            # Dark crabs
            (np.array([0, 0, 0]), np.array([180, 255, 60]))
        ]
        
        self.min_crab_area = 800
        self.max_crab_area = 15000
        self.proximity_threshold = 100
        
        # For temporal smoothing
        self.detection_history = deque(maxlen=5)
        
    def detect_crabs(self, frame):
        """Detect crabs using color segmentation and contour analysis"""
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        
        # Combine masks from different color ranges
        combined_mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
        for lower, upper in self.color_ranges:
            mask = cv2.inRange(hsv, lower, upper)
            combined_mask = cv2.bitwise_or(combined_mask, mask)
        
        # Clean up mask
        kernel = np.ones((5,5), np.uint8)
        combined_mask = cv2.morphologyEx(combined_mask, cv2.MORPH_OPEN, kernel)
        combined_mask = cv2.morphologyEx(combined_mask, cv2.MORPH_CLOSE, kernel)
        
        # Find contours
        contours, _ = cv2.findContours(combined_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        crabs = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if self.min_crab_area < area < self.max_crab_area:
                # Get bounding rectangle
                x, y, w, h = cv2.boundingRect(contour)
                
                # Filter by shape (crabs are roughly circular/oval)
                aspect_ratio = w / h
                if 0.5 < aspect_ratio < 2.0:
                    # Calculate circularity
                    perimeter = cv2.arcLength(contour, True)
                    if perimeter > 0:
                        circularity = 4 * np.pi * area / (perimeter * perimeter)
                        # Crabs are not perfectly circular, so accept a range
                        if circularity > 0.3:
                            crabs.append({
                                'x': x, 'y': y, 'w': w, 'h': h,
                                'area': area,
                                'center': (int(x + w/2), int(y + h/2))
                            })
        
        # Merge overlapping detections
        crabs = self.merge_overlapping(crabs)
        
        # Apply temporal smoothing
        self.detection_history.append(crabs)
        crabs = self.smooth_detections()
        
        return crabs
    
    def merge_overlapping(self, crabs, overlap_threshold=0.3):
        """Merge overlapping bounding boxes"""
        if not crabs:
            return []
        
        merged = []
        used = [False] * len(crabs)
        
        for i, crab1 in enumerate(crabs):
            if used[i]:
                continue
            
            current = crab1.copy()
            for j, crab2 in enumerate(crabs):
                if i != j and not used[j]:
                    # Calculate IoU
                    x1 = max(current['x'], crab2['x'])
                    y1 = max(current['y'], crab2['y'])
                    x2 = min(current['x'] + current['w'], crab2['x'] + crab2['w'])
                    y2 = min(current['y'] + current['h'], crab2['y'] + crab2['h'])
                    
                    if x1 < x2 and y1 < y2:
                        intersection = (x2 - x1) * (y2 - y1)
                        area1 = current['w'] * current['h']
                        area2 = crab2['w'] * crab2['h']
                        iou = intersection / (area1 + area2 - intersection)
                        
                        if iou > overlap_threshold:
                            # Merge boxes
                            current['x'] = min(current['x'], crab2['x'])
                            current['y'] = min(current['y'], crab2['y'])
                            current['w'] = max(current['x'] + current['w'], crab2['x'] + crab2['w']) - current['x']
                            current['h'] = max(current['y'] + current['h'], crab2['y'] + crab2['h']) - current['y']
                            used[j] = True
            
            merged.append(current)
            used[i] = True
        
        return merged
    
    def smooth_detections(self):
        """Apply temporal smoothing to reduce false positives"""
        if len(self.detection_history) < 3:
            return self.detection_history[-1] if self.detection_history else []
        
        # Return detections that appear consistently
        # This is simplified - for production, use tracking
        return self.detection_history[-1]
    
    def find_adjacent_crabs(self, crabs):
        """Find crabs that are beside each other"""
        adjacent_pairs = []
        groups = []
        
        for i, crab1 in enumerate(crabs):
            for j, crab2 in enumerate(crabs):
                if i >= j:
                    continue
                
                # Calculate distance between centers
                dx = crab1['center'][0] - crab2['center'][0]
                dy = crab1['center'][1] - crab2['center'][1]
                distance = np.sqrt(dx**2 + dy**2)
                
                # Check if horizontally aligned and close
                horizontal_alignment = abs(dy) < crab1['h'] * 0.5
                side_by_side = (dx > 0 and dx < self.proximity_threshold) or \
                              (distance < self.proximity_threshold)
                
                if side_by_side and horizontal_alignment:
                    adjacent_pairs.append((i, j))
                    
                    # Group them
                    found = False
                    for group in groups:
                        if i in group or j in group:
                            group.add(i)
                            group.add(j)
                            found = True
                            break
                    if not found:
                        groups.append({i, j})
        
        return adjacent_pairs, groups
    
    def draw_results(self, frame, crabs, adjacent_pairs, groups):
        """Draw all detection results on frame"""
        # Draw bounding boxes
        for idx, crab in enumerate(crabs):
            color = (0, 255, 0)  # Green for solitary crabs
            for group in groups:
                if idx in group:
                    color = (0, 255, 255)  # Yellow for crabs in groups
                    break
            
            cv2.rectangle(frame, (crab['x'], crab['y']), 
                         (crab['x'] + crab['w'], crab['y'] + crab['h']), color, 2)
            cv2.circle(frame, crab['center'], 4, (0, 0, 255), -1)
            cv2.putText(frame, f"Crab {idx}", (crab['x'], crab['y'] - 5),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
        
        # Draw connections between adjacent crabs
        for pair in adjacent_pairs:
            p1 = crabs[pair[0]]['center']
            p2 = crabs[pair[1]]['center']
            cv2.line(frame, p1, p2, (255, 0, 0), 2)
        
        # Draw info panel
        overlay = frame.copy()
        cv2.rectangle(overlay, (5, 5), (300, 130), (0, 0, 0), -1)
        frame = cv2.addWeighted(overlay, 0.7, frame, 0.3, 0)
        
        total_crabs = len(crabs)
        total_pairs = len(adjacent_pairs)
        total_groups = len(groups)
        
        cv2.putText(frame, f"Total Crabs: {total_crabs}", (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        cv2.putText(frame, f"Groups: {total_groups}", (10, 55),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 2)
        cv2.putText(frame, f"Adjacent Pairs: {total_pairs}", (10, 75),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 200, 0), 2)
        
        return frame

def main():
    # Create pipeline
    pipeline = dai.Pipeline()
    
    # Define source - Camera node (v3 API)
    cam = pipeline.create(dai.node.Camera)
    cam.setBoardSocket(dai.CameraBoardSocket.CAM_A)
    cam.setResolution(dai.ColorCameraProperties.SensorResolution.THE_1080_P)
    cam.setFps(30)
    
    # Request output
    video_out = cam.requestOutput((640, 480), type=dai.ImgFrame.Type.BGR888p)
    
    # Start pipeline
    pipeline.start()
    
    # Get output queue
    video_queue = video_out.createOutputQueue()
    
    detector = CrabDetector()
    
    print("Crab Detection Started")
    print("Controls:")
    print("  ESC - Quit")
    print("  +/- - Adjust proximity threshold")
    print("  r   - Reset detection history")
    
    prev_time = time.time()
    frame_count = 0
    
    try:
        while pipeline.isRunning():
            # Get frame
            in_video = video_queue.get()
            frame = in_video.getCvFrame()
            
            # Detect crabs
            crabs = detector.detect_crabs(frame)
            
            # Find adjacent crabs
            adjacent_pairs, groups = detector.find_adjacent_crabs(crabs)
            
            # Draw results
            frame = detector.draw_results(frame, crabs, adjacent_pairs, groups)
            
            # FPS counter
            curr_time = time.time()
            fps = 1 / (curr_time - prev_time) if (curr_time - prev_time) > 0 else 0
            prev_time = curr_time
            cv2.putText(frame, f"FPS: {fps:.1f}", (10, 105),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            
            cv2.imshow("Crab Detection", frame)
            
            key = cv2.waitKey(1) & 0xFF
            if key == 27:  # ESC
                break
            elif key == ord('+') or key == ord('='):
                detector.proximity_threshold += 10
                print(f"Proximity threshold: {detector.proximity_threshold}")
            elif key == ord('-') or key == ord('_'):
                detector.proximity_threshold = max(20, detector.proximity_threshold - 10)
                print(f"Proximity threshold: {detector.proximity_threshold}")
            elif key == ord('r'):
                detector.detection_history.clear()
                print("Detection history reset")
            
            frame_count += 1
            
    except KeyboardInterrupt:
        print("\nStopping...")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        cv2.destroyAllWindows()
        pipeline.stop()
        print("Pipeline stopped")

if __name__ == "__main__":
    main()