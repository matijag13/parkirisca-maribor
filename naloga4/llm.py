"""Klic ponudnika LLM (Groq, združljiv z OpenAI) in razčlenitev odgovora v razred OdgovorLLM."""

import json
import os
import re
from typing import Callable, Dict, List, Optional

import requests
from pydantic import ValidationError

from modeli import OdgovorLLM

URL = "https://api.groq.com/openai/v1/chat/completions"
URL_MODELI = "https://api.groq.com/openai/v1/models"
PRIVZETI_MODEL = "llama-3.3-70b-versatile"   # uporabi se samo, če seznama modelov ni mogoče prebrati
IZKLJUCI = ("guard", "whisper", "tts", "orpheus", "safeguard", "embed")


class LlmNapaka(RuntimeError):
    """Klic modela ni uspel ali je odgovor neuporaben."""


Klic = Callable[[List[Dict[str, str]]], str]


def seznam_modelov(kljuc: str, seja=requests) -> List[str]:
    """Imena aktivnih modelov pri Groq; ob napaki sproži LlmNapaka z razlogom."""
    try:
        r = seja.get(URL_MODELI, timeout=20, headers={"Authorization": f"Bearer {kljuc}"})
    except Exception as napaka:
        raise LlmNapaka(f"Groq: seznama modelov ni mogoče prebrati ({napaka})") from napaka
    if r.status_code >= 400:
        raise LlmNapaka(f"Groq: seznam modelov, napaka {r.status_code}: {r.text[:200]}")
    return [m["id"] for m in r.json().get("data", []) if m.get("active", True)]


def izberi_model(kljuc: str, seja=requests) -> str:
    """Iz Groqovega seznama izbere model za pogovor (imena se menjajo, zato ne vpišemo fiksnega).

    Prednost: Llama 70b, nato katera koli Llama, nato prvi model, ki ni namenjen govoru ali varnostnemu filtru.
    """
    ids = seznam_modelov(kljuc, seja)
    pogovorni = [i for i in ids if not any(x in i.lower() for x in IZKLJUCI)]
    llame = [i for i in pogovorni if "llama" in i.lower()]
    for skupina in (llame, pogovorni):
        for oznaka in ("70b", "versatile", ""):
            for i in skupina:
                if oznaka in i.lower():
                    return i
    raise LlmNapaka(f"na Groq ni nobenega primernega modela (seznam: {ids})")


def groq_klic(kljuc: str, model: Optional[str] = None, seja=requests) -> Klic:
    """Vrne funkcijo, ki pošlje sporočila modelu in vrne besedilo odgovora. Model se ob prvem klicu izbere sam."""
    izbran = {"model": model}

    def klici(sporocila: List[Dict[str, str]]) -> str:
        if not izbran["model"]:
            izbran["model"] = izberi_model(kljuc, seja)
        r = seja.post(URL, timeout=60, headers={"Authorization": f"Bearer {kljuc}"},
                      json={"model": izbran["model"], "messages": sporocila, "temperature": 0.3,
                            "response_format": {"type": "json_object"}})
        if r.status_code == 401:
            raise LlmNapaka("Groq: neveljaven API ključ (preveri GROQ_API_KEY v .env)")
        if r.status_code == 429:
            raise LlmNapaka("Groq: presežena omejitev klicev, poskusi čez minuto")
        if r.status_code >= 400:
            raise LlmNapaka(f"Groq: napaka {r.status_code}: {r.text[:300]}")
        return r.json()["choices"][0]["message"]["content"]

    return klici


def klic_iz_okolja() -> Optional[Klic]:
    kljuc = os.environ.get("GROQ_API_KEY")
    if not kljuc:
        return None
    return groq_klic(kljuc, os.environ.get("GROQ_MODEL") or None)


def izlusci_json(besedilo: str) -> dict:
    """Modeli včasih okoli JSON dodajo ```json ... ``` ali besedilo; vzamemo prvi {...} blok."""
    t = besedilo.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    zacetek, konec = t.find("{"), t.rfind("}")
    if zacetek == -1 or konec <= zacetek:
        raise ValueError("v odgovoru ni JSON objekta")
    return json.loads(t[zacetek:konec + 1])


def pridobi_odgovor(klic: Klic, sporocila: List[Dict[str, str]], poskusi: int = 2) -> OdgovorLLM:
    """Pošlje vprašanje, odgovor pretvori v OdgovorLLM; ob napačni obliki modelu pove napako in vpraša znova."""
    pogovor = list(sporocila)
    zadnja = ""
    for _ in range(poskusi):
        surovo = klic(pogovor)
        try:
            return OdgovorLLM.model_validate(izlusci_json(surovo))
        except (ValueError, ValidationError) as napaka:
            zadnja = str(napaka)[:300]
            pogovor += [{"role": "assistant", "content": surovo},
                        {"role": "user", "content": f"Odgovor ni veljaven ({zadnja}). Odgovori znova samo z JSON v zahtevani obliki."}]
    raise LlmNapaka(f"model ni vrnil veljavnega JSON po {poskusi} poskusih: {zadnja}")
