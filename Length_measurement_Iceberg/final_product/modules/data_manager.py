import json
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime


class DataManager:
    """Manages data persistence and session storage."""
    
    def __init__(self, data_dir: str = "./data"):
        self.data_dir = Path(data_dir)
        self.measurements_dir = self.data_dir / "measurements"
        self.sessions_dir = self.data_dir / "sessions"
        
        self.measurements_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
    
    def save_measurement(self, measurement: Dict[str, Any]) -> str:
        """Save a single measurement to file."""
        timestamp = datetime.now().isoformat().replace(':', '-')
        filename = f"pipe_{timestamp}.json"
        filepath = self.measurements_dir / filename
        
        with open(filepath, 'w') as f:
            json.dump(measurement, f, indent=2)
        
        return str(filepath)
    
    def save_session(self, session_data: Dict[str, Any]) -> str:
        """Save a complete session."""
        session_id = session_data.get('session_id', datetime.now().strftime("%Y%m%d_%H%M%S"))
        session_dir = self.sessions_dir / f"session_{session_id}"
        session_dir.mkdir(parents=True, exist_ok=True)
        
        metadata_path = session_dir / "metadata.json"
        with open(metadata_path, 'w') as f:
            json.dump(session_data, f, indent=2)
        
        return str(session_dir)
    
    def load_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Load a session by ID."""
        session_dir = self.sessions_dir / f"session_{session_id}"
        metadata_path = session_dir / "metadata.json"
        
        if not metadata_path.exists():
            return None
        
        with open(metadata_path, 'r') as f:
            return json.load(f)
    
    def list_sessions(self) -> List[str]:
        """List all available sessions."""
        sessions = []
        for item in self.sessions_dir.iterdir():
            if item.is_dir() and item.name.startswith("session_"):
                sessions.append(item.name.replace("session_", ""))
        return sorted(sessions, reverse=True)
    
    def get_recent_measurements(self, count: int = 10) -> List[Dict[str, Any]]:
        """Get recent measurements."""
        measurements = []
        for item in sorted(self.measurements_dir.glob("*.json"), reverse=True)[:count]:
            with open(item, 'r') as f:
                measurements.append(json.load(f))
        return measurements
