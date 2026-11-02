"""Filtriranje in združevanje (agregacija) podatkov iz PX tabel za grafe.

Vse funkcije dobijo že razčlenjeno tabelo (pcaxis.PxTabela) in vrnejo preproste slovarje/sezname,
ki jih FastAPI pretvori v JSON. Brez omrežja, zato jih je lahko preizkusiti.
"""

from typing import Dict, List, Optional

from pcaxis import PxTabela

# Koda tabel SURS, ki jih uporabljamo
T_VOZILA = "2222105S"          # cestna vozila konec leta po vrsti vozila, občinah in letih
T_POGON = "2222109S"           # vozila po vrsti pogona in goriva
T_MOTORIZACIJA = "2221110S"    # kazalniki transporta po občinah (avtomobili na 1000 prebivalcev)
T_POTI = "2281296S"            # letno število poti v MOL in MOM po prevoznem sredstvu
T_PARKIRANJE = "2281931S"      # kraj parkiranja avtomobila, uporabljenega za pot na delo

SLOVENIJA = "SLOVENIJA"
PRIVZETA_OBCINA = "Maribor"
KAZALNIK_MOTORIZACIJA = "Število navadnih osebnih avtomobilov na 1.000"
SKUPAJ_ZETON = "SKUPAJ"


class NapacenVnos(ValueError):
    """Uporabnik je zahteval vrednost, ki je v tabeli ni."""


def _najdi(t: PxTabela, spremenljivka: str, izbira: str) -> str:
    """Vrne točno oznako vrednosti ali sproži NapacenVnos (s seznamom možnosti za sporočilo)."""
    try:
        return t.oznake[spremenljivka][t.indeks_vrednosti(spremenljivka, izbira)]
    except KeyError as napaka:
        raise NapacenVnos(f"{spremenljivka}: neznana vrednost {izbira!r}") from napaka


def _zaokrozi(x: Optional[float], mest: int = 1) -> Optional[float]:
    if x is None:
        return None
    r = round(x, mest)
    return int(r) if mest == 0 else r


def _delez(del_: Optional[float], celota: Optional[float]) -> Optional[float]:
    if del_ is None or not celota:
        return None
    return round(100.0 * del_ / celota, 1)


def zadnje_leto(t: PxTabela, spremenljivka: str = "LETO") -> str:
    return t.oznake[spremenljivka][-1]


# ---------------------------------------------------------------------------
# 1. Vozni park po občinah (2222105S)
# ---------------------------------------------------------------------------

def izbire_vozil(t: PxTabela) -> Dict[str, object]:
    obcine = [o for o in t.oznake["OBČINE"]]
    privzete = []
    for koda in ("1.31", "1.4", "1.5"):
        try:
            privzete.append(_najdi(t, "VRSTA VOZILA", koda))
        except NapacenVnos:
            pass
    return {"obcine": obcine, "vrste": t.oznake["VRSTA VOZILA"], "leta": t.oznake["LETO"],
            "privzeto": {"obcina": PRIVZETA_OBCINA if PRIVZETA_OBCINA in obcine else obcine[0],
                         "vrste": privzete or t.oznake["VRSTA VOZILA"][:1]}}


def vozni_park(t: PxTabela, obcina: str, vrste: List[str], od_leta: Optional[str] = None) -> Dict[str, object]:
    """Število vozil po letih za eno občino; filtriranje po občini, vrstah vozil in začetnem letu."""
    obcina = _najdi(t, "OBČINE", obcina)
    leta = t.oznake["LETO"]
    if od_leta:
        od = _najdi(t, "LETO", od_leta)
        leta = leta[leta.index(od):]
    serije = []
    for vrsta in vrste:
        vrsta = _najdi(t, "VRSTA VOZILA", vrsta)
        vrednosti = [t.vrednost({"VRSTA VOZILA": vrsta, "OBČINE": obcina, "LETO": l}) for l in leta]
        prvo = next((v for v in vrednosti if v), None)
        serije.append({
            "vrsta": vrsta,
            "vrednosti": [_zaokrozi(v, 0) for v in vrednosti],
            # indeks rasti: prva razpoložljiva vrednost = 100
            "indeks": [round(100.0 * v / prvo, 1) if v is not None and prvo else None for v in vrednosti],
        })
    return {"obcina": obcina, "leta": leta, "enota": t.enota, "serije": serije}


