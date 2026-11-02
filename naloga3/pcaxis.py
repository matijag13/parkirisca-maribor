"""Razčlenjevalnik (parser) formata PC-Axis (.px).

PX datoteka je besedilna. Sestavljena je iz glave (ključne besede, vsaka se konča s podpičjem)
in bloka DATA=, v katerem so vse vrednosti tabele v eni vrsti:

    TITLE="Cestna vozila po: OBČINE, LETO";
    STUB="OBČINE";                 <- spremenljivke po vrsticah
    HEADING="LETO";                <- spremenljivke po stolpcih
    VALUES("LETO")="2023","2024";  <- vrednosti (oznake) spremenljivke
    DATA=
    100 110
    200 "..";                      <- "..", "..." ali "." pomeni manjkajoč podatek

Vrstni red števil: prva STUB spremenljivka se spreminja najpočasneje, zadnja HEADING najhitreje.
Zato je indeks v ploščatem seznamu enak vsoti (indeks vrednosti * korak) po vseh dimenzijah.

Koda je namenoma brez zunanjih knjižnic, da je vsak korak razložljiv.
"""

import re
from dataclasses import dataclass, field
from itertools import product
from typing import Dict, Iterator, List, Optional, Tuple


class PxNapaka(ValueError):
    """Datoteka ni veljavna PX datoteka (ali uporablja nepodprt del formata)."""


# ---------------------------------------------------------------------------
# 1. Razčlenitev glave
# ---------------------------------------------------------------------------

def _razdeli_stavke(besedilo: str) -> Tuple[List[Tuple[str, str]], str]:
    """Razreže glavo na stavke KLJUČ=VREDNOST; ter vrne tudi surovi blok DATA.

    Podpičje velja kot konec stavka samo zunaj narekovajev (v opombah se pojavljajo tudi
    podpičja v besedilu). Zato gremo po znakih in si zapomnimo, ali smo znotraj narekovajev.
    """
    stavki: List[Tuple[str, str]] = []
    zacetek = 0
    v_narekovajih = False
    i = 0
    n = len(besedilo)
    while i < n:
        c = besedilo[i]
        if c == '"':
            v_narekovajih = not v_narekovajih
        elif c == ";" and not v_narekovajih:
            stavki.append(_loci_kljuc(besedilo[zacetek:i]))
            zacetek = i + 1
        elif not v_narekovajih and besedilo.startswith("DATA=", i) and besedilo[zacetek:i].strip() == "":
            # blok DATA: preberemo do naslednjega podpičja (števila ne vsebujejo podpičij)
            konec = besedilo.find(";", i)
            if konec == -1:
                konec = n
            return stavki, besedilo[i + 5:konec]
        i += 1
    raise PxNapaka("v datoteki ni bloka DATA=")


def _loci_kljuc(stavek: str) -> Tuple[str, str]:
    """'KEY[lang]("podatrib")=vrednost' -> ('KEY[lang]("podatrib")', 'vrednost'); '=' mora biti zunaj narekovajev."""
    v_narekovajih = False
    for i, c in enumerate(stavek):
        if c == '"':
            v_narekovajih = not v_narekovajih
        elif c == "=" and not v_narekovajih:
            return stavek[:i].strip(), stavek[i + 1:]
    raise PxNapaka(f"stavek brez '=': {stavek[:60]!r}")


_KLJUC = re.compile(r'^([A-Za-z0-9\-]+)(?:\[([A-Za-z\-]+)\])?(?:\((.*)\))?$', re.S)


def _razcleni_kljuc(kljuc: str) -> Tuple[str, Optional[str], List[str]]:
    """'VALUES[en]("LETO")' -> ('VALUES', 'en', ['LETO'])."""
    m = _KLJUC.match(kljuc.strip())
    if not m:
        raise PxNapaka(f"neveljavna ključna beseda: {kljuc[:60]!r}")
    ime, jezik, podatrib = m.groups()
    return ime.upper(), jezik, (razcleni_seznam(podatrib) if podatrib else [])


