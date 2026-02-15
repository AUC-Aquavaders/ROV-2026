import cv2
import numpy as np
import pyrealsense2 as rs
pipeline = rs.pipeline()
config = rs.config()
config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)
pipeline.start(config)
sift = cv2.SIFT_create()
reference_images = {
    "Crab1": "carcinus-maenas.png",
}
ref_features = {}
for name, path in reference_images.items():
    img_ref = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    kp_ref, des_ref = sift.detectAndCompute(img_ref, None)
    ref_features[name] = (kp_ref, des_ref, img_ref.shape)

index_params = dict(algorithm=1, trees=5)
search_params = dict(checks=50)
flann = cv2.FlannBasedMatcher(index_params, search_params)

while True:
    frames = pipeline.wait_for_frames()
    color_frame = frames.get_color_frame()
    if not color_frame:
        continue
    frame = np.asanyarray(color_frame.get_data())

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    kp_target, des_target = sift.detectAndCompute(gray, None)

    if des_target is None:
        cv2.imshow("Crab Detection", frame)
        if cv2.waitKey(1) & 0xFF == 27:
            break
        continue
    for crab_name, (kp_ref, des_ref, (h_ref, w_ref)) in ref_features.items():
        matches = flann.knnMatch(des_ref, des_target, k=2)
        good = [m for m, n in matches if m.distance < 0.75 * n.distance]

        if len(good) > 10:  # threshold
            src_pts = np.float32([kp_ref[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
            dst_pts = np.float32([kp_target[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
            M, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)

            if M is not None:
                pts = np.float32([[0,0],[0,h_ref-1],[w_ref-1,h_ref-1],[w_ref-1,0]]).reshape(-1,1,2)
                dst = cv2.perspectiveTransform(pts, M)
                frame = cv2.polylines(frame, [np.int32(dst)], True, (0,255,0), 3, cv2.LINE_AA)
                x, y = np.int32(dst[0][0])
                cv2.putText(frame, crab_name, (x, y-10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2)

    cv2.imshow("Crab Detection", frame)
    if cv2.waitKey(1) & 0xFF == 27:  # ESC to quit
        break

pipeline.stop()
cv2.destroyAllWindows()
