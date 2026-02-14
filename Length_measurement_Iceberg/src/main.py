"""
Main Application - Iceberg Tracking System
===========================================
Integrates all modules for ROV iceberg survey task.
"""

import cv2
import numpy as np
import logging
import sys
import argparse
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

# Import modules
from modules.vision_processor import VisionProcessor
from modules.depth_measurement import DepthMeasurement
from modules.survey_tracker import SurveyTracker
from modules.threat_calculator import ThreatCalculator, IcebergData
from modules.data_manager import DataManager
from modules.video_overlay import VideoOverlay


class IcebergTrackingSystem:
    """Main application integrating all modules."""
    
    def __init__(self, config_dir="./config"):
        """Initialize the tracking system."""
        self.config_dir = Path(config_dir)
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)
        
        # Initialize modules
        self.logger.info("Initializing Iceberg Tracking System...")
        
        try:
            self.vision = VisionProcessor(ocr_engine='easyocr', confidence_threshold=0.6)
            self.depth = DepthMeasurement()
            self.tracker = SurveyTracker()
            self.threat_calc = ThreatCalculator()
            self.data_mgr = DataManager()
            self.overlay = VideoOverlay()
            
            self.logger.info("All modules initialized successfully")
        
        except Exception as e:
            self.logger.error(f"Failed to initialize modules: {e}")
            raise
        
        # State
        self.mode = 'survey'  # 'survey', 'depth_measure', 'threat_calc'
        self.running = False
    
    def start_survey(self):
        """Start the survey mode."""
        self.logger.info("=== Starting Survey Mode ===")
        self.tracker.start_survey()
        self.mode = 'survey'
        self.running = True
        
        try:
            while self.running:
                # Get frames
                color_frame, depth_frame = self.depth.get_frames()
                
                if color_frame is None:
                    continue
                
                # Display frame with HUD
                survey_status = self.tracker.get_status()
                display_frame = self.overlay.draw_hud(color_frame, survey_status)
                display_frame = self.overlay.draw_crosshair(display_frame)
                
                # Show instructions
                if not survey_status['complete']:
                    missing = self.tracker.get_missing_numbers()
                    if missing:
                        msg = f"Looking for numbers: {missing}"
                        display_frame = self.overlay.draw_alert(display_frame, msg, 'info')
                else:
                    display_frame = self.overlay.draw_alert(display_frame, 
                                                           "Survey Complete!", 'success')
                
                # Display
                cv2.imshow('Iceberg Survey', display_frame)
                
                # Keyboard controls
                key = cv2.waitKey(1) & 0xFF
                
                if key == ord('q'):
                    self.running = False
                elif key == ord('d'):  # Detect number
                    self.detect_and_add_number(color_frame)
                elif key == ord('m'):  # Measure depth
                    self.measure_and_add_depth(depth_frame)
                elif key == ord('s'):  # Save survey
                    self.save_survey()
                elif key == ord('t'):  # Calculate threats
                    self.calculate_threats_interactive()
                elif key == ord('r'):  # Reset survey
                    self.tracker.reset()
                    self.logger.info("Survey reset")
        
        finally:
            self.cleanup()
    
    def detect_and_add_number(self, frame):
        """Detect number in current frame and add to survey."""
        self.logger.info("Detecting number...")
        
        # Detect numbers
        detections = self.vision.detect_numbers(frame)
        
        if not detections:
            self.logger.warning("No numbers detected")
            return
        
        # Use highest confidence detection
        best_detection = max(detections, key=lambda d: d['confidence'])
        number = best_detection['number']
        confidence = best_detection['confidence']
        
        self.logger.info(f"Detected: {number} (confidence: {confidence:.2%})")
        
        # Add to tracker
        result = self.tracker.add_corner_number(
            number=int(number),
            location=f"Detection at confidence {confidence:.2%}",
            confidence=confidence
        )
        
        if result['success']:
            self.logger.info(f"✓ {result['message']}")
        else:
            self.logger.warning(f"✗ {result['message']}")
    
    def measure_and_add_depth(self, depth_frame):
        """Measure depth and add to survey."""
        self.logger.info("Measuring keel depth...")
        
        # Measure depth at center
        result = self.depth.measure_keel_depth(depth_frame)
        
        if not result['valid']:
            self.logger.warning("Invalid depth measurement")
            return
        
        keel_depth = result['keel_depth']
        confidence = result['confidence']
        
        self.logger.info(f"Measured: {keel_depth:.3f}m (confidence: {confidence:.2%})")
        
        # Add to tracker
        track_result = self.tracker.add_keel_depth(keel_depth, confidence)
        
        if track_result['success']:
            self.logger.info(f"✓ {track_result['message']}")
    
    def save_survey(self):
        """Save current survey data."""
        survey_data = self.tracker.export_data()
        survey_id = self.data_mgr.save_survey(survey_data)
        
        # Export for judge
        report_path = self.data_mgr.export_for_judge(survey_id)
        
        self.logger.info(f"Survey saved! Report: {report_path}")
    
    def calculate_threats_interactive(self):
        """Interactive threat level calculation."""
        print("\n" + "="*60)
        print("THREAT LEVEL CALCULATOR")
        print("="*60)
        
        # Get iceberg data from user
        print("\nEnter iceberg information:")
        
        try:
            lat = float(input("Latitude (decimal degrees): "))
            lon = float(input("Longitude (decimal degrees): "))
            heading = float(input("Heading (degrees 0-360): "))
            
            # Use measured keel depth if available
            survey_status = self.tracker.get_status()
            if survey_status['keel_depth']:
                keel_depth = survey_status['keel_depth']
                print(f"Using measured keel depth: {keel_depth:.3f}m")
            else:
                keel_depth = float(input("Keel depth (meters): "))
            
            # Create iceberg data
            iceberg = IcebergData(
                latitude=lat,
                longitude=lon,
                heading=heading,
                keel_depth=keel_depth
            )
            
            # Calculate threats
            results = self.threat_calc.calculate_all_threats(iceberg)
            
            # Display report
            report = self.threat_calc.generate_report(results)
            print("\n" + report)
            
            # Save results
            self.data_mgr.save_threat_assessment(results)
            
            print("\n✓ Threat assessment saved!")
        
        except ValueError as e:
            print(f"✗ Invalid input: {e}")
        except Exception as e:
            print(f"✗ Error: {e}")
    
    def cleanup(self):
        """Cleanup resources."""
        self.logger.info("Cleaning up...")
        self.depth.stop()
        cv2.destroyAllWindows()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Iceberg Tracking System')
    parser.add_argument('--config', default='./config', help='Config directory')
    parser.add_argument('--mode', choices=['survey', 'test'], default='survey',
                       help='Operating mode')
    
    args = parser.parse_args()
    
    # Create and run system
    system = IcebergTrackingSystem(config_dir=args.config)
    
    print("\n" + "="*60)
    print("ICEBERG TRACKING SYSTEM - ROV COMPETITION")
    print("="*60)
    print("\nControls:")
    print("  D - Detect number in current view")
    print("  M - Measure keel depth")
    print("  S - Save survey")
    print("  T - Calculate threat levels")
    print("  R - Reset survey")
    print("  Q - Quit")
    print("="*60 + "\n")
    
    try:
        if args.mode == 'survey':
            system.start_survey()
        elif args.mode == 'test':
            print("Test mode - showing camera feed only")
            system.start_survey()
    
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\n\n✗ Error: {e}")
        logging.exception("Fatal error")
    finally:
        system.cleanup()


if __name__ == "__main__":
    main()