def razcleni_seznam(surovo: str) -> List[str]:
    """Razčleni seznam vrednosti: "a","b" ali "dolgo besedilo, "\\n"nadaljevanje", 0, YES.

    * elementi so ločeni z vejicami (zunaj narekovajev),
    * več narekovanih nizov, ločenih samo s presledki/novo vrstico, je en sam niz (daljši nizi so v PX prelomljeni),
    * nenarekovani element (YES, 0, TLIST(A1,...)) se vrne kot besedilo.
    """
    elementi: List[str] = []
    i, n = 0, len(surovo)
    while i < n:
        while i < n and surovo[i] in " \t\r\n,":
            i += 1
        if i >= n:
            break
        if surovo[i] == '"':
            deli = []
            while i < n and surovo[i] == '"':
                konec = surovo.find('"', i + 1)
                if konec == -1:
                    raise PxNapaka("neskončan niz v narekovajih")
                deli.append(surovo[i + 1:konec])
                i = konec + 1
                j = i
                while j < n and surovo[j] in " \t\r\n":
                    j += 1
                if j < n and surovo[j] == '"':
                    i = j  # nadaljevanje istega niza v naslednji vrstici
                else:
                    break
            elementi.append("".join(deli))
        else:
            globina = 0
            j = i
            while j < n and not (surovo[j] == "," and globina == 0):
                if surovo[j] == "(":
                    globina += 1
                elif surovo[j] == ")":
                    globina -= 1
                j += 1
            elementi.append(surovo[i:j].strip())
            i = j
    return elementi


# ---------------------------------------------------------------------------
# 2. Razčlenitev podatkov
# ---------------------------------------------------------------------------

_PODATEK = re.compile(r'"[^"]*"|[^\s"]+')


def razcleni_podatke(surovo: str) -> List[Optional[float]]:
    """Pretvori blok DATA v seznam števil; simboli ("..", "...", "-") postanejo None."""
    rezultat: List[Optional[float]] = []
    for zeton in _PODATEK.findall(surovo):
        if zeton.startswith('"'):
            rezultat.append(None)
            continue
        try:
            rezultat.append(float(zeton))
        except ValueError:
            # nekatere datoteke zapišejo manjkajoče kot golo piko ali pomišljaj
            if zeton in {".", "..", "...", "-", "--"}:
                rezultat.append(None)
            else:
                raise PxNapaka(f"neveljavno število v DATA: {zeton!r}")
    return rezultat


# ---------------------------------------------------------------------------
# 3. Tabela
# ---------------------------------------------------------------------------

@dataclass
class PxTabela:
    """Razčlenjena PX datoteka."""

    naslov: str
    enota: str
    stub: List[str]
    heading: List[str]
    oznake: Dict[str, List[str]]   # spremenljivka -> oznake vrednosti (npr. "Maribor", "2024")
    kode: Dict[str, List[str]]     # spremenljivka -> kode vrednosti (če jih datoteka nima, so enake oznakam)
    podatki: List[Optional[float]]
    meta: Dict[str, str] = field(default_factory=dict)  # izbrane ključne besede (vir, datum posodobitve, ...)

    # --- zgradba ---------------------------------------------------------
    @property
    def dimenzije(self) -> List[str]:
        """Vrstni red dimenzij v podatkih: najprej STUB, nato HEADING."""
        return self.stub + self.heading

    @property
    def koraki(self) -> List[int]:
        """Koliko mest v seznamu preskočimo, ko se vrednost dimenzije poveča za 1."""
        koraki, korak = [], 1
        for ime in reversed(self.dimenzije):
            koraki.append(korak)
            korak *= len(self.oznake[ime])
        return list(reversed(koraki))

    def indeks_vrednosti(self, spremenljivka: str, izbira: str) -> int:
        """Poišče položaj vrednosti: točna oznaka, točna koda, nato oznaka, ki se začne z izbiro.

        Primer: izbira "1.31" najde "1.31 Navadni osebni avtomobili", čeprav obstaja tudi "1.3 Osebni ...".
        """
        if spremenljivka not in self.oznake:
            raise KeyError(f"neznana spremenljivka: {spremenljivka!r}")
        oznake, kode = self.oznake[spremenljivka], self.kode[spremenljivka]
        if izbira in oznake:
            return oznake.index(izbira)
        if izbira in kode:
            return kode.index(izbira)
        for predpona in (izbira + " ", izbira):
            zadetki = [i for i, o in enumerate(oznake) if o.startswith(predpona)]
            if len(zadetki) == 1:
                return zadetki[0]
            if len(zadetki) > 1:
                raise KeyError(f"izbira {izbira!r} je dvoumna pri {spremenljivka!r}: {[oznake[i] for i in zadetki]}")
        raise KeyError(f"vrednosti {izbira!r} ni pri {spremenljivka!r}")

    # --- branje ----------------------------------------------------------
    def vrednost(self, izbor: Dict[str, str]) -> Optional[float]:
        """Ena celica; `izbor` mora določiti vrednost za vsako dimenzijo."""
        manjka = [d for d in self.dimenzije if d not in izbor]
        if manjka:
            raise KeyError(f"manjkajo dimenzije: {manjka}")
        indeks = sum(self.indeks_vrednosti(d, izbor[d]) * k for d, k in zip(self.dimenzije, self.koraki))
        return self.podatki[indeks]

    def serija(self, spremenljivka: str, izbor: Dict[str, str]) -> List[Tuple[str, Optional[float]]]:
        """Vrednosti vzdolž ene dimenzije; ostale dimenzije določa `izbor` (filtriranje)."""
        ostale = {d: v for d, v in izbor.items() if d != spremenljivka}
        return [(o, self.vrednost({**ostale, spremenljivka: o})) for o in self.oznake[spremenljivka]]

    def vrstice(self) -> Iterator[Dict[str, object]]:
        """Vsaka celica kot slovar {dimenzija: oznaka, ..., 'vrednost': x} (za izvoz in preverjanje)."""
        kombinacije = product(*[self.oznake[d] for d in self.dimenzije])
        for kombinacija, vrednost in zip(kombinacije, self.podatki):
            vrstica: Dict[str, object] = dict(zip(self.dimenzije, kombinacija))
            vrstica["vrednost"] = vrednost
            yield vrstica


