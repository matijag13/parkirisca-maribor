#!/usr/bin/env python3
"""Naloga 2: razčlenjevalnik (parser) spletnih strani Marprom o parkiranju v Mariboru.

Program prenese dve javni strani podjetja Marprom:
  A) Javna parkirišča in pajek  - uradni cenik (HTML tabele)
  B) Ograjena parkirišča        - seznam parkirišč z zapornicami in čas plačljivosti (seznam + besedilo)
iz njiju izlušči cene, območne kode, kapacitete in čase plačljivosti ter jih shrani
v datoteki cenik.json in cenik.xml, ki ju lahko uporabi končni izdelek.

Zahteve: Python 3.9+, requests, beautifulsoup4 (glej requirements.txt).
"""
import argparse
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent

VIR = "https://www.marprom.si"
STRANI = {
    "cenik": {
        "url": f"{VIR}/ceniki-in-vozovnice/javna-parkirisca-in-pajek/",
        "datoteka": "javna-parkirisca-in-pajek.html",
    },
    "ograjena": {
        "url": f"{VIR}/ograjena-parkirisca/",
        "datoteka": "ograjena-parkirisca.html",
    },
}
USER_AGENT = "Mozilla/5.0 (compatible; parkirisca-maribor-studijski-projekt/1.0)"
PREMOR_MED_ZAHTEVAMI_S = 1.0


class ParserNapaka(Exception):
    """Stran nima pričakovane strukture (npr. ker se je spremenila)."""


# ---------------------------------------------------------------------------
# Prenos strani (z lokalnim predpomnilnikom, da strežnika ne obremenjujemo)
# ---------------------------------------------------------------------------
def prenesi(url, cache_mapa, max_starost_ur, osvezi):
    """Vrne (html, iz_cacha). Predpomnjena stran se uporabi, če ni starejša od max_starost_ur."""
    cache_mapa.mkdir(parents=True, exist_ok=True)
    ime = re.sub(r"[^a-z0-9]+", "-", url.lower().replace("https://", "")).strip("-") + ".html"
    pot = cache_mapa / ime
    if not osvezi and pot.exists():
        starost_ur = (time.time() - pot.stat().st_mtime) / 3600
        if starost_ur < max_starost_ur:
            return pot.read_text(encoding="utf-8"), True

    odgovor = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
    odgovor.raise_for_status()
    html = odgovor.content.decode("utf-8", errors="replace")
    pot.write_text(html, encoding="utf-8")
    return html, False


def preberi_html(kljuc, args):
    """Vrne HTML strani: iz lokalne mape (brez omrežja) ali s spleta."""
    stran = STRANI[kljuc]
    if args.html_mapa:
        pot = Path(args.html_mapa) / stran["datoteka"]
        if not pot.exists():
            raise ParserNapaka(f"Manjka datoteka {pot}")
        return pot.read_text(encoding="utf-8")

    html, iz_cacha = prenesi(stran["url"], Path(args.cache_mapa), args.max_starost_ur, args.osvezi)
    print(f"  {'predpomnilnik' if iz_cacha else 'preneseno'}: {stran['url']}")
    if not iz_cacha:
        time.sleep(PREMOR_MED_ZAHTEVAMI_S)
    return html


# ---------------------------------------------------------------------------
# Pomožne funkcije za besedilo in cene
# ---------------------------------------------------------------------------
def cisto(besedilo):
    """Odstrani nedeljive presledke in odvečne presledke."""
    return re.sub(r"\s+", " ", (besedilo or "").replace("\xa0", " ")).strip()


def v_stevilo(s):
    """'1,80' -> 1.8 (slovenski decimalni zapis)."""
    return float(s.replace(".", "").replace(",", ".")) if "," in s else float(s)


