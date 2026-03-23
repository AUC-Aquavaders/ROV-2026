"""
Standalone OAK-D Camera Test - Minimal FPS Benchmark
"""
import cv2
import depthai as dai
import numpy as np
import time

def main():
    print("Initializing OAK-D camera...")

    pipeline = dai.Pipeline()

    cam = pipeline.createColorCamera()
    cam.setResolution(dai.ColorCameraProperties.SensorResolution.THE_1080_P)
    cam.setIspScale(2, 3)
    cam.setPreviewSize(1280, 720)
    cam.setInterleaved(False)
    cam.setFps(30)
    cam.initialControl.setAutoExposureLimit(33000)

    mono_left = pipeline.createMonoCamera()
    mono_left.setBoardSocket(dai.CameraBoardSocket.CAM_B)
    mono_left.setResolution(dai.MonoCameraProperties.SensorResolution.THE_720_P)
    mono_left.setFps(30)
    mono_left.initialControl.setAutoExposureLimit(33000)

    mono_right = pipeline.createMonoCamera()
    mono_right.setBoardSocket(dai.CameraBoardSocket.CAM_C)
    mono_right.setResolution(dai.MonoCameraProperties.SensorResolution.THE_720_P)
    mono_right.setFps(30)
    mono_right.initialControl.setAutoExposureLimit(33000)

    stereo = pipeline.createStereoDepth()
    stereo.setDefaultProfilePreset(dai.node.StereoDepth.PresetMode.HIGH_DENSITY)
    stereo.setLeftRightCheck(True)
    stereo.initialConfig.setMedianFilter(dai.MedianFilter.KERNEL_7x7)

    mono_left.out.link(stereo.left)
    mono_right.out.link(stereo.right)

    xout_color = pipeline.createXLinkOut()
    xout_color.setStreamName("color")
    xout_color.input.setBlocking(False)
    cam.preview.link(xout_color.input)

    xout_depth = pipeline.createXLinkOut()
    xout_depth.setStreamName("depth")
    xout_depth.input.setBlocking(False)
    stereo.depth.link(xout_depth.input)

    device = dai.Device(pipeline)

    color_queue = device.getOutputQueue(name="color", maxSize=4, blocking=False)
    depth_queue = device.getOutputQueue(name="depth", maxSize=4, blocking=False)

    cv2.namedWindow("Color", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Color", 1280, 720)
    cv2.namedWindow("Depth", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Depth", 1280, 720)

    print("Camera initialized. Press 'Q' to quit.")

    last_time = time.time()
    fps = 0.0
    frame_count = 0

    while True:
        color_msg = color_queue.tryGet()
        depth_msg = depth_queue.tryGet()

        if color_msg:
            color_frame = color_msg.getCvFrame()
            frame_count += 1

            current_time = time.time()
            delta = current_time - last_time

            if delta >= 1.0:
                fps = frame_count / delta
                frame_count = 0
                last_time = current_time
                print(f"FPS: {fps:.1f}")

            cv2.putText(color_frame, f"FPS: {fps:.1f}", (20, 40),
                      cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
            cv2.imshow("Color", color_frame)

        if depth_msg:
            depth_frame = depth_msg.getFrame()
            depth_m = (depth_frame / 1000.0).astype(np.float32)
            depth_scaled = np.clip((depth_m - 0.2) / 2.8 * 255, 0, 255).astype(np.uint8)
            depth_color = cv2.applyColorMap(depth_scaled, cv2.COLORMAP_TURBO)
            depth_color = cv2.resize(depth_color, (1280, 720), interpolation=cv2.INTER_NEAREST)
            cv2.imshow("Depth", depth_color)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break

    device.close()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
