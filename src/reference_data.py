"""Reference station coordinates, distance metrics, and spatial helpers for KWRIS."""

from __future__ import annotations
import math
from typing import Dict, List, Optional, Tuple
from src.models import StationCoordinates


# Reference coordinates for known Karnataka KWRIS stations
KARNATAKA_STATION_CATALOG: Dict[str, Tuple[float, float, str, str]] = {
    # Arkavathi Basin (Cauvery)
    "adankuppe": (13.085, 77.345, "Cauvery", "Arkavati"),
    "bidadi": (12.798, 77.387, "Cauvery", "Arkavati"),
    "byramangala": (12.748, 77.409, "Cauvery", "Arkavati"),
    "doddaballapur": (13.292, 77.538, "Cauvery", "Arkavati"),
    "doddabelavangala": (13.342, 77.412, "Cauvery", "Arkavati"),
    "doddalahally": (12.483, 77.489, "Cauvery", "Arkavati"),
    "doddamaralawadi": (12.637, 77.491, "Cauvery", "Arkavati"),
    "harohally": (12.658, 77.468, "Cauvery", "Arkavati"),
    "kailancha": (12.632, 77.291, "Cauvery", "Arkavati"),
    "kanakapura": (12.551, 77.416, "Cauvery", "Arkavati"),
    "kanasavadi": (13.250, 77.441, "Cauvery", "Arkavati"),
    "kengeri": (12.912, 77.484, "Cauvery", "Arkavati"),
    "kodihally": (12.502, 77.531, "Cauvery", "Arkavati"),
    "manchanbele": (12.876, 77.334, "Cauvery", "Arkavati"),
    "mullahally": (12.441, 77.391, "Cauvery", "Arkavati"),
    "nelamangala": (13.098, 77.391, "Cauvery", "Arkavati"),
    "ramanagara": (12.723, 77.281, "Cauvery", "Arkavati"),
    "shivanahalli": (12.697, 77.581, "Cauvery", "Arkavati"),
    "solur": (13.051, 77.195, "Cauvery", "Arkavati"),
    "sonnenahally": (12.964, 77.502, "Cauvery", "Arkavati"),
    "tavarekere": (12.962, 77.417, "Cauvery", "Arkavati"),
    "thippagondanahalli": (12.963, 77.342, "Cauvery", "Arkavati"),
    "thyamagondlu": (13.212, 77.302, "Cauvery", "Arkavati"),
    "uttarahalli": (12.903, 77.545, "Cauvery", "Arkavati"),

    # Ghataprabha Basin (Krishna)
    "anagawadi": (16.234, 75.684, "Krishna", "Ghataprabha"),
    "ankalgi": (16.035, 74.654, "Krishna", "Ghataprabha"),
    "bagalkot": (16.181, 75.696, "Krishna", "Ghataprabha"),
    "belgaum": (15.849, 74.497, "Krishna", "Ghataprabha"),
    "bugate allur": (16.291, 74.721, "Krishna", "Ghataprabha"),
    "chikanandi": (16.284, 74.842, "Krishna", "Ghataprabha"),
    "daddi": (15.962, 74.412, "Krishna", "Ghataprabha"),
    "gokak": (16.167, 74.823, "Krishna", "Ghataprabha"),
    "hallur": (16.273, 75.148, "Krishna", "Ghataprabha"),
    "hattargi": (16.068, 74.492, "Krishna", "Ghataprabha"),
    "hidkal dam": (16.151, 74.633, "Krishna", "Ghataprabha"),
    "hirekoppa": (16.121, 75.051, "Krishna", "Ghataprabha"),
    "hukkeri": (16.223, 74.601, "Krishna", "Ghataprabha"),
    "hulkund": (16.082, 75.132, "Krishna", "Ghataprabha"),
    "jodatti": (16.342, 74.891, "Krishna", "Ghataprabha"),
    "kakati": (15.932, 74.521, "Krishna", "Ghataprabha"),
    "kaladagi": (16.208, 75.498, "Krishna", "Ghataprabha"),
    "kulgod": (16.283, 75.017, "Krishna", "Ghataprabha"),
    "lokapur": (16.159, 75.362, "Krishna", "Ghataprabha"),
    "mahalingpur": (16.389, 75.118, "Krishna", "Ghataprabha"),
    "maradi.shivapur": (16.251, 74.812, "Krishna", "Ghataprabha"),
    "mudalgi": (16.329, 75.042, "Krishna", "Ghataprabha"),
    "mudhol": (16.345, 75.284, "Krishna", "Ghataprabha"),
    "nagarmunoli": (16.421, 74.783, "Krishna", "Ghataprabha"),
    "nesargi": (15.952, 74.791, "Krishna", "Ghataprabha"),
    "sankeshwar": (16.262, 74.482, "Krishna", "Ghataprabha"),
    "sarapur": (16.211, 75.241, "Krishna", "Ghataprabha"),
    "savasuddi": (16.442, 75.031, "Krishna", "Ghataprabha"),
    "sutagatti": (15.912, 74.682, "Krishna", "Ghataprabha"),
    "yadwad": (16.241, 75.092, "Krishna", "Ghataprabha"),

    # Malaprabha / K3 / K4 Basin Stations
    "badami": (15.919, 75.681, "Krishna", "Malaprabha"),
    "kerur": (16.012, 75.561, "Krishna", "Malaprabha"),
    "kulageri_cross": (15.981, 75.489, "Krishna", "Malaprabha"),
    "belur(bgk)": (15.852, 75.721, "Krishna", "Malaprabha"),
    "katageri": (15.941, 75.521, "Krishna", "Malaprabha"),
    "gudur": (15.892, 75.891, "Krishna", "Malaprabha"),
    "sulebhavi_1": (16.031, 75.812, "Krishna", "Malaprabha"),
    "guledgudd": (16.052, 75.789, "Krishna", "Malaprabha"),
    "rampur": (15.962, 75.941, "Krishna", "Malaprabha"),
    "bevur": (16.091, 75.882, "Krishna", "Malaprabha"),
    "amingad": (16.042, 75.981, "Krishna", "Malaprabha"),
    "kudalsangam": (16.212, 76.051, "Krishna", "Malaprabha"),
    "yergatti": (15.962, 75.012, "Krishna", "Malaprabha"),
    "soundathi": (15.762, 75.112, "Krishna", "Malaprabha"),
    "kittur": (15.602, 74.792, "Krishna", "Malaprabha"),
    "walmi": (15.482, 74.961, "Krishna", "Malaprabha"),
    "khanapur": (15.632, 74.512, "Krishna", "Malaprabha"),
    "asoga": (15.612, 74.501, "Krishna", "Malaprabha"),
    "tegur": (15.621, 74.812, "Krishna", "Malaprabha"),
    "byahatti": (15.421, 75.251, "Krishna", "Malaprabha"),
    "koliwad": (15.391, 75.361, "Krishna", "Malaprabha"),
    "hole-alur": (15.751, 75.712, "Krishna", "Malaprabha"),
    "ron": (15.692, 75.731, "Krishna", "Malaprabha"),
    "hanumanal": (15.821, 75.931, "Krishna", "Malaprabha"),
}


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points in km."""
    R = 6371.0  # Earth's radius in kilometers
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (math.sin(delta_phi / 2.0) ** 2 +
         math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2))
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(R * c, 2)


def get_quadrant(target_lat: float, target_lon: float,
                 candidate_lat: float, candidate_lon: float) -> str:
    """Determine quadrant of candidate relative to target: 'NE', 'SE', 'SW', 'NW'."""
    d_lat = candidate_lat - target_lat
    d_lon = candidate_lon - target_lon
    if d_lat >= 0 and d_lon >= 0:
        return "NE"
    elif d_lat < 0 and d_lon >= 0:
        return "SE"
    elif d_lat < 0 and d_lon < 0:
        return "SW"
    else:
        return "NW"


def lookup_station_coordinates(station_name: str, station_id: Optional[str] = None) -> Optional[Tuple[float, float]]:
    """Lookup station coordinates from built-in catalog using fuzzy/normalized name match."""
    norm_name = str(station_name).strip().lower()
    if norm_name in KARNATAKA_STATION_CATALOG:
        lat, lon, _, _ = KARNATAKA_STATION_CATALOG[norm_name]
        return (lat, lon)
    
    # Try partial or stripped match
    for k, v in KARNATAKA_STATION_CATALOG.items():
        if k in norm_name or norm_name in k:
            return (v[0], v[1])
            
    return None


def select_neighbours(
    target_station: str,
    all_stations: List[str],
    coords_map: Dict[str, Tuple[float, float]],
    max_neighbours: int = 8,
    max_per_quadrant: int = 2,
    search_radius_km: float = 35.0
) -> List[Dict[str, Any]]:
    """
    Select up to `max_neighbours` stations within `search_radius_km`, 
    with at most `max_per_quadrant` per quadrant (NE, SE, SW, NW).
    Returns list of dicts with station, distance_km, quadrant.
    """
    if target_station not in coords_map:
        return []
    
    t_lat, t_lon = coords_map[target_station]
    candidates = []
    
    for s in all_stations:
        if s == target_station or s not in coords_map:
            continue
        c_lat, c_lon = coords_map[s]
        dist = haversine_distance_km(t_lat, t_lon, c_lat, c_lon)
        if dist <= search_radius_km:
            quad = get_quadrant(t_lat, t_lon, c_lat, c_lon)
            candidates.append({
                "station": s,
                "distance_km": dist,
                "quadrant": quad,
                "lat": c_lat,
                "lon": c_lon
            })
            
    # Sort candidates by distance ascending
    candidates.sort(key=lambda x: x["distance_km"])
    
    # Select at most max_per_quadrant per quadrant
    quad_counts = {"NE": 0, "SE": 0, "SW": 0, "NW": 0}
    selected = []
    
    for c in candidates:
        q = c["quadrant"]
        if quad_counts[q] < max_per_quadrant and len(selected) < max_neighbours:
            selected.append(c)
            quad_counts[q] += 1
            
    return selected
