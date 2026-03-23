from dataclasses import dataclass
from typing import Optional, List, Dict, Any


@dataclass
class IcebergData:
    """Data class for iceberg information."""
    x: float
    y: float
    z: float
    width: float
    height: float
    threat_level: str = 'low'


class ThreatCalculator:
    """Calculates threat levels for detected objects."""
    
    def __init__(self):
        self.threat_thresholds = {
            'low': 10.0,
            'medium': 5.0,
            'high': 2.0
        }
    
    def calculate_threat(self, iceberg: IcebergData, pipe_position: float) -> Dict[str, Any]:
        """Calculate threat level based on distance to pipe."""
        distance = abs(iceberg.z - pipe_position)
        
        if distance < self.threat_thresholds['high']:
            threat = 'high'
        elif distance < self.threat_thresholds['medium']:
            threat = 'medium'
        else:
            threat = 'low'
        
        return {
            'threat_level': threat,
            'distance': distance,
            'warning': threat in ('medium', 'high')
        }
    
    def get_all_threats(self, icebergs: List[IcebergData], pipe_position: float) -> List[Dict[str, Any]]:
        """Calculate threats for multiple icebergs."""
        return [self.calculate_threat(iceberg, pipe_position) for iceberg in icebergs]
