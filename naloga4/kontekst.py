"""Iz cenika in vnosa uporabnika izračuna dejstva, ki jih dobi model (razdalje, plačljivost, cena)."""

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, List, Optional

import geo
from modeli import Vnos

CENIK = Path(__file__).resolve().parent / "data" / "cenik.json"


def nalozi_cenik(pot: Path = CENIK) -> dict:
    return json.loads(Path(pot).read_text(encoding="utf-8"))


def placljive_ure(zacetek: datetime, trajanje_ur: float, cenik: dict) -> float:
    """Koliko ur parkiranja je plačljivih (delavnik 6–22, sobota 8–13, nedelja brezplačno)."""
    p = cenik["ograjenaParkirisca"]["placljivost"]
    konec = zacetek + timedelta(hours=trajanje_ur)
    skupaj = 0.0
    dan = zacetek.date()
    while dan <= konec.date():
        okno = p["delavnik"] if dan.weekday() < 5 else (p["sobota"] if dan.weekday() == 5 else None)
        if okno:
            od = datetime.combine(dan, datetime.min.time()) + timedelta(hours=okno["od"])
            do = datetime.combine(dan, datetime.min.time()) + timedelta(hours=okno["do"])
            skupaj += max(0.0, (min(konec, do) - max(zacetek, od)).total_seconds() / 3600)
        dan += timedelta(days=1)
    return round(skupaj, 2)


def opisi_placljivost(cenik: dict) -> str:
    p = cenik["ograjenaParkirisca"]["placljivost"]
    return f"delavnik {p['delavnik']['od']}–{p['delavnik']['do']}, sobota {p['sobota']['od']}–{p['sobota']['do']}, nedelja brezplačno"


def zberi_opcije(vnos: Vnos, cilj: Optional[geo.Tocka], cenik: dict,
                 geokodiraj: Callable[[str], Optional[geo.Tocka]] = geo.geokodiraj) -> List[Dict[str, object]]:
    """Seznam parkirnih možnosti z dejstvi, izračunanimi na strežniku. Model sme izbirati samo med njimi."""
    zacetek = datetime.combine(vnos.datum, datetime.strptime(vnos.ura, "%H:%M").time())
    ure = placljive_ure(zacetek, vnos.trajanje_ur, cenik)
    ogr = cenik["ograjenaParkirisca"]
    opcije: List[Dict[str, object]] = []
    for p in ogr["parkirisca"]:
        tocka = geokodiraj(p["ime"])
        razd = round(geo.razdalja_m(cilj, tocka)) if cilj and tocka else None
        opcije.append({
            "ime": p["ime"], "tip": "ograjeno", "stevilo_mest": p["steviloMest"], "mesta_za_ev": p["steviloMestEl"],
            "razdalja_m": razd, "pes_minut": geo.minut_peske(razd) if razd is not None else None,
            "cena_na_uro": ogr["cenaNaUro"], "placljivih_ur": ure, "ocenjena_cena_eur": round(ure * ogr["cenaNaUro"], 2),
        })
    cene = [o["cenaNaUro"] for o in cenik["belaCona"]["urnaCena"] if not o["avtodomi"]]
    opcije.append({
        "ime": "Bela cona (ob cesti)", "tip": "bela cona", "stevilo_mest": None, "mesta_za_ev": None,
        "razdalja_m": None, "pes_minut": None,
        "cena_na_uro": f"{min(cene):.2f}–{max(cene):.2f}", "placljivih_ur": ure,
        "ocenjena_cena_eur": round(ure * min(cene), 2),
        "opomba": "cena je odvisna od območne kode, a Marprom ne objavlja, katere ulice spadajo v katero kodo; "
                  "prosta mesta niso znana; ocenjena cena je spodnja meja",
    })
    return opcije
