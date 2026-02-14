"""
Data Management Module
======================
Handles storage, logging, and export of mission data.
"""

import json
import csv
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
import sqlite3


class DataManager:
    """Manages mission data storage and export."""
    
    def __init__(self, data_dir: str = "./data"):
        """
        Initialize data manager.
        
        Args:
            data_dir: Directory for storing data files
        """
        self.data_dir = Path(data_dir)
        
        # Create directories
        self.surveys_dir = self.data_dir / "surveys"
        self.logs_dir = self.data_dir / "logs"
        self.exports_dir = self.data_dir / "exports"
        
        for dir_path in [self.surveys_dir, self.logs_dir, self.exports_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)
        
        # Setup logging
        self._setup_logging()
        
        # Database for detailed logging
        self.db_path = self.data_dir / "mission_data.db"
        self._setup_database()
        
        logging.info(f"DataManager initialized at {self.data_dir}")
    
    def _setup_logging(self):
        """Setup file logging."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = self.logs_dir / f"mission_{timestamp}.log"
        
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        
        logging.getLogger().addHandler(file_handler)
    
    def _setup_database(self):
        """Setup SQLite database for structured data."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create tables
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS surveys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                sequence_type TEXT,
                keel_depth REAL,
                keel_confidence REAL,
                complete INTEGER,
                points_earned INTEGER,
                data_json TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS measurements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                survey_id INTEGER,
                timestamp TEXT NOT NULL,
                measurement_type TEXT,
                value REAL,
                confidence REAL,
                location TEXT,
                FOREIGN KEY (survey_id) REFERENCES surveys (id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS threat_assessments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                survey_id INTEGER,
                timestamp TEXT NOT NULL,
                iceberg_lat REAL,
                iceberg_lon REAL,
                iceberg_heading REAL,
                iceberg_keel_depth REAL,
                results_json TEXT,
                FOREIGN KEY (survey_id) REFERENCES surveys (id)
            )
        ''')
        
        conn.commit()
        conn.close()
        
        logging.info("Database initialized")
    
    def save_survey(self, survey_data: Dict) -> int:
        """
        Save survey data to database.
        
        Args:
            survey_data: Survey data dictionary
            
        Returns:
            Survey ID
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Extract key fields
        timestamp = survey_data.get('completed_at') or datetime.now().isoformat()
        sequence_type = survey_data.get('sequence_type')
        keel_depth = survey_data['keel_depth']['depth'] if survey_data.get('keel_depth') else None
        keel_confidence = survey_data['keel_depth']['confidence'] if survey_data.get('keel_depth') else None
        complete = 1 if survey_data.get('complete') else 0
        
        # Insert survey
        cursor.execute('''
            INSERT INTO surveys (timestamp, sequence_type, keel_depth, keel_confidence, 
                               complete, points_earned, data_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (timestamp, sequence_type, keel_depth, keel_confidence, complete, 0, 
              json.dumps(survey_data)))
        
        survey_id = cursor.lastrowid
        
        # Insert individual measurements
        for number_entry in survey_data.get('numbers_found', []):
            cursor.execute('''
                INSERT INTO measurements (survey_id, timestamp, measurement_type, 
                                        value, confidence, location)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (survey_id, number_entry['timestamp'], 'corner_number',
                  number_entry['number'], number_entry.get('confidence', 1.0),
                  number_entry.get('location', 'unknown')))
        
        conn.commit()
        conn.close()
        
        # Also save as JSON file
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_file = self.surveys_dir / f"survey_{timestamp_str}.json"
        with open(json_file, 'w') as f:
            json.dump(survey_data, f, indent=2)
        
        logging.info(f"Survey saved with ID: {survey_id}")
        
        return survey_id
    
    def save_threat_assessment(self, threat_results: Dict, survey_id: Optional[int] = None):
        """
        Save threat assessment results.
        
        Args:
            threat_results: Results from ThreatCalculator
            survey_id: Optional survey ID to link to
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        iceberg = threat_results['iceberg']
        timestamp = datetime.now().isoformat()
        
        cursor.execute('''
            INSERT INTO threat_assessments (survey_id, timestamp, iceberg_lat, 
                                          iceberg_lon, iceberg_heading, 
                                          iceberg_keel_depth, results_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (survey_id, timestamp, iceberg['latitude'], iceberg['longitude'],
              iceberg['heading'], iceberg['keel_depth'], json.dumps(threat_results)))
        
        conn.commit()
        conn.close()
        
        # Save as JSON
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_file = self.exports_dir / f"threat_assessment_{timestamp_str}.json"
        with open(json_file, 'w') as f:
            json.dump(threat_results, f, indent=2)
        
        logging.info("Threat assessment saved")
    
    def log_measurement(self, measurement_type: str, value: float, 
                       confidence: float = 1.0, location: str = ''):
        """
        Log a measurement to database.
        
        Args:
            measurement_type: Type of measurement (e.g., 'depth', 'number')
            value: Measurement value
            confidence: Confidence score
            location: Location description
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        timestamp = datetime.now().isoformat()
        
        cursor.execute('''
            INSERT INTO measurements (timestamp, measurement_type, value, 
                                    confidence, location)
            VALUES (?, ?, ?, ?, ?)
        ''', (timestamp, measurement_type, value, confidence, location))
        
        conn.commit()
        conn.close()
    
    def export_for_judge(self, survey_id: int) -> str:
        """
        Export survey data in judge-friendly format.
        
        Args:
            survey_id: Survey ID to export
            
        Returns:
            Path to exported file
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get survey data
        cursor.execute('SELECT * FROM surveys WHERE id = ?', (survey_id,))
        survey = cursor.fetchone()
        
        if not survey:
            logging.error(f"Survey {survey_id} not found")
            return None
        
        # Get measurements
        cursor.execute('''
            SELECT timestamp, measurement_type, value, confidence, location
            FROM measurements WHERE survey_id = ?
        ''', (survey_id,))
        measurements = cursor.fetchall()
        
        conn.close()
        
        # Create export document
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_file = self.exports_dir / f"judge_report_{timestamp_str}.txt"
        
        with open(export_file, 'w') as f:
            f.write("=" * 70 + "\n")
            f.write("ICEBERG SURVEY - JUDGE REPORT\n")
            f.write("=" * 70 + "\n\n")
            
            f.write(f"Survey ID: {survey[0]}\n")
            f.write(f"Timestamp: {survey[1]}\n")
            f.write(f"Sequence Type: {survey[2]}\n")
            f.write(f"Complete: {'Yes' if survey[5] else 'No'}\n\n")
            
            f.write("-" * 70 + "\n")
            f.write("CORNER NUMBERS SURVEYED\n")
            f.write("-" * 70 + "\n")
            
            corner_numbers = [m for m in measurements if m[1] == 'corner_number']
            for i, meas in enumerate(corner_numbers, 1):
                f.write(f"{i}. Number {int(meas[2])} - {meas[4]} "
                       f"(Confidence: {meas[3]:.2%}) - {meas[0]}\n")
            
            f.write("\n" + "-" * 70 + "\n")
            f.write("KEEL DEPTH MEASUREMENT\n")
            f.write("-" * 70 + "\n")
            
            if survey[3]:
                f.write(f"Depth: {survey[3]:.3f} meters\n")
                f.write(f"Confidence: {survey[4]:.2%}\n")
            else:
                f.write("Not measured\n")
            
            f.write("\n" + "=" * 70 + "\n")
        
        logging.info(f"Judge report exported to {export_file}")
        
        return str(export_file)
    
    def export_to_csv(self, table_name: str, output_file: Optional[str] = None) -> str:
        """
        Export database table to CSV.
        
        Args:
            table_name: Name of table to export
            output_file: Optional output file path
            
        Returns:
            Path to exported file
        """
        if output_file is None:
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = self.exports_dir / f"{table_name}_{timestamp_str}.csv"
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get data
        cursor.execute(f'SELECT * FROM {table_name}')
        rows = cursor.fetchall()
        
        # Get column names
        column_names = [description[0] for description in cursor.description]
        
        conn.close()
        
        # Write to CSV
        with open(output_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(column_names)
            writer.writerows(rows)
        
        logging.info(f"Exported {table_name} to {output_file}")
        
        return str(output_file)
    
    def get_survey_history(self, limit: int = 10) -> List[Dict]:
        """
        Get recent survey history.
        
        Args:
            limit: Number of surveys to retrieve
            
        Returns:
            List of survey data dictionaries
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, timestamp, sequence_type, keel_depth, complete, points_earned
            FROM surveys
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (limit,))
        
        surveys = []
        for row in cursor.fetchall():
            surveys.append({
                'id': row[0],
                'timestamp': row[1],
                'sequence_type': row[2],
                'keel_depth': row[3],
                'complete': bool(row[4]),
                'points_earned': row[5]
            })
        
        conn.close()
        
        return surveys


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Initialize data manager
    dm = DataManager(data_dir="./data")
    
    # Example survey data
    survey_data = {
        'numbers_found': [
            {'number': 5, 'location': 'Corner 1', 'timestamp': datetime.now().isoformat(), 'confidence': 0.95},
            {'number': 6, 'location': 'Corner 2', 'timestamp': datetime.now().isoformat(), 'confidence': 0.92},
            {'number': 7, 'location': 'Corner 3', 'timestamp': datetime.now().isoformat(), 'confidence': 0.88},
            {'number': 8, 'location': 'Corner 4', 'timestamp': datetime.now().isoformat(), 'confidence': 0.91},
            {'number': 9, 'location': 'Corner 5', 'timestamp': datetime.now().isoformat(), 'confidence': 0.94},
        ],
        'keel_depth': {
            'depth': 1.23,
            'timestamp': datetime.now().isoformat(),
            'confidence': 0.95
        },
        'sequence_type': '5-9',
        'complete': True,
        'started_at': datetime.now().isoformat(),
        'completed_at': datetime.now().isoformat()
    }
    
    # Save survey
    survey_id = dm.save_survey(survey_data)
    
    # Export for judge
    report_path = dm.export_for_judge(survey_id)
    print(f"Judge report: {report_path}")
    
    # Get history
    history = dm.get_survey_history(limit=5)
    print(f"\nRecent surveys: {len(history)}")
    for survey in history:
        print(f"  - {survey['timestamp']}: {survey['sequence_type']} - Complete: {survey['complete']}")
