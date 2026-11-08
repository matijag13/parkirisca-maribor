"""Vremenska napoved iz Open-Meteo (brez ključa)."""

from datetime import date
from typing import Dict, Optional

import requests

URL = "https://api.open-meteo.com/v1/forecast"

KODE = {0: "jasno", 1: "pretežno jasno", 2: "delno oblačno", 3: "oblačno", 45: "megla", 48: "megla s ivjem",
        51: "rahlo pršenje", 53: "pršenje", 55: "močno pršenje", 61: "rahel dež", 63: "dež", 65: "močan dež",
        66: "rahel ledeni dež", 67: "ledeni dež", 71: "rahlo sneženje", 73: "sneženje", 75: "močno sneženje",
        77: "zrnat sneg", 80: "rahle plohe", 81: "plohe", 82: "močne plohe", 85: "snežne plohe", 86: "močne snežne plohe",
        95: "nevihta", 96: "nevihta s točo", 99: "huda nevihta s točo"}


def napoved(lat: float, lon: float, dan: date, ura: int, seja=requests) -> Optional[Dict[str, object]]:
    """Vreme za dano uro; None, če napovedi ni (npr. datum je prek 16 dni v prihodnosti ali v preteklosti)."""
    r = seja.get(URL, timeout=20, params={
        "latitude": lat, "longitude": lon, "timezone": "Europe/Ljubljana",
        "hourly": "temperature_2m,precipitation_probability,precipitation,weather_code",
        "start_date": dan.isoformat(), "end_date": dan.isoformat()})
    if r.status_code == 400:
        return None
    r.raise_for_status()
    h = r.json().get("hourly") or {}
    if not h.get("time") or ura >= len(h["time"]):
        return None
    koda = h["weather_code"][ura]
    return {"opis": KODE.get(koda, f"koda {koda}"), "temperatura_c": h["temperature_2m"][ura],
            "verjetnost_padavin_pct": h["precipitation_probability"][ura], "padavine_mm": h["precipitation"][ura]}
