"""Sestavljanje vprašanja (prompt) za model iz vnosa uporabnika, vremena in izračunanih dejstev."""

import json
from typing import Dict, List, Optional

from modeli import Vnos

DNEVI = ["ponedeljek", "torek", "sreda", "četrtek", "petek", "sobota", "nedelja"]

SISTEM = """Si svetovalec za parkiranje v Mariboru. Odgovarjaš samo v slovenščini.
Priporoči od 1 do 3 parkirne možnosti IZKLJUČNO izmed možnosti, ki so navedene v vprašanju (polje "ime" mora biti
natanko enako imenu iz seznama). Ne izmišljaj parkirišč, cen ali razdalj; uporabljaj podane številke.
Odgovori SAMO z veljavnim JSON brez dodatnega besedila, v tej obliki:
{
  "povzetek": "en do dva stavka",
  "priporocila": [
    {"ime": "...", "tip": "ograjeno | bela cona | drugo", "razlog": "kratka utemeljitev",
     "ocenjena_cena_eur": 0.0, "pes_minut": 0}
  ],
  "opozorilo": "neobvezno opozorilo ali null"
}"""


def vreme_besedilo(vreme: Optional[Dict[str, object]]) -> str:
    if not vreme:
        return "napoved ni na voljo"
    return (f"{vreme['opis']}, {vreme['temperatura_c']} °C, verjetnost padavin {vreme['verjetnost_padavin_pct']} %, "
            f"padavine {vreme['padavine_mm']} mm")


def sestavi(vnos: Vnos, vreme: Optional[Dict[str, object]], opcije: List[Dict[str, object]], placljivost: str) -> List[Dict[str, str]]:
    """Vrne seznam sporočil [{role, content}] za pogovorni API."""
    dan = DNEVI[vnos.datum.weekday()]
    uporabnik = (
        f"Cilj: {vnos.cilj}\n"
        f"Datum in ura prihoda: {dan}, {vnos.datum.strftime('%d. %m. %Y')} ob {vnos.ura}\n"
        f"Predvideno trajanje parkiranja: {vnos.trajanje_ur} ur\n"
        f"Namen obiska: {vnos.namen}\n"
        f"Vozilo: {vnos.vozilo}\n"
        f"Največ, kar je uporabnik pripravljen hoditi: {vnos.max_pes_min} minut\n"
        f"Vreme ob prihodu: {vreme_besedilo(vreme)}\n"
        f"Parkiranje je plačljivo: {placljivost}\n\n"
        f"Možnosti (dejstva so izračunana, ne popravljaj jih):\n{json.dumps(opcije, ensure_ascii=False, indent=1)}\n\n"
        f"Predlagaj najboljše možnosti za {vnos.namen} v {dan}, "
        f"upoštevaj vreme ({vreme['opis'] if vreme else 'neznano'}), vozilo ({vnos.vozilo}) in omejitev hoje."
    )
    return [{"role": "system", "content": SISTEM}, {"role": "user", "content": uporabnik}]
