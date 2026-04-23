
import cv2
import numpy as np
import depthai as dai
import time
import os
import math
from sklearn.cluster import DBSCAN

def main():
    sift = cv2.SIFT_create()
    script_dir = os.path.dirname(os.path.abspath(__file__))

    reference_images = {
        "Crab1": os.path.join(script_dir, "carcinus-maenas.jpeg"),
    }

    ref_features = {}
    for name, path in reference_images.items():
        img_ref = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        if img_ref is None:
            raise FileNotFoundError(f"Could not load reference image: {path}")
        kp_ref, des_ref = sift.detectAndCompute(img_ref, None)
        ref_features[name] = (kp_ref, des_ref, img_ref.shape)

    index_params = dict(algorithm=1, trees=5)
    search_params = dict(checks=50)
    flann = cv2.FlannBasedMatcher(index_params, search_params)

    # OAK-D setup with fallback to webcam
    device = None
    video_queue = None
    use_oak_d = False
    
    try:
        pipeline = dai.Pipeline()
        cam = pipeline.create(dai.node.ColorCamera)
        cam.setBoardSocket(dai.CameraBoardSocket.RGB)
        cam.setPreviewSize(640, 480)
        cam.setResolution(dai.ColorCameraProperties.SensorResolution.THE_1080_P)
        cam.setInterleaved(False)
        cam.setColorOrder(dai.ColorCameraProperties.ColorOrder.BGR)
        
        xout = pipeline.create(dai.node.XLinkOut)
        xout.setStreamName("preview")
        cam.preview.link(xout.input)
        
        device = dai.Device(pipeline)
        video_queue = device.getOutputQueue(name="preview", maxSize=4, blocking=False)
        use_oak_d = True
        print("OAK-D Pro connected. Starting stream...")
    except RuntimeError as e:
        print(f"OAK-D not available: {e}")
        print("Falling back to webcam...")
        video_queue = cv2.VideoCapture(0)
        if not video_queue.isOpened():
            print("Error: Could not open webcam")
            return

    prev_time = time.time()

    # --- CONFIGURATION FOR PROXIMITY ---
    proximity_threshold = 150  # Distance in pixels to consider crabs "beside each other"

    while True:
        if use_oak_d:
            in_video = video_queue.get()
            if in_video is None:
                continue
            frame = in_video.getCvFrame()
        else:
            ret, frame = video_queue.read()
            if not ret:
                break
        
        if frame is None:
            continue
        
        frame = cv2.resize(frame, (640, 480))
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        kp_target, des_target = sift.detectAndCompute(gray, None)

        detected_centers = []

        if des_target is not None and len(des_target) > 2:
            for crab_name, (kp_ref, des_ref, (h_ref, w_ref)) in ref_features.items():
                matches = flann.knnMatch(des_ref, des_target, k=2)
                good = [m for m, n in matches if m.distance < 0.75 * n.distance]

                # Mask to track which keypoints have been used
                used_mask = np.zeros(len(kp_target), dtype=bool)
                
                # Try to detect multiple instances
                for detection_attempt in range(5):  # Allow up to 5 crabs
                    if len(good) < 6:
                        break
                    
                    # Filter good matches to exclude used keypoints
                    available_good = [m for m in good if not used_mask[m.trainIdx]]
                    
                    if len(available_good) < 6:
                        break
                    
                    src_pts = np.float32([kp_ref[m.queryIdx].pt for m in available_good]).reshape(-1, 1, 2)
                    dst_pts = np.float32([kp_target[m.trainIdx].pt for m in available_good]).reshape(-1, 1, 2)

                    M, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
                    if M is not None:
                        pts = np.float32([[0, 0], [0, h_ref - 1], [w_ref - 1, h_ref - 1], [w_ref - 1, 0]]).reshape(-1, 1, 2)
                        dst = cv2.perspectiveTransform(pts, M)
                        
                        # Validate detection
                        area = cv2.contourArea(np.int32(dst))
                        if area > 200 and area < 500000:  # Reasonable area
                            # Draw detection box
                            frame = cv2.polylines(frame, [np.int32(dst)], True, (0, 255, 0), 2, cv2.LINE_AA)
                            
                            # Calculate Centroid
                            center_x = int(np.mean(dst[:, 0, 0]))
                            center_y = int(np.mean(dst[:, 0, 1]))
                            detected_centers.append((center_x, center_y))
                            
                            cv2.circle(frame, (center_x, center_y), 5, (0, 0, 255), -1)
                            
                            # Mark inlier keypoints as used
                            inlier_indices = np.where(mask.ravel())[0]
                            for idx in inlier_indices:
                                actual_idx = available_good[idx].trainIdx
                                used_mask[actual_idx] = True

        # --- LOGIC: DETECT CRABS BESIDE EACH OTHER ---
        beside_count = 0
        if len(detected_centers) > 1:
            for i in range(len(detected_centers)):
                for j in range(i + 1, len(detected_centers)):
                    p1 = detected_centers[i]
                    p2 = detected_centers[j]
                    
                    # Calculate Euclidean Distance
                    dist = math.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)
                    
                    if dist < proximity_threshold:
                        beside_count += 1
                        # Draw a line between crabs that are "beside" each other
                        cv2.line(frame, p1, p2, (255, 255, 0), 2)

        # UI Overlays
        curr_time = time.time()
        fps = 1 / (curr_time - prev_time)
        prev_time = curr_time

        cv2.putText(frame, f"Total Crabs: {len(detected_centers)}", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(frame, f"Pairs Beside Each Other: {beside_count}", (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
        cv2.putText(frame, f"FPS: {fps:.1f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        
        cv2.imshow("Crab Detection", frame)
        if cv2.waitKey(1) & 0xFF == 27:
            break

    cv2.destroyAllWindows()
    if not use_oak_d:
        video_queue.release()

if __name__ == "__main__":
    main()