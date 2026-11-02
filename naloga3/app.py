"""FastAPI strežnik: iz PX tabel SURS izračuna JSON za grafe; statična stran jih naloži ob odprtju.

Zagon:  py app.py            (nato odpri http://127.0.0.1:8000)
        py app.py --lokalno tests/fixtures   (brez interneta, z majhnimi testnimi tabelami)
"""

import argparse
import os
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import analiza as a
from sistat import Vir, ViraNapaka

MAPA = Path(__file__).resolve().parent
STATIC = MAPA / "static"

VIRI = [
    {"koda": a.T_VOZILA, "opis": "Cestna vozila konec leta po vrsti vozila, občinah in letih"},
    {"koda": a.T_POGON, "opis": "Vozila po vrsti pogona in goriva"},
    {"koda": a.T_MOTORIZACIJA, "opis": "Nekateri kazalniki transporta po občinah (stopnja motorizacije)"},
    {"koda": a.T_POTI, "opis": "Letno število poti v MO Ljubljana in MO Maribor po glavnem prevoznem sredstvu"},
    {"koda": a.T_PARKIRANJE, "opis": "Kraj parkiranja osebnega avtomobila, uporabljenega za pot na delo"},
]


def ustvari_app(vir: Vir) -> FastAPI:
    app = FastAPI(title="Promet in parkiranje v Mariboru: podatki SURS (PC-Axis)")

    @app.exception_handler(a.NapacenVnos)
    async def _napacen_vnos(_, napaka):
        return JSONResponse(status_code=404, content={"napaka": str(napaka)})

    @app.exception_handler(ViraNapaka)
    async def _vir(_, napaka):
        return JSONResponse(status_code=502, content={"napaka": str(napaka)})

    @app.get("/api/meta")
    def meta():
        """Viri, licenca in datum zadnje posodobitve vsake tabele."""
        viri = []
        for v in VIRI:
            t = vir.tabela(v["koda"])
            viri.append({**v, "naslov": t.naslov, "enota": t.enota, "zadnjaPosodobitev": t.meta.get("last_updated"),
                         "url": f"https://pxweb.stat.si/SiStatData/pxweb/sl/Data/-/{v['koda']}.px"})
        return {"izdajatelj": "Statistični urad Republike Slovenije (SURS)", "licenca": "CC BY 4.0",
                "opis": "Odprti podatki v formatu PC-Axis, katalog: podatki.gov.si", "viri": viri}

    # --- vozni park ---------------------------------------------------
    @app.get("/api/vozila/izbire")
    def vozila_izbire():
        return a.izbire_vozil(vir.tabela(a.T_VOZILA))

    @app.get("/api/vozila/trend")
    def vozila_trend(obcina: str = a.PRIVZETA_OBCINA, vrste: List[str] = Query(default=[]), od: Optional[str] = None):
        t = vir.tabela(a.T_VOZILA)
        return a.vozni_park(t, obcina, vrste or a.izbire_vozil(t)["privzeto"]["vrste"], od)

    @app.get("/api/vozila/lestvica")
    def vozila_lestvica(leto: Optional[str] = None, vrsta: Optional[str] = None,
                        top: int = Query(10, ge=1, le=50), obcina: str = a.PRIVZETA_OBCINA):
        t = vir.tabela(a.T_VOZILA)
        vrsta = vrsta or a.izbire_vozil(t)["privzeto"]["vrste"][0]
        return a.lestvica_vozil(t, leto or a.zadnje_leto(t), vrsta, top, obcina)

    # --- motorizacija ------------------------------------------------------
    @app.get("/api/motorizacija/trend")
    def motorizacija_trend(obcine: List[str] = Query(default=[a.PRIVZETA_OBCINA, "Ljubljana", a.SLOVENIJA])):
        return a.motorizacija(vir.tabela(a.T_MOTORIZACIJA), obcine)

    @app.get("/api/motorizacija/lestvica")
    def motorizacija_lestvica(leto: Optional[str] = None, top: int = Query(10, ge=1, le=50), obcina: str = a.PRIVZETA_OBCINA):
        t = vir.tabela(a.T_MOTORIZACIJA)
        return a.lestvica_motorizacije(t, leto or a.zadnje_leto(t), top, obcina)

    # --- pogon -----------------------------------------------------------------
    @app.get("/api/pogon/izbire")
    def pogon_izbire():
        return a.izbire_pogona(vir.tabela(a.T_POGON))

    @app.get("/api/pogon")
    def pogon(vrsta: Optional[str] = None, meritev: Optional[str] = None):
        t = vir.tabela(a.T_POGON)
        return a.pogon(t, vrsta or a.izbire_pogona(t)["privzeto"]["vrsta"], meritev)

    # --- poti in parkiranje -----------------------------------------------------
    @app.get("/api/poti")
    def poti(leto: Optional[str] = None):
        t = vir.tabela(a.T_POTI)
        return {**a.potovanja(t, leto or a.zadnje_leto(t)), "leta": t.oznake["LETO"]}

    @app.get("/api/parkiranje")
    def parkiranje(leto: Optional[str] = None, spol: str = "TOT"):
        t = vir.tabela(a.T_PARKIRANJE)
        return {**a.parkiranje(t, leto or a.zadnje_leto(t), spol), "leta": t.oznake["LETO"], "spoli": t.oznake["SPOL"]}

    # --- povzetek za kartice na vrhu strani ---------------------------------------
    @app.get("/api/povzetek")
    def povzetek():
        """Nekaj ključnih števil za Maribor (zadnje leto v vsaki tabeli)."""
        tv, tm = vir.tabela(a.T_VOZILA), vir.tabela(a.T_MOTORIZACIJA)
        tp, tpot, tpark = vir.tabela(a.T_POGON), vir.tabela(a.T_POTI), vir.tabela(a.T_PARKIRANJE)
        vrsta = a.izbire_vozil(tv)["privzeto"]["vrste"][0]
        leto_v = a.zadnje_leto(tv)
        lest = a.lestvica_vozil(tv, leto_v, vrsta, 1)
        mar = next(p for p in lest["postavke"] if p["obcina"] == a.PRIVZETA_OBCINA)
        mot = a.lestvica_motorizacije(tm, a.zadnje_leto(tm), 1)
        mar_mot = next(p for p in mot["postavke"] if p["obcina"] == a.PRIVZETA_OBCINA)
        pogon_ = a.pogon(tp, a.izbire_pogona(tp)["privzeto"]["vrsta"])
        elektrika = next((s for s in pogon_["serije"] if "lektri" in s["pogon"]), None)
        poti_ = next(o for o in a.potovanja(tpot, a.zadnje_leto(tpot))["obcine"] if o["mestnaObcina"] == a.PRIVZETA_OBCINA)
        avto = next(n for n in poti_["nacini"] if n["nacin"].startswith("Osebni avto"))
        park = a.parkiranje(tpark, a.zadnje_leto(tpark))
        javno = next((s for s in park["skupine"] if s["skupina"].startswith("Javno")), None)
        return {
            "vozila": {"leto": leto_v, "vrsta": vrsta, "stevilo": mar["vrednost"], "rang": mar["rang"], "delezVSloveniji": mar["delezVSloveniji"]},
            "motorizacija": {"leto": mot["leto"], "vrednost": mar_mot["vrednost"], "slovenija": mot["slovenija"], "rang": mar_mot["rang"]},
            "elektrika": {"leto": pogon_["leta"][-1], "delez": elektrika["delez"][-1] if elektrika else None},
            "poti": {"leto": a.zadnje_leto(tpot), "delezAvto": avto["delez"], "zasedenostAvta": poti_["zasedenostAvta"]},
            "parkiranje": {"leto": park["leto"], "delezJavno": javno["delez"] if javno else None},
        }

    @app.get("/")
    def domov():
        return FileResponse(STATIC / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


def vir_iz_okolja() -> Vir:
    lokalno = os.environ.get("PX_LOKALNO")
    return Vir(MAPA / ".cache" / "px", Path(lokalno) if lokalno else None)


app = ustvari_app(vir_iz_okolja())


def main() -> None:
    import uvicorn

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lokalno", help="mapa z datotekami <KODA>.px (brez prenosa s SiStat)")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    if args.lokalno:
        os.environ["PX_LOKALNO"] = str(Path(args.lokalno).resolve())
    uvicorn.run(ustvari_app(vir_iz_okolja()), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