_META_KLJUCI = ("MATRIX", "SOURCE", "LAST-UPDATED", "CREATION-DATE", "CONTACT", "DESCRIPTION", "SUBJECT-AREA", "CONTENTS")


def razcleni(besedilo: str) -> PxTabela:
    """Razčleni vsebino PX datoteke (že dekodirano v besedilo)."""
    stavki, surovi_podatki = _razdeli_stavke(besedilo)

    # privzeti jezik: LANGUAGE="sl"; ključne besede z drugimi jeziki (npr. TITLE[en]) preskočimo
    privzeti = None
    for kljuc, vrednost in stavki:
        if kljuc.upper() == "LANGUAGE":
            privzeti = (razcleni_seznam(vrednost) or [None])[0]
            break

    enojni: Dict[str, List[str]] = {}
    oznake: Dict[str, List[str]] = {}
    kode: Dict[str, List[str]] = {}
    for kljuc, vrednost in stavki:
        ime, jezik, podatrib = _razcleni_kljuc(kljuc)
        if jezik is not None and jezik != privzeti:
            continue
        seznam = razcleni_seznam(vrednost)
        if ime == "VALUES" and podatrib:
            oznake[podatrib[0]] = seznam
        elif ime == "CODES" and podatrib:
            kode[podatrib[0]] = seznam
        elif not podatrib:
            enojni[ime] = seznam

    for obvezno in ("TITLE", "STUB", "HEADING"):
        if obvezno not in enojni and not (obvezno == "STUB" and "HEADING" in enojni):
            raise PxNapaka(f"manjka obvezna beseda {obvezno}")

    stub = enojni.get("STUB", [])
    heading = enojni.get("HEADING", [])
    for d in stub + heading:
        if d not in oznake:
            raise PxNapaka(f"manjka VALUES za spremenljivko {d!r}")
    for d in oznake:
        k = kode.get(d)
        if k is None:
            kode[d] = list(oznake[d])
        elif len(k) != len(oznake[d]):
            raise PxNapaka(f"CODES in VALUES se pri {d!r} ne ujemata po dolžini")

    podatki = razcleni_podatke(surovi_podatki)
    pricakovano = 1
    for d in stub + heading:
        pricakovano *= len(oznake[d])
    if len(podatki) != pricakovano:
        raise PxNapaka(f"število podatkov ({len(podatki)}) ni enako produktu dimenzij ({pricakovano})")

    meta = {k.lower().replace("-", "_"): " ".join(enojni[k]) for k in _META_KLJUCI if k in enojni}
    return PxTabela(
        naslov=" ".join(enojni["TITLE"]),
        enota=" ".join(enojni.get("UNITS", [])),
        stub=stub,
        heading=heading,
        oznake={d: oznake[d] for d in stub + heading},
        kode={d: kode[d] for d in stub + heading},
        podatki=podatki,
        meta=meta,
    )


def razcleni_bajte(vsebina: bytes) -> PxTabela:
    """Dekodira bajte s kodno tabelo iz CODEPAGE (SURS uporablja windows-1250) in razčleni."""
    glava = vsebina[:2000].decode("ascii", errors="ignore")
    m = re.search(r'CODEPAGE\s*=\s*"([^"]+)"', glava)
    kodiranje = m.group(1) if m else "windows-1250"
    if kodiranje.upper() == "ANSI":
        kodiranje = "windows-1250"
    return razcleni(vsebina.decode(kodiranje))
