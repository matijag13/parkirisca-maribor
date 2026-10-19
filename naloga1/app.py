#!/usr/bin/env python3
"""Naloga 1: XML in JSON - parkirišča v Mariboru.

Program prebere tri medsebojno povezane XML datoteke (cone, parkirišča, cilji),
podatke deserializira v Python objekte, jih poveže prek ID-jev, filtrira po
uporabnikovih pogojih, rezultat izpiše v konzolo ter shrani v JSON in nov XML.

Uporablja samo standardno knjižnico (Python 3.9 ali novejši).
"""
import argparse
import json
import math
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"


# ---------------------------------------------------------------------------
# Modeli (deserializirani objekti)
# ---------------------------------------------------------------------------
@dataclass
class Cona:
    id: str
    ime: str
    tip: str
    cena_na_uro: Optional[float]
    placljivo_od: Optional[str]
    placljivo_do: Optional[str]
    vikend_brezplacno: Optional[bool]
    datum_vira: Optional[date]
    opomba: Optional[str]


@dataclass
class Parkirisce:
    id: str
    ime: str
    naslov: str
    tip: str
    lat: float
    lon: float
    kapaciteta: Optional[int]
    id_cone: Optional[str]
    datum_vnosa: Optional[date]
    opomba: Optional[str]
    cona: Optional[Cona] = None             # nastavi se pri povezovanju
    razdalja_m: Optional[float] = None      # nastavi se, če uporabnik izbere cilj


@dataclass
class Cilj:
    id: str
    ime: str
    naslov: str
    kategorija: str
    lat: float
    lon: float
    id_parkirisca: Optional[str]
    datum_vnosa: Optional[date]
    parkirisce: Optional[Parkirisce] = None  # nastavi se pri povezovanju


# ---------------------------------------------------------------------------
# Pomožne funkcije za branje (prazna ali manjkajoča vrednost -> None)
# ---------------------------------------------------------------------------
def tekst(el, tag):
    child = el.find(tag)
    if child is None or child.text is None or not child.text.strip():
        return None
    return child.text.strip()


def v_float(s):
    return float(s) if s is not None else None


def v_int(s):
    return int(s) if s is not None else None


def v_datum(s):
    return date.fromisoformat(s) if s is not None else None


def v_bool(s):
    return None if s is None else s.lower() == "true"


# ---------------------------------------------------------------------------
# 1. Branje XML datotek
# ---------------------------------------------------------------------------
def zgradi_cono(el):
    return Cona(
        id=el.get("id"),
        ime=tekst(el, "ime"),
        tip=tekst(el, "tip"),
        cena_na_uro=v_float(tekst(el, "cenaNaUro")),
        placljivo_od=tekst(el, "placljivoOd"),
        placljivo_do=tekst(el, "placljivoDo"),
        vikend_brezplacno=v_bool(tekst(el, "vikendBrezplacno")),
        datum_vira=v_datum(tekst(el, "datumVira")),
        opomba=tekst(el, "opomba"),
    )


def zgradi_parkirisce(el):
    return Parkirisce(
        id=el.get("id"),
        ime=tekst(el, "ime"),
        naslov=tekst(el, "naslov"),
        tip=tekst(el, "tip"),
        lat=float(tekst(el, "lat")),
        lon=float(tekst(el, "lon")),
        kapaciteta=v_int(tekst(el, "kapaciteta")),
        id_cone=tekst(el, "idCone"),
        datum_vnosa=v_datum(tekst(el, "datumVnosa")),
        opomba=tekst(el, "opomba"),
    )


def zgradi_cilj(el):
    return Cilj(
        id=el.get("id"),
        ime=tekst(el, "ime"),
        naslov=tekst(el, "naslov"),
        kategorija=tekst(el, "kategorija"),
        lat=float(tekst(el, "lat")),
        lon=float(tekst(el, "lon")),
        id_parkirisca=tekst(el, "idParkirisca"),
        datum_vnosa=v_datum(tekst(el, "datumVnosa")),
    )


def nalozi(datoteka, tag, builder):
    """Prebere XML datoteko in vrne slovar {id: objekt}. Preveri unikatnost ID-jev."""
    pot = DATA_DIR / datoteka
    koren = ET.parse(pot).getroot()
    rezultat = {}
    for el in koren.findall(tag):
        if not el.get("id"):
            raise ValueError(f"{datoteka}: element <{tag}> nima atributa id")
        obj = builder(el)
        if obj.id in rezultat:
            raise ValueError(f"{datoteka}: podvojen id '{obj.id}'")
        rezultat[obj.id] = obj
    return rezultat


