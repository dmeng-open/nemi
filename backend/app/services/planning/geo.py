from math import asin, cos, radians, sin, sqrt

ASSUMED_URBAN_SPEED_KMH = 30
EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1 = radians(lat1)
    phi2 = radians(lat2)
    d_phi = radians(lat2 - lat1)
    d_lambda = radians(lon2 - lon1)
    a = sin(d_phi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(a))


def estimate_travel_minutes(distance_km: float) -> int:
    return max(1, round(distance_km / ASSUMED_URBAN_SPEED_KMH * 60))
