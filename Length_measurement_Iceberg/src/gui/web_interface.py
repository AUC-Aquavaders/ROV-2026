"""
Web Interface for Iceberg Tracking System
==========================================
Flask-based web GUI for remote operation and monitoring.
Access from surface computer: http://192.168.2.2:5000

PRODUCTION VERSION - RealSense D415 Camera Required
"""

from flask import Flask, render_template, Response, jsonify, request
from flask_cors import CORS
import cv2
import sys
from pathlib import Path
import json
import logging
import time

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.vision_processor import VisionProcessor
from modules.depth_measurement import DepthMeasurement
from modules.survey_tracker import SurveyTracker
from modules.threat_calculator import ThreatCalculator, IcebergData
from modules.video_overlay import VideoOverlay
from modules.data_manager import DataManager

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize all modules (RealSense required)
try:
    depth_sensor = DepthMeasurement()
    vision = VisionProcessor()
    tracker = SurveyTracker()
    threat_calc = ThreatCalculator()
    overlay = VideoOverlay()
    logger.info("✓ All modules initialized successfully")
except Exception as e:
    logger.error(f"✗ Failed to initialize: {e}")
    logger.error("  Ensure RealSense D415 camera is connected")
    raise

# Global state
current_frame = None
survey_active = False


def generate_frames():
    """Generate video frames with HUD overlay."""
    global current_frame
    
    while True:
        try:
            # Get camera frames
            color_frame, depth_frame = depth_sensor.get_frames()
            
            if color_frame is None:
                time.sleep(0.01)
                continue
            
            # Get survey status
            survey_status = tracker.get_status()
            
            # Draw HUD overlay
            display_frame = overlay.draw_hud(color_frame, survey_status)
            display_frame = overlay.draw_crosshair(display_frame)
            
            # Store for other endpoints
            current_frame = display_frame
            
            # Encode frame as JPEG
            ret, buffer = cv2.imencode('.jpg', display_frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            frame = buffer.tobytes()
            
            # Yield frame in multipart format
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
        
        except Exception as e:
            logger.error(f"Error generating frame: {e}")
            time.sleep(0.1)
            continue


@app.route('/')
def index():
    """Main page."""
    return render_template('index.html')


@app.route('/video_feed')
def video_feed():
    """Video streaming route."""
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/api/detect_number', methods=['POST'])
def detect_number():
    """Detect number in current frame."""
    global current_frame
    
    if current_frame is None:
        return jsonify({'success': False, 'message': 'No frame available'})
    
    try:
        detections = vision.detect_numbers(current_frame)
        
        if not detections:
            return jsonify({'success': False, 'message': 'No numbers detected'})
        
        # Use best detection
        best = max(detections, key=lambda d: d['confidence'])
        number = int(best['number'])
        confidence = best['confidence']
        
        # Add to tracker
        result = tracker.add_corner_number(number, 'Web interface', confidence)
        
        return jsonify({
            'success': result['success'],
            'message': result['message'],
            'number': number,
            'confidence': confidence
        })
    
    except Exception as e:
        logger.error(f"Error in detect_number: {e}")
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/measure_depth', methods=['POST'])
def measure_depth():
    """Measure depth at current position."""
    try:
        _, depth_frame = depth_sensor.get_frames()
        
        if depth_frame is None:
            return jsonify({'success': False, 'message': 'No depth data available'})
        
        result = depth_sensor.measure_keel_depth(depth_frame)
        
        if not result['valid']:
            return jsonify({
                'success': False,
                'message': f"Invalid measurement: {result.get('error', 'Unknown error')}"
            })
        
        # Add to tracker
        tracker.add_keel_depth(result['keel_depth'], result['confidence'])
        
        return jsonify({
            'success': True,
            'depth': result['keel_depth'],
            'confidence': result['confidence'],
            'message': f"Depth: {result['keel_depth']:.3f}m (confidence: {result['confidence']:.1%})"
        })
    
    except Exception as e:
        logger.error(f"Error in measure_depth: {e}")
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/survey_status', methods=['GET'])
def survey_status():
    """Get current survey status."""
    try:
        status = tracker.get_status()
        return jsonify(status)
    except Exception as e:
        logger.error(f"Error in survey_status: {e}")
        return jsonify({'error': str(e)})


@app.route('/api/calculate_threats', methods=['POST'])
def calculate_threats():
    """Calculate threat levels for platforms and subsea assets."""
    try:
        data = request.json
        
        # Get keel depth from tracker if not provided
        survey_status = tracker.get_status()
        keel_depth = float(data.get('keel_depth', survey_status.get('keel_depth', 1.0)))
        
        iceberg = IcebergData(
            latitude=float(data['latitude']),
            longitude=float(data['longitude']),
            heading=float(data['heading']),
            keel_depth=keel_depth
        )
        
        results = threat_calc.calculate_all_threats(iceberg)
        
        return jsonify({
            'success': True,
            'results': results
        })
    
    except KeyError as e:
        return jsonify({'success': False, 'message': f'Missing required field: {e}'})
    except Exception as e:
        logger.error(f"Error in calculate_threats: {e}")
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/reset_survey', methods=['POST'])
def reset_survey():
    """Reset current survey."""
    try:
        tracker.reset()
        logger.info("Survey reset")
        return jsonify({'success': True, 'message': 'Survey reset successfully'})
    except Exception as e:
        logger.error(f"Error in reset_survey: {e}")
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/save_survey', methods=['POST'])
def save_survey():
    """Save current survey to database."""
    try:
        dm = DataManager()
        survey_data = tracker.export_data()
        survey_id = dm.save_survey(survey_data)
        
        logger.info(f"Survey saved with ID: {survey_id}")
        return jsonify({
            'success': True,
            'survey_id': survey_id,
            'message': f'Survey saved successfully (ID: {survey_id})'
        })
    
    except Exception as e:
        logger.error(f"Error in save_survey: {e}")
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/system_status', methods=['GET'])
def system_status():
    """Get system health status."""
    try:
        # Test camera connection
        color_frame, depth_frame = depth_sensor.get_frames()
        camera_ok = (color_frame is not None and depth_frame is not None)
        
        return jsonify({
            'camera': 'connected' if camera_ok else 'error',
            'vision': 'ready',
            'tracker': 'ready',
            'survey_active': survey_active
        })
    except Exception as e:
        return jsonify({
            'camera': 'error',
            'error': str(e)
        })


if __name__ == '__main__':
    logger.info("=" * 70)
    logger.info("ICEBERG TRACKING SYSTEM - WEB INTERFACE")
    logger.info("=" * 70)
    logger.info("")
    logger.info("✓ RealSense D415 camera required")
    logger.info("")
    logger.info("Access the interface at:")
    logger.info("  Local:        http://localhost:5000")
    logger.info("  ROV Network:  http://192.168.2.2:5000")
    logger.info("")
    logger.info("Controls:")
    logger.info("  • Detect Number - Press button or 'D' key")
    logger.info("  • Measure Depth - Press button or 'M' key")
    logger.info("  • Save Survey - Press button or 'S' key")
    logger.info("  • Reset Survey - Press button or 'R' key")
    logger.info("")
    logger.info("Press Ctrl+C to stop the server")
    logger.info("=" * 70)
    
    # Run server on all interfaces, port 5000
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
