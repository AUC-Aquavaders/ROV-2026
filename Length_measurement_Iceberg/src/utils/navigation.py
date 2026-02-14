"""
Navigation Utilities
====================
Geographic calculations for iceberg tracking.
"""

import math
from typing import Tuple


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate great circle distance between two points.
    
    Args:
        lat1, lon1: First point (decimal degrees)
        lat2, lon2: Second point (decimal degrees)
        
    Returns:
        Distance in nautical miles
    """
    # Convert to radians
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    
    # Haversine formula
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    
    # Nautical miles (1 NM = 1.852 km, Earth radius = 6371 km)
    nm = c * 6371 / 1.852
    
    return nm


def bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate initial bearing from point 1 to point 2.
    
    Args:
        lat1, lon1: Start point (decimal degrees)
        lat2, lon2: End point (decimal degrees)
        
    Returns:
        Bearing in degrees (0-360)
    """
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    
    dlon = lon2 - lon1
    
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    
    initial_bearing = math.atan2(x, y)
    
    # Convert to degrees and normalize to 0-360
    bearing_deg = (math.degrees(initial_bearing) + 360) % 360
    
    return bearing_deg


def destination_point(lat: float, lon: float, distance_nm: float, bearing_deg: float) -> Tuple[float, float]:
    """
    Calculate destination point given start, distance, and bearing.
    
    Args:
        lat, lon: Start point (decimal degrees)
        distance_nm: Distance in nautical miles
        bearing_deg: Bearing in degrees
        
    Returns:
        (latitude, longitude) of destination point
    """
    # Convert to radians
    lat_rad = math.radians(lat)
    lon_rad = math.radians(lon)
    bearing_rad = math.radians(bearing_deg)
    
    # Distance in radians (1 NM = 1.852 km, Earth radius = 6371 km)
    distance_rad = distance_nm * 1.852 / 6371
    
    # Calculate destination
    lat2 = math.asin(math.sin(lat_rad) * math.cos(distance_rad) +
                     math.cos(lat_rad) * math.sin(distance_rad) * math.cos(bearing_rad))
    
    lon2 = lon_rad + math.atan2(math.sin(bearing_rad) * math.sin(distance_rad) * math.cos(lat_rad),
                                math.cos(distance_rad) - math.sin(lat_rad) * math.sin(lat2))
    
    # Convert back to degrees
    return math.degrees(lat2), math.degrees(lon2)


def cross_track_distance(lat1: float, lon1: float, lat2: float, lon2: float,
                         lat3: float, lon3: float) -> float:
    """
    Calculate perpendicular distance from point 3 to great circle path from point 1 to 2.
    
    Args:
        lat1, lon1: Path start point
        lat2, lon2: Path end point
        lat3, lon3: Test point
        
    Returns:
        Cross-track distance in nautical miles
    """
    # Distance from start to test point
    d13 = haversine_distance(lat1, lon1, lat3, lon3) * 1.852 / 6371  # Convert to radians
    
    # Bearing from start to test point
    bearing13 = math.radians(bearing(lat1, lon1, lat3, lon3))
    
    # Bearing from start to end
    bearing12 = math.radians(bearing(lat1, lon1, lat2, lon2))
    
    # Cross-track distance
    dxt = math.asin(math.sin(d13) * math.sin(bearing13 - bearing12))
    
    # Convert back to nautical miles
    dxt_nm = abs(dxt * 6371 / 1.852)
    
    return dxt_nm


def latitude_to_nm(lat_degrees: float) -> float:
    """
    Convert latitude degrees to nautical miles.
    1 degree of latitude = 60 nautical miles
    
    Args:
        lat_degrees: Latitude in degrees
        
    Returns:
        Distance in nautical miles
    """
    return lat_degrees * 60


def longitude_to_nm(lon_degrees: float, latitude: float) -> float:
    """
    Convert longitude degrees to nautical miles at given latitude.
    
    Args:
        lon_degrees: Longitude in degrees
        latitude: Reference latitude (degrees)
        
    Returns:
        Distance in nautical miles
    """
    return lon_degrees * 60 * math.cos(math.radians(latitude))


# Example usage
if __name__ == "__main__":
    # Example: Distance from Hibernia to Sea Rose
    hibernia = (43.7504, -48.7819)
    sea_rose = (46.7895, -48.1417)
    
    dist = haversine_distance(*hibernia, *sea_rose)
    print(f"Distance Hibernia to Sea Rose: {dist:.2f} NM")
    
    bear = bearing(*hibernia, *sea_rose)
    print(f"Bearing: {bear:.1f}°")
    
    # Example iceberg track
    iceberg = (45.0, -48.5)
    heading = 180  # South
    
    # Distance from iceberg track to platform
    track_end = destination_point(*iceberg, 100, heading)  # Project 100 NM ahead
    cross_dist = cross_track_distance(*iceberg, *track_end, *sea_rose)
    print(f"Cross-track distance to Sea Rose: {cross_dist:.2f} NM")