def razcleni_ceno(besedilo):
    """'1,60 € (max. 15,70 €/dan)' -> {'cena': 1.6, 'maxNaDan': 15.7}; 'brezplačno' -> cena 0."""
    t = cisto(besedilo)
    rezultat = {"cena": None, "maxNaDan": None, "besedilo": t}
    if "brezplačno" in t.lower():
        rezultat["cena"] = 0.0
        return rezultat
    m_max = re.search(r"max\.?\s*(\d+(?:,\d+)?)\s*€", t, re.IGNORECASE)
    if m_max:
        rezultat["maxNaDan"] = v_stevilo(m_max.group(1))
        t = t[:m_max.start()]
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*€", t)
    if m:
        rezultat["cena"] = v_stevilo(m.group(1))
    return rezultat


# ---------------------------------------------------------------------------
# Stran A: cenik (HTML tabele)
# ---------------------------------------------------------------------------
def preberi_tabele(soup):
    """Vrne seznam tabel: {'naslov': ..., 'vrstice': [(oznaka, besedilo_cene), ...]}."""
    tabele = []
    for tabela in soup.find_all("table"):
        glava = tabela.find("th")
        if glava is None:
            continue
        vrstice = []
        for tr in tabela.find_all("tr"):
            celice = tr.find_all("td")
            if len(celice) == 2:
                vrstice.append((cisto(celice[0].get_text()), cisto(celice[1].get_text())))
        tabele.append({"naslov": cisto(glava.get_text()), "vrstice": vrstice})
    return tabele


def najdi_tabelo(tabele, ustreza, opis):
    for t in tabele:
        if ustreza(t["naslov"].lower()):
            return t
    raise ParserNapaka(f"Na strani s cenikom ni tabele: {opis}")


def postavke(vrstice, opozorila):
    izhod = []
    for oznaka, cena_txt in vrstice:
        c = razcleni_ceno(cena_txt)
        if c["cena"] is None:
            opozorila.append(f"Cene ni mogoče prebrati: '{oznaka}' = '{cena_txt}'")
        izhod.append({"naziv": oznaka, "cena": c["cena"], "maxNaDan": c["maxNaDan"], "besedilo": c["besedilo"]})
    return izhod


def razcleni_cenik(html):
    soup = BeautifulSoup(html, "html.parser")
    opozorila = []
    tabele = preberi_tabele(soup)
    if not tabele:
        raise ParserNapaka("Na strani s cenikom ni nobene tabele")

    bela = najdi_tabelo(tabele, lambda n: n.startswith("bela cona") and "mesečni" not in n, "Bela cona")
    mesecni = najdi_tabelo(tabele, lambda n: "mesečni najem" in n, "Bela cona - mesečni najem")
    ograjena = najdi_tabelo(tabele, lambda n: n.startswith("ograjena"), "Ograjena parkirišča")
    pajek = najdi_tabelo(tabele, lambda n: "pajek" in n, "Odvoz (pajek)")

    # Ena vrstica tabele lahko velja za več območnih kod: "(območne kode 312, 314, 318)"
    kode = []
    for oznaka, cena_txt in bela["vrstice"]:
        c = razcleni_ceno(cena_txt)
        najdene = re.findall(r"\b(\d{3})\b", oznaka)
        if not najdene or c["cena"] is None:
            opozorila.append(f"Vrstice ni mogoče razčleniti: '{oznaka}' = '{cena_txt}'")
            continue
        for koda in najdene:
            kode.append({
                "koda": koda,
                "cenaNaUro": c["cena"],
                "avtodomi": "avtodom" in oznaka.lower(),
                "maxNaDan": c["maxNaDan"],
            })
    if not kode:
        raise ParserNapaka("V tabeli Bela cona ni nobene območne kode")

    # Datum veljavnosti: "Velja od 1. 4. 2026."
    velja_od = None
    m = re.search(r"Velja od\s+(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})", cisto(soup.get_text(" ")))
    if m:
        velja_od = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    else:
        opozorila.append("Na strani ni datuma veljavnosti cenika ('Velja od ...')")

    return {
        "veljaOd": velja_od,
        "belaCona": {
            "urnaCena": kode,
            "mesecniNajemInKartice": postavke(mesecni["vrstice"], opozorila),
        },
        "ograjenaCenik": postavke(ograjena["vrstice"], opozorila),
        "pajek": postavke(pajek["vrstice"], opozorila),
        "opozorila": opozorila,
    }


