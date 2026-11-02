"""Prenos PX datotek s portala SiStat (Statistični urad RS) z predpomnilnikom na disku in v pomnilniku."""

import logging
import threading
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

import requests

import pcaxis

URL = "https://pxweb.stat.si/SiStatData/Resources/PX/Databases/Data/{koda}.PX"
UA = "TIDS-student-projekt/1.0 (Maribor parkirisca; PX prenos)"
log = logging.getLogger("sistat")


class ViraNapaka(RuntimeError):
    """Tabele ni bilo mogoče pridobiti (ni omrežja in ni predpomnilnika)."""


class Vir:
    """Vrne razčlenjeno PX tabelo po kodi (npr. '2222105S').

    Vrstni red iskanja:
      1. razčlenjena tabela v pomnilniku (ne starejša od `max_starost_ur`),
      2. datoteka v lokalni mapi `lokalna_mapa` (za razvoj brez interneta in za teste),
      3. datoteka v `cache_mapa`, če ni starejša od `max_starost_ur`,
      4. prenos s SiStat; če ta ne uspe, uporabimo tudi starejšo datoteko iz predpomnilnika.
    """

    def __init__(self, cache_mapa: Path, lokalna_mapa: Optional[Path] = None, max_starost_ur: float = 24.0,
                 seja: Optional[requests.Session] = None):
        self.cache_mapa = Path(cache_mapa)
        self.lokalna_mapa = Path(lokalna_mapa) if lokalna_mapa else None
        self.max_starost_s = max_starost_ur * 3600
        self.seja = seja or requests.Session()
        self._pomnilnik: Dict[str, Tuple[float, pcaxis.PxTabela]] = {}
        self._kljuc = threading.Lock()

    def tabela(self, koda: str) -> pcaxis.PxTabela:
        with self._kljuc:
            videno = self._pomnilnik.get(koda)
            if videno and time.time() - videno[0] < self.max_starost_s:
                return videno[1]
            vsebina = self._preberi_bajte(koda)
            tabela = pcaxis.razcleni_bajte(vsebina)
            self._pomnilnik[koda] = (time.time(), tabela)
            return tabela

    # ------------------------------------------------------------------
    def _preberi_bajte(self, koda: str) -> bytes:
        if self.lokalna_mapa:
            pot = self.lokalna_mapa / f"{koda}.px"
            if not pot.exists():
                raise ViraNapaka(f"lokalna datoteka ne obstaja: {pot}")
            return pot.read_bytes()

        pot = self.cache_mapa / f"{koda}.px"
        if pot.exists() and time.time() - pot.stat().st_mtime < self.max_starost_s:
            return pot.read_bytes()
        try:
            odgovor = self.seja.get(URL.format(koda=koda), headers={"User-Agent": UA}, timeout=60)
            odgovor.raise_for_status()
        except requests.RequestException as napaka:
            if pot.exists():
                log.warning("prenos %s ni uspel (%s); uporabljam starejši predpomnilnik", koda, napaka)
                return pot.read_bytes()
            raise ViraNapaka(f"prenos tabele {koda} ni uspel: {napaka}") from napaka
        self.cache_mapa.mkdir(parents=True, exist_ok=True)
        pot.write_bytes(odgovor.content)
        return odgovor.content
