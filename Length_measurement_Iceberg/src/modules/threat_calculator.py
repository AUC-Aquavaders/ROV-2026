"""
Threat Calculator Module
=========================
Calculates threat levels for oil platforms and subsea assets based on:
- Iceberg position, heading, and keel depth
- Platform locations and water depths
- Distance-based threats (surface platforms)
- Depth-based threats (subsea assets)
"""

import math
import logging
from typing import Dict, Tuple, List
from dataclasses import dataclass


@dataclass
class IcebergData:
    """Iceberg information from data sheet."""
    latitude: float  # Decimal degrees
    longitude: float  # Decimal degrees
    heading: float  # Degrees (0-360)
    keel_depth: float  # Meters


@dataclass
class Platform:
    """Oil platform information."""
    name: str
    latitude: float
    longitude: float
    water_depth: float  # Meters (negative value)


class ThreatCalculator:
    """Calculate threat levels for platforms and subsea assets."""
    
    # Platform data from competition
    PLATFORMS = {
        'Hibernia': Platform('Hibernia', 43.7504, -48.7819, -78),
        'Sea Rose': Platform('Sea Rose', 46.7895, -48.1417, -107),
        'Terra Nova': Platform('Terra Nova', 46.4, -48.4, -91),
        'Hebron': Platform('Hebron', 46.544, -48.498, -93)
    }
    
    def __init__(self):
        """Initialize threat calculator."""
        logging.info("ThreatCalculator initialized")
    
    def haversine_distance(self, lat1: float, lon1: float, 
                          lat2: float, lon2: float) -> float:
        """
        Calculate distance between two points using Haversine formula.
        
        Args:
            lat1, lon1: First point (decimal degrees)
            lat2, lon2: Second point (decimal degrees)
            
        Returns:
            Distance in nautical miles
        """
        # Convert to radians
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)
        
        # Haversine formula
        a = (math.sin(delta_lat / 2) ** 2 + 
             math.cos(lat1_rad) * math.cos(lat2_rad) * 
             math.sin(delta_lon / 2) ** 2)
        c = 2 * math.asin(math.sqrt(a))
        
        # Earth's radius in nautical miles
        r_nm = 3440.065  # nautical miles
        
        distance = r_nm * c
        
        return distance
    
    def simple_distance(self, lat1: float, lon1: float,
                       lat2: float, lon2: float) -> float:
        """
        Simple distance calculation using latitude minutes.
        Note: 1 minute of latitude = 1 nautical mile
        
        This is an approximation suitable for small distances.
        
        Args:
            lat1, lon1: First point (decimal degrees)
            lat2, lon2: Second point (decimal degrees)
            
        Returns:
            Distance in nautical miles
        """
        # Convert to minutes
        lat_diff_minutes = (lat2 - lat1) * 60
        lon_diff_minutes = (lon2 - lon1) * 60 * math.cos(math.radians((lat1 + lat2) / 2))
        
        # Pythagorean distance
        distance = math.sqrt(lat_diff_minutes**2 + lon_diff_minutes**2)
        
        return distance
    
    def distance_to_track(self, iceberg: IcebergData, platform: Platform) -> float:
        """
        Calculate the closest distance between iceberg track and platform.
        
        Assumes iceberg travels in straight line along heading.
        
        Args:
            iceberg: Iceberg data
            platform: Platform data
            
        Returns:
            Minimum distance in nautical miles
        """
        # For simplicity, we calculate perpendicular distance from platform 
        # to iceberg's track line
        
        # Convert heading to radians
        heading_rad = math.radians(iceberg.heading)
        
        # Vector from iceberg to platform
        delta_lat = platform.latitude - iceberg.latitude
        delta_lon = platform.longitude - iceberg.longitude
        
        # Convert to nautical miles (approximate)
        delta_lat_nm = delta_lat * 60  # 1 degree lat = 60 NM
        delta_lon_nm = delta_lon * 60 * math.cos(math.radians(iceberg.latitude))
        
        # Iceberg direction vector (unit vector)
        dir_lat = math.cos(heading_rad)
        dir_lon = math.sin(heading_rad)
        
        # Perpendicular distance from point to line
        # Using cross product magnitude
        cross = abs(delta_lat_nm * dir_lon - delta_lon_nm * dir_lat)
        
        # This gives perpendicular distance
        distance = cross
        
        return distance
    
    def determine_platform_threat(self, iceberg: IcebergData, 
                                  platform: Platform) -> str:
        """
        Determine threat level to surface platform.
        
        Threat levels:
        - GREEN: >10 NM away OR keel depth ≥ 110% water depth
        - YELLOW: 5-10 NM away
        - RED: <5 NM away
        
        Args:
            iceberg: Iceberg data
            platform: Platform data
            
        Returns:
            Threat level: 'green', 'yellow', or 'red'
        """
        # Check if iceberg will ground before reaching platform
        water_depth_abs = abs(platform.water_depth)
        if iceberg.keel_depth >= 1.10 * water_depth_abs:
            logging.info(f"{platform.name}: GREEN (will ground - keel {iceberg.keel_depth}m >= {1.10*water_depth_abs:.1f}m)")
            return 'green'
        
        # Calculate distance to iceberg track
        distance = self.distance_to_track(iceberg, platform)
        
        # Determine threat level based on distance
        if distance < 5:
            threat = 'red'
        elif distance < 10:
            threat = 'yellow'
        else:
            threat = 'green'
        
        logging.info(f"{platform.name}: {threat.upper()} (distance: {distance:.2f} NM)")
        
        return threat
    
    def determine_subsea_threat(self, iceberg: IcebergData,
                               platform: Platform) -> str:
        """
        Determine threat level to subsea assets.
        
        Only applies if iceberg passes within 25 NM of platform.
        
        Threat levels based on keel depth vs water depth:
        - GREEN: keel ≥ 110% depth (will ground) OR keel < 70% depth (safe clearance)
        - YELLOW: keel 70-90% depth (caution)
        - RED: keel 90-110% depth (critical danger)
        
        Args:
            iceberg: Iceberg data
            platform: Platform data
            
        Returns:
            Threat level: 'green', 'yellow', or 'red'
        """
        # Check if within 25 NM
        distance = self.distance_to_track(iceberg, platform)
        
        if distance > 25:
            logging.info(f"{platform.name} subsea: GREEN (beyond 25 NM)")
            return 'green'
        
        # Calculate keel depth as percentage of water depth
        water_depth_abs = abs(platform.water_depth)
        keel_percentage = (iceberg.keel_depth / water_depth_abs) * 100
        
        # Determine threat level
        if iceberg.keel_depth >= 1.10 * water_depth_abs:
            threat = 'green'
            reason = "will ground"
        elif iceberg.keel_depth < 0.70 * water_depth_abs:
            threat = 'green'
            reason = "safe clearance"
        elif 0.70 * water_depth_abs <= iceberg.keel_depth < 0.90 * water_depth_abs:
            threat = 'yellow'
            reason = "caution - may impact seafloor"
        else:  # 0.90 to 1.10
            threat = 'red'
            reason = "critical danger"
        
        logging.info(f"{platform.name} subsea: {threat.upper()} "
                    f"(keel {keel_percentage:.1f}% of depth - {reason})")
        
        return threat
    
    def calculate_all_threats(self, iceberg: IcebergData) -> Dict:
        """
        Calculate threat levels for all platforms and subsea assets.
        
        Args:
            iceberg: Iceberg data
            
        Returns:
            Dictionary with all threat assessments
        """
        results = {
            'iceberg': {
                'latitude': iceberg.latitude,
                'longitude': iceberg.longitude,
                'heading': iceberg.heading,
                'keel_depth': iceberg.keel_depth
            },
            'platforms': {},
            'subsea': {},
            'summary': {
                'platform_points': 0,
                'subsea_points': 0,
                'total_points': 0
            }
        }
        
        # Calculate for each platform
        for name, platform in self.PLATFORMS.items():
            platform_threat = self.determine_platform_threat(iceberg, platform)
            subsea_threat = self.determine_subsea_threat(iceberg, platform)
            distance = self.distance_to_track(iceberg, platform)
            
            results['platforms'][name] = {
                'threat': platform_threat,
                'distance_nm': round(distance, 2),
                'water_depth': platform.water_depth,
                'latitude': platform.latitude,
                'longitude': platform.longitude
            }
            
            results['subsea'][name] = {
                'threat': subsea_threat,
                'distance_nm': round(distance, 2)
            }
        
        return results
    
    def validate_threats(self, calculated: Dict, actual: Dict) -> Dict:
        """
        Validate calculated threats against actual/judge's answer.
        
        Args:
            calculated: Calculated threat results
            actual: Actual threat levels (for scoring)
            
        Returns:
            Validation results with points
        """
        platform_correct = 0
        subsea_correct = 0
        
        # Check platform threats
        for name in self.PLATFORMS.keys():
            if calculated['platforms'][name]['threat'] == actual['platforms'].get(name):
                platform_correct += 1
        
        # Check subsea threats
        for name in self.PLATFORMS.keys():
            if calculated['subsea'][name]['threat'] == actual['subsea'].get(name):
                subsea_correct += 1
        
        # Calculate points
        # Platform: 10 points for all 4 correct, 5 points for 3 correct
        if platform_correct == 4:
            platform_points = 10
        elif platform_correct == 3:
            platform_points = 5
        else:
            platform_points = 0
        
        # Subsea: 5 points only if all 4 correct
        subsea_points = 5 if subsea_correct == 4 else 0
        
        return {
            'platform_correct': platform_correct,
            'subsea_correct': subsea_correct,
            'platform_points': platform_points,
            'subsea_points': subsea_points,
            'total_points': platform_points + subsea_points
        }
    
    def generate_report(self, results: Dict) -> str:
        """
        Generate human-readable threat assessment report.
        
        Args:
            results: Results from calculate_all_threats()
            
        Returns:
            Formatted report string
        """
        report = []
        report.append("=" * 60)
        report.append("ICEBERG THREAT ASSESSMENT REPORT")
        report.append("=" * 60)
        report.append(f"\nIceberg Position: {results['iceberg']['latitude']:.4f}°, "
                     f"{results['iceberg']['longitude']:.4f}°")
        report.append(f"Heading: {results['iceberg']['heading']:.1f}°")
        report.append(f"Keel Depth: {results['iceberg']['keel_depth']:.1f}m")
        
        report.append("\n" + "-" * 60)
        report.append("SURFACE PLATFORM THREATS")
        report.append("-" * 60)
        for name, data in results['platforms'].items():
            threat_color = data['threat'].upper()
            report.append(f"{name:15} | Threat: {threat_color:6} | "
                         f"Distance: {data['distance_nm']:6.2f} NM | "
                         f"Depth: {data['water_depth']}m")
        
        report.append("\n" + "-" * 60)
        report.append("SUBSEA ASSET THREATS")
        report.append("-" * 60)
        for name, data in results['subsea'].items():
            threat_color = data['threat'].upper()
            report.append(f"{name:15} | Threat: {threat_color:6} | "
                         f"Distance: {data['distance_nm']:6.2f} NM")
        
        report.append("=" * 60)
        
        return "\n".join(report)


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Example iceberg data
    iceberg = IcebergData(
        latitude=45.5,
        longitude=-48.5,
        heading=180,  # Moving south
        keel_depth=85  # meters
    )
    
    # Calculate threats
    calc = ThreatCalculator()
    results = calc.calculate_all_threats(iceberg)
    
    # Print report
    print(calc.generate_report(results))
    
    # Example validation
    actual = {
        'platforms': {
            'Hibernia': 'green',
            'Sea Rose': 'yellow',
            'Terra Nova': 'red',
            'Hebron': 'yellow'
        },
        'subsea': {
            'Hibernia': 'green',
            'Sea Rose': 'yellow',
            'Terra Nova': 'red',
            'Hebron': 'yellow'
        }
    }
    
    validation = calc.validate_threats(results, actual)
    print(f"\nValidation: {validation}")