# ---------------------------------------------------------------------------
# Stran B: ograjena parkirišča (seznam + besedilo)
# ---------------------------------------------------------------------------
def razcleni_ograjena(html):
    soup = BeautifulSoup(html, "html.parser")
    opozorila = []

    parkirisca = []
    for li in soup.find_all("li"):
        t = cisto(li.get_text())
        m = re.match(r"^(.+?):\s*(\d+)\s*parkirnih mest(?:\s*\+\s*(\d+)\s*za el\.?\s*vozila)?", t)
        if m:
            parkirisca.append({
                "ime": m.group(1).strip(),
                "steviloMest": int(m.group(2)),
                "steviloMestEl": int(m.group(3)) if m.group(3) else None,
            })
    if not parkirisca:
        raise ParserNapaka("Na strani z ograjenimi parkirišči ni seznama parkirišč")

    besedilo = cisto(soup.get_text(" "))

    m_del = re.search(r"delavnik\w*\s+med\s+(\d{1,2})\.\s+in\s+(\d{1,2})\.\s+uro", besedilo)
    m_sob = re.search(r"sobot\w*\s+med\s+(\d{1,2})\.\s+in\s+(\d{1,2})\.\s+uro", besedilo)
    if not (m_del and m_sob):
        raise ParserNapaka("Na strani z ograjenimi parkirišči ni časa plačljivosti")
    placljivost = {
        "delavnik": {"od": int(m_del.group(1)), "do": int(m_del.group(2))},
        "sobota": {"od": int(m_sob.group(1)), "do": int(m_sob.group(2))},
    }

    m_cena = re.search(r"(\d+(?:,\d+)?)\s*€\s*/\s*uro", besedilo)
    cena = v_stevilo(m_cena.group(1)) if m_cena else None
    if cena is None:
        opozorila.append("Na strani z ograjenimi parkirišči ni enotne urne cene")

    mesecni = []
    for li in soup.find_all("li"):
        m = re.match(r"^(.+?):\s*(\d+(?:,\d+)?)\s*€\s*mesečno", cisto(li.get_text()))
        if m:
            mesecni.append({"naziv": m.group(1).strip(), "cena": v_stevilo(m.group(2))})

    # Podatek je znan samo, če stran izrecno pove, da prostih mest ni.
    prosta_mesecna = False if "ni prostih parkirnih mest za mesečni najem" in besedilo else None

    return {
        "parkirisca": parkirisca,
        "placljivost": placljivost,
        "cenaNaUro": cena,
        "mesecniNajem": mesecni,
        "prostaMestaZaMesecniNajem": prosta_mesecna,
        "opozorila": opozorila,
    }


# ---------------------------------------------------------------------------
# Združevanje in preverjanje
# ---------------------------------------------------------------------------
def sestavi(cenik, ograjena, pridobljeno):
    opozorila = list(cenik["opozorila"]) + list(ograjena["opozorila"])

    # Navzkrižno preverjanje: urna cena na strani B mora biti enaka ceni v tabeli na strani A.
    cena_a = next((p["cena"] for p in cenik["ograjenaCenik"] if p["naziv"].lower().startswith("ura parkiranja")), None)
    if cena_a is not None and ograjena["cenaNaUro"] is not None and cena_a != ograjena["cenaNaUro"]:
        opozorila.append(f"Cena ograjenih parkirišč se razlikuje: stran A {cena_a} €, stran B {ograjena['cenaNaUro']} €")

    return {
        "meta": {
            "vir": VIR,
            "strani": [s["url"] for s in STRANI.values()],
            "pridobljeno": pridobljeno,
            "veljaOd": cenik["veljaOd"].isoformat() if cenik["veljaOd"] else None,
            "opozorila": opozorila,
        },
        "belaCona": cenik["belaCona"],
        "ograjenaParkirisca": {
            "parkirisca": ograjena["parkirisca"],
            "placljivost": ograjena["placljivost"],
            "cenaNaUro": ograjena["cenaNaUro"] if ograjena["cenaNaUro"] is not None else cena_a,
            "cenik": cenik["ograjenaCenik"],
            "mesecniNajem": ograjena["mesecniNajem"],
            "prostaMestaZaMesecniNajem": ograjena["prostaMestaZaMesecniNajem"],
        },
        "pajek": cenik["pajek"],
    }


