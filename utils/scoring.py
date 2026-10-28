"""
utils/scoring.py — real distance calculation and the suitability score
that makes search results feel smart instead of just alphabetical.
"""

import math


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371  # Earth's radius in km
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def compute_score(distance_km: float, price_per_hour: float, available_slots: int, total_slots: int) -> int:
    """
    Weighted suitability score, 0-100.
    distance 40% + price 30% + availability 30%.
    """
    max_distance = 5.0
    max_price = 50.0

    distance_score = 1 - min(distance_km / max_distance, 1)
    price_score = 1 - min(price_per_hour / max_price, 1)
    availability_score = (available_slots / total_slots) if total_slots else 0

    score = (0.4 * distance_score) + (0.3 * price_score) + (0.3 * availability_score)
    return round(score * 100)