def lestvica_vozil(t: PxTabela, leto: str, vrsta: str, top: int = 10, izpostavi: str = PRIVZETA_OBCINA) -> Dict[str, object]:
    """Občine, urejene po številu vozil; izpostavljena občina je vedno vključena z rangom in deležem v državi."""
    leto = _najdi(t, "LETO", leto)
    vrsta = _najdi(t, "VRSTA VOZILA", vrsta)
    izpostavi = _najdi(t, "OBČINE", izpostavi)
    vse = []
    for obcina in t.oznake["OBČINE"]:
        if obcina == SLOVENIJA:
            continue
        v = t.vrednost({"VRSTA VOZILA": vrsta, "OBČINE": obcina, "LETO": leto})
        if v is not None:
            vse.append((obcina, v))
    vse.sort(key=lambda x: x[1], reverse=True)
    skupaj = t.vrednost({"VRSTA VOZILA": vrsta, "OBČINE": SLOVENIJA, "LETO": leto})
    vrstni_red = {o: i + 1 for i, (o, _) in enumerate(vse)}
    izbrane = vse[:max(1, top)]
    if izpostavi not in {o for o, _ in izbrane} and izpostavi in vrstni_red:
        izbrane.append((izpostavi, dict(vse)[izpostavi]))
    return {
        "leto": leto, "vrsta": vrsta, "izpostavljena": izpostavi, "steviloObcin": len(vse),
        "slovenija": _zaokrozi(skupaj, 0),
        "postavke": [{"obcina": o, "vrednost": _zaokrozi(v, 0), "rang": vrstni_red[o], "delezVSloveniji": _delez(v, skupaj)}
                     for o, v in izbrane],
    }


# ---------------------------------------------------------------------------
# 2. Stopnja motorizacije (2221110S)
# ---------------------------------------------------------------------------

def motorizacija(t: PxTabela, obcine: List[str]) -> Dict[str, object]:
    kazalnik = _najdi(t, "KAZALNIK", KAZALNIK_MOTORIZACIJA)
    leta = t.oznake["LETO"]
    serije = []
    for obcina in obcine:
        obcina = _najdi(t, "OBČINE", obcina)
        serije.append({"obcina": obcina, "vrednosti": [_zaokrozi(t.vrednost({"KAZALNIK": kazalnik, "OBČINE": obcina, "LETO": l}))
                                                       for l in leta]})
    return {"kazalnik": kazalnik, "leta": leta, "serije": serije}


def lestvica_motorizacije(t: PxTabela, leto: str, top: int = 10, izpostavi: str = PRIVZETA_OBCINA) -> Dict[str, object]:
    kazalnik = _najdi(t, "KAZALNIK", KAZALNIK_MOTORIZACIJA)
    leto = _najdi(t, "LETO", leto)
    izpostavi = _najdi(t, "OBČINE", izpostavi)
    vse = [(o, t.vrednost({"KAZALNIK": kazalnik, "OBČINE": o, "LETO": leto})) for o in t.oznake["OBČINE"] if o != SLOVENIJA]
    vse = sorted([(o, v) for o, v in vse if v is not None], key=lambda x: x[1], reverse=True)
    rang = {o: i + 1 for i, (o, _) in enumerate(vse)}
    izbrane = vse[:max(1, top)]
    if izpostavi not in {o for o, _ in izbrane} and izpostavi in rang:
        izbrane.append((izpostavi, dict(vse)[izpostavi]))
    povprecje = t.vrednost({"KAZALNIK": kazalnik, "OBČINE": SLOVENIJA, "LETO": leto})
    return {"leto": leto, "kazalnik": kazalnik, "izpostavljena": izpostavi, "steviloObcin": len(vse),
            "slovenija": _zaokrozi(povprecje),
            "postavke": [{"obcina": o, "vrednost": _zaokrozi(v), "rang": rang[o]} for o, v in izbrane]}


# ---------------------------------------------------------------------------
# 3. Pogon osebnih avtomobilov (2222109S)
# ---------------------------------------------------------------------------

def izbire_pogona(t: PxTabela) -> Dict[str, object]:
    vrste = t.oznake["VRSTA VOZILA"]
    osebni = next((v for v in vrste if "osebni avtomobili" in v.lower()), vrste[0])
    return {"vrste": vrste, "meritve": t.oznake["MERITVE"], "leta": t.oznake["LETO"],
            "privzeto": {"vrsta": osebni, "meritev": t.oznake["MERITVE"][0]}}