# ---------------------------------------------------------------------------
# Izvoz
# ---------------------------------------------------------------------------
IME_ELEMENTA = {
    "strani": "stran",
    "opozorila": "opozorilo",
    "urnaCena": "obmocje",
    "mesecniNajemInKartice": "postavka",
    "parkirisca": "parkirisce",
    "cenik": "postavka",
    "mesecniNajem": "postavka",
    "pajek": "postavka",
}


def v_xml(starš, tag, vrednost):
    el = ET.SubElement(starš, tag)
    if isinstance(vrednost, dict):
        for k, v in vrednost.items():
            v_xml(el, k, v)
    elif isinstance(vrednost, list):
        for v in vrednost:
            v_xml(el, IME_ELEMENTA.get(tag, "element"), v)
    elif isinstance(vrednost, bool):
        el.text = "true" if vrednost else "false"
    elif vrednost is not None:
        el.text = str(vrednost)
    return el


def izvozi(podatki, mapa):
    mapa.mkdir(parents=True, exist_ok=True)
    with open(mapa / "cenik.json", "w", encoding="utf-8") as f:
        json.dump(podatki, f, ensure_ascii=False, indent=2)
    koren = ET.Element("cenik")
    for k, v in podatki.items():
        v_xml(koren, k, v)
    ET.indent(koren)
    ET.ElementTree(koren).write(mapa / "cenik.xml", encoding="utf-8", xml_declaration=True)


def izpisi_povzetek(p):
    print("\nPovzetek:")
    print(f"  cenik velja od: {p['meta']['veljaOd']}")
    print(f"  območne kode bele cone: {len(p['belaCona']['urnaCena'])}")
    for o in p["belaCona"]["urnaCena"]:
        dodatek = " (avtodomi)" if o["avtodomi"] else ""
        print(f"    {o['koda']}: {o['cenaNaUro']:.2f} €/h{dodatek}")
    og = p["ograjenaParkirisca"]
    print(f"  ograjena parkirišča: {len(og['parkirisca'])}, {og['cenaNaUro']:.2f} €/h")
    for pk in og["parkirisca"]:
        print(f"    {pk['ime']}: {pk['steviloMest']} mest")
    for o in p["meta"]["opozorila"]:
        print(f"  OPOZORILO: {o}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description="Razčlenjevalnik Marprom strani o parkiranju.")
    ap.add_argument("--izhod", default=".", help="mapa za cenik.json in cenik.xml (privzeto trenutna)")
    ap.add_argument("--osvezi", action="store_true", help="prezri predpomnilnik in ponovno prenesi strani")
    ap.add_argument("--cache-mapa", default=str(ROOT / ".cache"), help="mapa predpomnilnika")
    ap.add_argument("--max-starost-ur", type=float, default=6, help="največja starost predpomnilnika v urah")
    ap.add_argument("--html-mapa", help="preberi HTML iz lokalne mape (brez omrežja), npr. tests/fixtures")
    args = ap.parse_args()

    try:
        print("Berem strani Marprom ...")
        cenik = razcleni_cenik(preberi_html("cenik", args))
        ograjena = razcleni_ograjena(preberi_html("ograjena", args))
    except requests.RequestException as e:
        print(f"Napaka pri prenosu: {e}", file=sys.stderr)
        return 1
    except ParserNapaka as e:
        print(f"Napaka pri razčlenjevanju: {e}\nStran se je morda spremenila.", file=sys.stderr)
        return 1

    podatki = sestavi(cenik, ograjena, datetime.now().astimezone().isoformat(timespec="seconds"))
    izvozi(podatki, Path(args.izhod))
    izpisi_povzetek(podatki)
    print(f"\nShranjeno: {Path(args.izhod) / 'cenik.json'} in {Path(args.izhod) / 'cenik.xml'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
