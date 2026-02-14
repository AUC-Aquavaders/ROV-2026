"""
Survey Tracker Module
=====================
Tracks progress of iceberg survey - 5 corner numbers + keel depth.
Validates number sequences and manages survey completion status.
"""

import logging
from typing import List, Dict, Optional, Set
from datetime import datetime
import json


class SurveyTracker:
    """Manages iceberg survey progress and validation."""
    
    def __init__(self):
        """Initialize survey tracker."""
        self.survey_data = {
            'numbers_found': [],  # List of {'number': int, 'location': str, 'timestamp': str}
            'keel_depth': None,   # {'depth': float, 'timestamp': str, 'confidence': float}
            'keel_number': None,  # Number found on keel
            'sequence_type': None,  # '0-4' or '5-9'
            'complete': False,
            'started_at': None,
            'completed_at': None
        }
        
        logging.info("SurveyTracker initialized")
    
    def start_survey(self):
        """Start a new survey."""
        self.survey_data = {
            'numbers_found': [],
            'keel_depth': None,
            'keel_number': None,
            'sequence_type': None,
            'complete': False,
            'started_at': datetime.now().isoformat(),
            'completed_at': None
        }
        logging.info("Survey started")
    
    def add_corner_number(self, number: int, location: str = 'unknown', 
                         confidence: float = 1.0) -> Dict:
        """
        Add a detected corner number to survey.
        
        Args:
            number: Detected number (0-9)
            location: Description of corner location
            confidence: Detection confidence (0-1)
            
        Returns:
            Status dictionary with success and message
        """
        # Validate number
        if not isinstance(number, int) or number < 0 or number > 9:
            return {
                'success': False,
                'message': f'Invalid number: {number}. Must be 0-9.'
            }
        
        # Check if already detected
        detected_numbers = [n['number'] for n in self.survey_data['numbers_found']]
        if number in detected_numbers:
            return {
                'success': False,
                'message': f'Number {number} already surveyed.'
            }
        
        # Check if we already have 5 numbers
        if len(self.survey_data['numbers_found']) >= 5:
            return {
                'success': False,
                'message': 'Already surveyed 5 corners.'
            }
        
        # Add number
        self.survey_data['numbers_found'].append({
            'number': number,
            'location': location,
            'timestamp': datetime.now().isoformat(),
            'confidence': confidence
        })
        
        # Check if sequence is valid
        if len(self.survey_data['numbers_found']) == 5:
            self._validate_sequence()
        
        logging.info(f"Corner number added: {number} at {location}")
        
        return {
            'success': True,
            'message': f'Number {number} added. Progress: {self.get_progress()}'
        }
    
    def add_keel_depth(self, depth: float, confidence: float = 1.0) -> Dict:
        """
        Add keel depth measurement.
        
        Args:
            depth: Measured keel depth in meters
            confidence: Measurement confidence (0-1)
            
        Returns:
            Status dictionary
        """
        # Validate depth (0.5m - 1.5m expected range)
        if depth < 0.3 or depth > 2.0:
            logging.warning(f"Depth {depth}m outside expected range (0.5-1.5m)")
        
        self.survey_data['keel_depth'] = {
            'depth': depth,
            'timestamp': datetime.now().isoformat(),
            'confidence': confidence
        }
        
        logging.info(f"Keel depth added: {depth:.3f}m (confidence: {confidence:.2f})")
        
        # Check if survey is complete
        self._check_completion()
        
        return {
            'success': True,
            'message': f'Keel depth recorded: {depth:.3f}m'
        }
    
    def add_keel_number(self, number: int, confidence: float = 1.0) -> Dict:
        """
        Add the number found on the keel (sixth number).
        
        Args:
            number: Detected number on keel (0-9)
            confidence: Detection confidence
            
        Returns:
            Status dictionary
        """
        if not isinstance(number, int) or number < 0 or number > 9:
            return {
                'success': False,
                'message': f'Invalid keel number: {number}'
            }
        
        self.survey_data['keel_number'] = {
            'number': number,
            'timestamp': datetime.now().isoformat(),
            'confidence': confidence
        }
        
        logging.info(f"Keel number added: {number}")
        
        return {
            'success': True,
            'message': f'Keel number recorded: {number}'
        }
    
    def _validate_sequence(self):
        """Validate that the 5 corner numbers form valid sequence (0-4 or 5-9)."""
        numbers = [n['number'] for n in self.survey_data['numbers_found']]
        numbers_set = set(numbers)
        
        if numbers_set == {0, 1, 2, 3, 4}:
            self.survey_data['sequence_type'] = '0-4'
            logging.info("Valid sequence detected: 0-4")
        elif numbers_set == {5, 6, 7, 8, 9}:
            self.survey_data['sequence_type'] = '5-9'
            logging.info("Valid sequence detected: 5-9")
        else:
            self.survey_data['sequence_type'] = 'invalid'
            logging.warning(f"Invalid sequence: {sorted(numbers)}")
    
    def _check_completion(self):
        """Check if survey is complete."""
        corners_complete = len(self.survey_data['numbers_found']) == 5
        keel_measured = self.survey_data['keel_depth'] is not None
        sequence_valid = self.survey_data['sequence_type'] in ['0-4', '5-9']
        
        if corners_complete and keel_measured and sequence_valid:
            self.survey_data['complete'] = True
            self.survey_data['completed_at'] = datetime.now().isoformat()
            logging.info("Survey COMPLETE!")
    
    def get_progress(self) -> str:
        """
        Get survey progress as string.
        
        Returns:
            Progress string like "3/5 corners, keel: measured"
        """
        corners = len(self.survey_data['numbers_found'])
        keel = "measured" if self.survey_data['keel_depth'] else "not measured"
        
        return f"{corners}/5 corners, keel: {keel}"
    
    def get_status(self) -> Dict:
        """
        Get detailed survey status.
        
        Returns:
            Dictionary with all survey information
        """
        return {
            'progress': self.get_progress(),
            'corners_found': len(self.survey_data['numbers_found']),
            'corners_needed': 5,
            'numbers': sorted([n['number'] for n in self.survey_data['numbers_found']]),
            'sequence_type': self.survey_data['sequence_type'],
            'sequence_valid': self.survey_data['sequence_type'] in ['0-4', '5-9'],
            'keel_depth': self.survey_data['keel_depth']['depth'] if self.survey_data['keel_depth'] else None,
            'keel_confidence': self.survey_data['keel_depth']['confidence'] if self.survey_data['keel_depth'] else None,
            'complete': self.survey_data['complete'],
            'points_earned': self.calculate_points()
        }
    
    def calculate_points(self) -> int:
        """
        Calculate points earned based on current survey progress.
        
        Scoring:
        - 10 points: All 5 corners surveyed (valid sequence)
        - 5 points: 1-4 corners surveyed
        - 10 points: Keel depth within ±5cm
        - 5 points: Keel depth within ±5.01-10cm
        
        Returns:
            Total points (0-20)
        """
        points = 0
        
        # Points for corners
        corners_found = len(self.survey_data['numbers_found'])
        sequence_valid = self.survey_data['sequence_type'] in ['0-4', '5-9']
        
        if corners_found == 5 and sequence_valid:
            points += 10
        elif 1 <= corners_found <= 4:
            points += 5
        
        # Points for keel depth (assume within tolerance for now)
        # Actual validation requires true depth comparison
        if self.survey_data['keel_depth']:
            confidence = self.survey_data['keel_depth']['confidence']
            if confidence >= 0.9:
                points += 10  # Assuming high confidence = accurate
            elif confidence >= 0.7:
                points += 5
        
        return points
    
    def is_complete(self) -> bool:
        """Check if survey is complete."""
        return self.survey_data['complete']
    
    def get_missing_numbers(self) -> List[int]:
        """
        Get list of numbers not yet found (based on detected sequence).
        
        Returns:
            List of missing numbers, or empty list if sequence not determined
        """
        if self.survey_data['sequence_type'] == '0-4':
            expected = {0, 1, 2, 3, 4}
        elif self.survey_data['sequence_type'] == '5-9':
            expected = {5, 6, 7, 8, 9}
        else:
            # Try to guess from partial numbers
            found = [n['number'] for n in self.survey_data['numbers_found']]
            if any(n < 5 for n in found):
                expected = {0, 1, 2, 3, 4}
            elif any(n >= 5 for n in found):
                expected = {5, 6, 7, 8, 9}
            else:
                return []
        
        found_set = {n['number'] for n in self.survey_data['numbers_found']}
        missing = expected - found_set
        
        return sorted(list(missing))
    
    def export_data(self) -> Dict:
        """
        Export survey data for saving or transmission.
        
        Returns:
            Complete survey data dictionary
        """
        return self.survey_data.copy()
    
    def save_to_file(self, filepath: str):
        """
        Save survey data to JSON file.
        
        Args:
            filepath: Path to save file
        """
        with open(filepath, 'w') as f:
            json.dump(self.survey_data, f, indent=2)
        
        logging.info(f"Survey data saved to {filepath}")
    
    def load_from_file(self, filepath: str):
        """
        Load survey data from JSON file.
        
        Args:
            filepath: Path to load file
        """
        with open(filepath, 'r') as f:
            self.survey_data = json.load(f)
        
        logging.info(f"Survey data loaded from {filepath}")
    
    def reset(self):
        """Reset survey to start fresh."""
        self.start_survey()
        logging.info("Survey reset")


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Create tracker
    tracker = SurveyTracker()
    tracker.start_survey()
    
    # Simulate survey
    print("=== Starting Survey ===")
    
    # Add corner numbers
    tracker.add_corner_number(5, "Corner 1 - Top Left")
    tracker.add_corner_number(6, "Corner 2 - Top Right")
    tracker.add_corner_number(7, "Corner 3 - Bottom Right")
    
    print(f"Progress: {tracker.get_progress()}")
    print(f"Missing numbers: {tracker.get_missing_numbers()}")
    
    tracker.add_corner_number(8, "Corner 4 - Bottom Left")
    tracker.add_corner_number(9, "Corner 5 - Center")
    
    # Add keel measurement
    tracker.add_keel_depth(1.23, confidence=0.95)
    tracker.add_keel_number(9)
    
    # Check status
    status = tracker.get_status()
    print("\n=== Survey Status ===")
    print(f"Complete: {status['complete']}")
    print(f"Sequence: {status['sequence_type']}")
    print(f"Numbers found: {status['numbers']}")
    print(f"Keel depth: {status['keel_depth']:.3f}m")
    print(f"Points earned: {status['points_earned']}")
    
    # Save to file
    tracker.save_to_file("survey_example.json")
