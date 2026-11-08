"""FastAPI: iz obrazca sestavi vprašanje za LLM, odgovor pretvori v JSON razred in ga vrne strani.

Zagon:  py app.py     (potrebuje GROQ_API_KEY v datoteki .env, glej README)
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import geo
import kontekst
import llm
import prompt
import vreme
from modeli import Vnos

MAPA = Path(__file__).resolve().parent
STATIC = MAPA / "static"


class NapakaVnosa(ValueError):
    pass


def nalozi_env(pot: Path) -> None:
    """Prebere .env (KLJUČ=vrednost) v okolje; obstoječih spremenljivk ne prepiše."""
    if not pot.exists():
        return
    for vrstica in pot.read_text(encoding="utf-8").splitlines():
        vrstica = vrstica.strip()
        if vrstica and not vrstica.startswith("#") and "=" in vrstica:
            k, v = vrstica.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def ustvari_app(klic: Optional[llm.Klic], geokodiraj: Callable = geo.geokodiraj, napoved: Callable = vreme.napoved,
                cenik: Optional[dict] = None) -> FastAPI:
    app = FastAPI(title="Svetovalec za parkiranje v Mariboru (LLM)")
    cenik = cenik or kontekst.nalozi_cenik()

    @app.exception_handler(NapakaVnosa)
    async def _vnos(_, n):
        return JSONResponse(status_code=404, content={"napaka": str(n)})

    @app.exception_handler(llm.LlmNapaka)
    async def _llm(_, n):
        return JSONResponse(status_code=502, content={"napaka": str(n)})

    @app.get("/api/stanje")
    def stanje():
        return {"llmNastavljen": klic is not None, "model": os.environ.get("GROQ_MODEL") or "samodejno"}

    @app.get("/api/modeli")
    def modeli():
        """Pomožna stran: kateri modeli so na voljo in kateri bo izbran (ključa ne izpiše)."""
        kljuc = os.environ.get("GROQ_API_KEY")
        if not kljuc:
            raise llm.LlmNapaka("GROQ_API_KEY ni nastavljen")
        return {"modeli": llm.seznam_modelov(kljuc), "izbran": os.environ.get("GROQ_MODEL") or llm.izberi_model(kljuc)}

    @app.post("/api/priporoci")
    def priporoci(vnos: Vnos):
        if klic is None:
            raise llm.LlmNapaka("GROQ_API_KEY ni nastavljen (glej README, korak .env)")
        cilj = geokodiraj(vnos.cilj)
        if cilj is None:
            raise NapakaVnosa(f"naslova »{vnos.cilj}« ni mogoče najti v Mariboru")

        ura = int(vnos.ura[:2])
        try:
            vreme_ = napoved(cilj[0], cilj[1], vnos.datum, ura)
        except Exception:   # vreme je dodatek; ob napaki nadaljujemo brez njega
            vreme_ = None

        opcije = kontekst.zberi_opcije(vnos, cilj, cenik, geokodiraj)
        for o in opcije:
            o["znotraj_omejitve_hoje"] = None if o["pes_minut"] is None else o["pes_minut"] <= vnos.max_pes_min

        sporocila = prompt.sestavi(vnos, vreme_, opcije, kontekst.opisi_placljivost(cenik))
        odgovor = llm.pridobi_odgovor(klic, sporocila)

        # model sme izbirati samo med našimi možnostmi; številke vedno vzamemo iz izračuna, ne iz besedila modela
        po_imenu: Dict[str, dict] = {o["ime"]: o for o in opcije}
        opozorila: List[str] = []
        veljavna = []
        for p in odgovor.priporocila:
            o = po_imenu.get(p.ime)
            if o is None:
                opozorila.append(f"Model je predlagal »{p.ime}«, ki ni na seznamu možnosti; priporočilo je izpuščeno.")
                continue
            p.tip, p.ocenjena_cena_eur, p.pes_minut = o["tip"], o["ocenjena_cena_eur"], o["pes_minut"]
            veljavna.append(p)
        if not veljavna:
            raise llm.LlmNapaka("model ni predlagal nobene veljavne možnosti")
        odgovor.priporocila = veljavna

        return {"vnos": vnos.model_dump(mode="json"), "cilj": {"lat": cilj[0], "lon": cilj[1]}, "vreme": vreme_,
                "opcije": opcije, "prompt": sporocila, "odgovor": odgovor.model_dump(), "opozorila": opozorila}

    @app.get("/")
    def domov():
        return FileResponse(STATIC / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


def main() -> None:
    import uvicorn

    nalozi_env(MAPA / ".env")
    uvicorn.run(ustvari_app(llm.klic_iz_okolja()), host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
