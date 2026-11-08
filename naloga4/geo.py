"""Geokodiranje (Nominatim) in razdalje."""

import math
from functools import lru_cache
from typing import Optional, Tuple

import requests

NOMINATIM = "https://nominatim.openstreetmap.org/search"
UA = "TIDS-student-projekt/1.0 (Maribor parkirisca)"
# okvir Maribora (levo, zgoraj, desno, spodaj); zadetki izven njega se ne upoštevajo
OKVIR = "15.50,46.62,15.75,46.50"

Tocka = Tuple[float, float]


@lru_cache(maxsize=256)
def geokodiraj(naslov: str) -> Optional[Tocka]:
    """Naslov -> (lat, lon) v Mariboru ali None. Rezultati so predpomnjeni (Nominatim dovoli 1 zahtevo/s)."""
    q = naslov if "maribor" in naslov.lower() else f"{naslov}, Maribor"
    r = requests.get(NOMINATIM, headers={"User-Agent": UA}, timeout=20,
                     params={"q": q, "format": "jsonv2", "limit": 1, "viewbox": OKVIR, "bounded": 1, "countrycodes": "si"})
    r.raise_for_status()
    zadetki = r.json()
    if not zadetki:
        return None
    return float(zadetki[0]["lat"]), float(zadetki[0]["lon"])


def razdalja_m(a: Tocka, b: Tocka) -> float:
    """Zračna razdalja v metrih (haversine)."""
    r = 6371000.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def minut_peske(razdalja: float) -> int:
    """Zračno razdaljo pomnožimo z 1,3 (ovinki) in delimo s hitrostjo 80 m/min."""
    return max(1, round(razdalja * 1.3 / 80))
