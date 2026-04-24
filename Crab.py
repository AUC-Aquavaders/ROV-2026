import cv2
import numpy as np
import depthai as dai
import time
import os
import math

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

    use_oak_d = False
    video_queue = None
    pipeline = None

    try:
        pipeline = dai.Pipeline()
        cam = pipeline.create(dai.node.Camera)
        cam.build()
        preview_out = cam.requestOutput((640, 480), dai.ImgFrame.Type.BGR888p)

        # ✅ v3: attach a queue directly to the output
        queue = preview_out.createOutputQueue(maxSize=4, blocking=False)

        pipeline.start()
        video_queue = queue
        use_oak_d = True
        print("OAK-D connected. Starting stream...")
    except Exception as e:
        print(f"OAK-D not available: {e}")
        print("Falling back to webcam...")
        if pipeline:
            try:
                pipeline.stop()
            except:
                pass
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            print("Error: Could not open webcam")
            return
        video_queue = cap
        use_oak_d = False

    prev_time = time.time()
    proximity_threshold = 150

    try:
        while True:
            if use_oak_d:
                if not pipeline.isRunning():
                    break
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

                    used_mask = np.zeros(len(kp_target), dtype=bool)

                    for detection_attempt in range(5):
                        if len(good) < 6:
                            break

                        available_good = [m for m in good if not used_mask[m.trainIdx]]

                        if len(available_good) < 6:
                            break

                        src_pts = np.float32([kp_ref[m.queryIdx].pt for m in available_good]).reshape(-1, 1, 2)
                        dst_pts = np.float32([kp_target[m.trainIdx].pt for m in available_good]).reshape(-1, 1, 2)

                        M, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
                        if M is not None:
                            pts = np.float32([[0, 0], [0, h_ref - 1], [w_ref - 1, h_ref - 1], [w_ref - 1, 0]]).reshape(-1, 1, 2)
                            dst = cv2.perspectiveTransform(pts, M)

                            area = cv2.contourArea(np.int32(dst))
                            if 200 < area < 500000:
                                frame = cv2.polylines(frame, [np.int32(dst)], True, (0, 255, 0), 2, cv2.LINE_AA)

                                center_x = int(np.mean(dst[:, 0, 0]))
                                center_y = int(np.mean(dst[:, 0, 1]))
                                detected_centers.append((center_x, center_y))

                                cv2.circle(frame, (center_x, center_y), 5, (0, 0, 255), -1)

                                inlier_indices = np.where(mask.ravel())[0]
                                for idx in inlier_indices:
                                    used_mask[available_good[idx].trainIdx] = True

            beside_count = 0
            if len(detected_centers) > 1:
                for i in range(len(detected_centers)):
                    for j in range(i + 1, len(detected_centers)):
                        p1, p2 = detected_centers[i], detected_centers[j]
                        dist = math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)
                        if dist < proximity_threshold:
                            beside_count += 1
                            cv2.line(frame, p1, p2, (255, 255, 0), 2)

            curr_time = time.time()
            fps = 1 / (curr_time - prev_time)
            prev_time = curr_time

            cv2.putText(frame, f"FPS: {fps:.1f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            cv2.putText(frame, f"Total Crabs: {len(detected_centers)}", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.putText(frame, f"Pairs Beside Each Other: {beside_count}", (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)

            cv2.imshow("Crab Detection", frame)
            if cv2.waitKey(1) & 0xFF == 27:
                break

    finally:
        cv2.destroyAllWindows()
        if use_oak_d and pipeline:
            try:
                pipeline.stop()
            except:
                pass
        elif not use_oak_d and video_queue:
            video_queue.release()

if __name__ == "__main__":
    main()
    