# ---------------------------------------------------------------------------
# 2. Povezovanje podatkov prek ID-jev
# ---------------------------------------------------------------------------
def povezi(cone, parkirisca, cilji):
    for p in parkirisca.values():
        if p.id_cone is not None:
            p.cona = cone.get(p.id_cone)
            if p.cona is None:
                print(f"Opozorilo: parkirišče {p.id} se sklicuje na neznano cono {p.id_cone}",
                      file=sys.stderr)
    for c in cilji.values():
        if c.id_parkirisca is not None:
            c.parkirisce = parkirisca.get(c.id_parkirisca)
            if c.parkirisce is None:
                print(f"Opozorilo: cilj {c.id} se sklicuje na neznano parkirišče {c.id_parkirisca}",
                      file=sys.stderr)


def razdalja_m(lat1, lon1, lat2, lon2):
    """Razdalja po zračni liniji v metrih (Haversine)."""
    r = 6371000
    f1, f2 = math.radians(lat1), math.radians(lat2)
    df = f2 - f1
    dl = math.radians(lon2 - lon1)
    a = math.sin(df / 2) ** 2 + math.cos(f1) * math.cos(f2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


# ---------------------------------------------------------------------------
# 3. Filtriranje
# ---------------------------------------------------------------------------
def filtriraj(parkirisca, args, cilj):
    rezultat = []
    for p in parkirisca.values():
        if cilj is not None:
            p.razdalja_m = razdalja_m(cilj.lat, cilj.lon, p.lat, p.lon)
        cena = p.cona.cena_na_uro if p.cona else None

        if args.radij is not None and p.razdalja_m > args.radij:
            continue
        if args.max_cena is not None and (cena is None or cena > args.max_cena):
            continue
        if args.min_kapaciteta is not None and (p.kapaciteta is None or p.kapaciteta < args.min_kapaciteta):
            continue
        if args.tip is not None and p.tip != args.tip:
            continue
        if args.brezplacen_vikend and not (p.cona and p.cona.vikend_brezplacno):
            continue
        rezultat.append(p)

    ključi = {
        "ime": lambda p: p.ime,
        "cena": lambda p: (p.cona is None or p.cona.cena_na_uro is None,
                           p.cona.cena_na_uro if p.cona and p.cona.cena_na_uro is not None else 0),
        "kapaciteta": lambda p: (p.kapaciteta is None, -(p.kapaciteta or 0)),
        "razdalja": lambda p: (p.razdalja_m is None, p.razdalja_m or 0),
    }
    rezultat.sort(key=ključi[args.razvrsti])
    return rezultat


# ---------------------------------------------------------------------------
# Izpis v konzolo (tabela)
# ---------------------------------------------------------------------------
def izpisi_tabelo(parkirisca, cilj):
    glava = ["ID", "Ime", "Tip", "Cona", "€/h", "Mest", "Razdalja"]
    vrstice = []
    for p in parkirisca:
        vrstice.append([
            p.id,
            p.ime,
            p.tip,
            p.cona.id if p.cona else "-",
            f"{p.cona.cena_na_uro:.2f}" if p.cona and p.cona.cena_na_uro is not None else "-",
            str(p.kapaciteta) if p.kapaciteta is not None else "-",
            f"{p.razdalja_m:.0f} m" if p.razdalja_m is not None else "-",
        ])
    if cilj:
        print(f"\nCilj: {cilj.ime} ({cilj.naslov})")
    if not vrstice:
        print("\nNobeno parkirišče ne ustreza filtru.")
        return
    sirine = [max(len(str(r[i])) for r in [glava] + vrstice) for i in range(len(glava))]
    def vrstica(r):
        return " | ".join(str(c).ljust(sirine[i]) for i, c in enumerate(r))
    print()
    print(vrstica(glava))
    print("-+-".join("-" * s for s in sirine))
    for r in vrstice:
        print(vrstica(r))
    print(f"\nŠtevilo rezultatov: {len(vrstice)}")


# ---------------------------------------------------------------------------
# 4. Izvoz v JSON
# ---------------------------------------------------------------------------
def iso(d):
    return d.isoformat() if d else None


def v_slovar(p):
    cona = None
    if p.cona:
        cona = {
            "id": p.cona.id,
            "ime": p.cona.ime,
            "tip": p.cona.tip,
            "cenaNaUro": p.cona.cena_na_uro,
            "placljivoOd": p.cona.placljivo_od,
            "placljivoDo": p.cona.placljivo_do,
            "vikendBrezplacno": p.cona.vikend_brezplacno,
            "datumVira": iso(p.cona.datum_vira),
        }
    return {
        "id": p.id,
        "ime": p.ime,
        "naslov": p.naslov,
        "tip": p.tip,
        "lokacija": {"lat": p.lat, "lon": p.lon},
        "kapaciteta": p.kapaciteta,
        "razdaljaDoCiljaM": round(p.razdalja_m) if p.razdalja_m is not None else None,
        "datumVnosa": iso(p.datum_vnosa),
        "opomba": p.opomba,
        "cona": cona,
    }


def izvozi_json(parkirisca, pot):
    with open(pot, "w", encoding="utf-8") as f:
        json.dump([v_slovar(p) for p in parkirisca], f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# 5. Izvoz v nov XML
# ---------------------------------------------------------------------------
def dodaj(starš, tag, vrednost):
    el = ET.SubElement(starš, tag)
    if vrednost is not None:
        el.text = str(vrednost).lower() if isinstance(vrednost, bool) else str(vrednost)
    return el


def izvozi_xml(parkirisca, pot):
    koren = ET.Element("filtrirano", stevilo=str(len(parkirisca)))
    for p in parkirisca:
        d = v_slovar(p)
        el = ET.SubElement(koren, "parkirisce", id=p.id)
        for tag in ("ime", "naslov", "tip"):
            dodaj(el, tag, d[tag])
        dodaj(el, "lat", p.lat)
        dodaj(el, "lon", p.lon)
        dodaj(el, "kapaciteta", d["kapaciteta"])
        dodaj(el, "razdaljaDoCiljaM", d["razdaljaDoCiljaM"])
        dodaj(el, "datumVnosa", d["datumVnosa"])
        dodaj(el, "opomba", d["opomba"])
        if p.cona:
            c = ET.SubElement(el, "cona", id=p.cona.id)
            for tag, kljuc in (("ime", "ime"), ("tip", "tip"), ("cenaNaUro", "cenaNaUro"),
                               ("placljivoOd", "placljivoOd"), ("placljivoDo", "placljivoDo"),
                               ("vikendBrezplacno", "vikendBrezplacno"), ("datumVira", "datumVira")):
                dodaj(c, tag, d["cona"][kljuc])
    ET.indent(koren)
    ET.ElementTree(koren).write(pot, encoding="utf-8", xml_declaration=True)


# ---------------------------------------------------------------------------
# Glavni program
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Iskanje parkirišč v Mariboru iz XML podatkov.")
    ap.add_argument("--cilj", help="ID cilja (npr. C02); izračuna razdaljo do parkirišč")
    ap.add_argument("--radij", type=float, help="največja razdalja do cilja v metrih (zahteva --cilj)")
    ap.add_argument("--max-cena", type=float, help="največja cena na uro v evrih")
    ap.add_argument("--min-kapaciteta", type=int, help="najmanjše število parkirnih mest")
    ap.add_argument("--tip", choices=["ograjeno", "ob cesti"], help="tip parkirišča")
    ap.add_argument("--brezplacen-vikend", action="store_true", help="samo parkirišča, brezplačna ob vikendih")
    ap.add_argument("--razvrsti", choices=["ime", "cena", "kapaciteta", "razdalja"], default="ime")
    ap.add_argument("--seznam-ciljev", action="store_true", help="izpiši vse cilje in končaj")
    ap.add_argument("--izhod", default=".", help="mapa za filtrirano.json in filtrirano.xml")
    args = ap.parse_args()

    cone = nalozi("cone.xml", "cona", zgradi_cono)
    parkirisca = nalozi("parkirisca.xml", "parkirisce", zgradi_parkirisce)
    cilji = nalozi("cilji.xml", "cilj", zgradi_cilj)
    povezi(cone, parkirisca, cilji)
    print(f"Naloženo: {len(cone)} con, {len(parkirisca)} parkirišč, {len(cilji)} ciljev")

    if args.seznam_ciljev:
        for c in cilji.values():
            privzeto = c.parkirisce.ime if c.parkirisce else "-"
            print(f"{c.id}  {c.ime:<32} {c.naslov:<24} privzeto parkirišče: {privzeto}")
        return

    cilj = None
    if args.cilj:
        cilj = cilji.get(args.cilj)
        if cilj is None:
            ap.error(f"neznan cilj '{args.cilj}' (poglejte --seznam-ciljev)")
    if args.radij is not None and cilj is None:
        ap.error("--radij zahteva --cilj")
    if args.razvrsti == "razdalja" and cilj is None:
        ap.error("razvrščanje po razdalji zahteva --cilj")

    rezultat = filtriraj(parkirisca, args, cilj)
    izpisi_tabelo(rezultat, cilj)

    mapa = Path(args.izhod)
    mapa.mkdir(parents=True, exist_ok=True)
    izvozi_json(rezultat, mapa / "filtrirano.json")
    izvozi_xml(rezultat, mapa / "filtrirano.xml")
    print(f"Shranjeno: {mapa / 'filtrirano.json'} in {mapa / 'filtrirano.xml'}")


if __name__ == "__main__":
    main()