def pogon(t: PxTabela, vrsta: str, meritev: Optional[str] = None) -> Dict[str, object]:
    """Delež posameznih pogonov (v %) po letih: del / vrstica »SKUPAJ«."""
    vrsta = _najdi(t, "VRSTA VOZILA", vrsta)
    meritev = _najdi(t, "MERITVE", meritev or t.oznake["MERITVE"][0])
    leta = t.oznake["LETO"]
    pogoni = t.oznake["VRSTA POGONA IN GORIVA"]
    skupaj_oznaka = next((p for p in pogoni if SKUPAJ_ZETON in p), None)
    if skupaj_oznaka is None:
        raise NapacenVnos("tabela nima vrstice SKUPAJ za pogon")

    def v(pogon_, leto):
        return t.vrednost({"LETO": leto, "VRSTA VOZILA": vrsta, "VRSTA POGONA IN GORIVA": pogon_, "MERITVE": meritev})

    skupaj = [v(skupaj_oznaka, l) for l in leta]
    serije = []
    for p in pogoni:
        if p == skupaj_oznaka:
            continue
        stevila = [v(p, l) for l in leta]
        serije.append({"pogon": p, "stevilo": [_zaokrozi(x, 0) for x in stevila],
                       "delez": [_delez(x, s) for x, s in zip(stevila, skupaj)]})
    return {"vrsta": vrsta, "meritev": meritev, "leta": leta, "skupaj": [_zaokrozi(x, 0) for x in skupaj], "serije": serije}


# ---------------------------------------------------------------------------
# 4. Poti po prevoznih sredstvih, MOL in MOM (2281296S)
# ---------------------------------------------------------------------------

SKUPAJ_POTI = "Glavno prevozno sredstvo - SKUPAJ"
GLAVNI_NACINI = ["Osebni avto - skupaj", "Avtobus - skupaj", "Vlak", "Kolo", "Peš, tek",
                 "Motorno kolo, moped", "Taksi", "Kombi, avtodom", "Drugo prevozno sredstvo"]
VOZNIK, SOPOTNIK = "..osebni avto kot voznik", "..osebni avto kot sopotnik"


def potovanja(t: PxTabela, leto: str) -> Dict[str, object]:
    """Za vsako mestno občino: število poti po načinih (v 1000), delež (%) in povprečna zasedenost avtomobila."""
    leto = _najdi(t, "LETO", leto)
    rezultat = []
    for mo in t.oznake["MESTNA OBČINA"]:
        def v(nacin):
            return t.vrednost({"MESTNA OBČINA": mo, "GLAVNO PREVOZNO SREDSTVO": nacin, "LETO": leto})
        skupaj = v(SKUPAJ_POTI)
        nacini = [{"nacin": n, "stevilo": _zaokrozi(v(n), 0), "delez": _delez(v(n), skupaj)} for n in GLAVNI_NACINI]
        voznik, sopotnik = v(VOZNIK), v(SOPOTNIK)
        zasedenost = round((voznik + sopotnik) / voznik, 2) if voznik and sopotnik is not None else None
        rezultat.append({"mestnaObcina": mo, "skupaj": _zaokrozi(skupaj, 0), "nacini": nacini,
                         "zasedenostAvta": zasedenost, "potiKotVoznik": _zaokrozi(voznik, 0)})
    return {"leto": leto, "enota": t.enota, "obcine": rezultat}


# ---------------------------------------------------------------------------
# 5. Kje parkirajo zaposleni, ki na delo pridejo z avtom (2281931S)
# ---------------------------------------------------------------------------

def _skupina_parkiranja(oznaka: str) -> str:
    """Združi sedem kategorij v štiri skupine, ki jih potrebuje aplikacija za iskanje parkirišč."""
    if "SKUPAJ" in oznaka:
        return "skupaj"
    if "podjetja" in oznaka:
        return "Pri delodajalcu"
    if "P&R" in oznaka:
        return "P+R"
    if "javn" in oznaka:   # »javnem parkirišču« ter »ob cesti ali ... javni površini«
        return "Javno (ob cesti, javno parkirišče)"
    return "Drugje"


def parkiranje(t: PxTabela, leto: str, spol: str = "TOT") -> Dict[str, object]:
    leto = _najdi(t, "LETO", leto)
    spol = _najdi(t, "SPOL", spol)
    podrobno, skupine, skupaj = [], {}, None
    for kraj in t.oznake["KRAJ PARKIRANJA"]:
        v = t.vrednost({"KRAJ PARKIRANJA": kraj, "LETO": leto, "SPOL": spol})
        g = _skupina_parkiranja(kraj)
        if g == "skupaj":
            skupaj = v
            continue
        podrobno.append({"kraj": kraj, "skupina": g, "stevilo": _zaokrozi(v, 0)})
        if v is not None:
            skupine[g] = skupine.get(g, 0) + v
    for p in podrobno:
        p["delez"] = _delez(p["stevilo"], skupaj)
    return {"leto": leto, "spol": spol, "enota": t.enota, "skupaj": _zaokrozi(skupaj, 0), "podrobno": podrobno,
            "skupine": [{"skupina": g, "stevilo": _zaokrozi(s, 0), "delez": _delez(s, skupaj)} for g, s in skupine.items()]}
