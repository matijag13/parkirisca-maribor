"""Razredi za JSON: vnos uporabnika in odgovor modela (Pydantic preveri obliko in tipe)."""

from datetime import date
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class Vnos(BaseModel):
    """Podatki iz obrazca."""

    cilj: str = Field(min_length=2, max_length=120)
    datum: date
    ura: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    trajanje_ur: float = Field(ge=0.5, le=12)
    namen: Literal["nakupovanje", "delo", "obisk zdravnika", "restavracija ali kultura", "drugo"]
    vozilo: Literal["osebni avto", "električni avto", "avtodom"] = "osebni avto"
    max_pes_min: int = Field(default=10, ge=1, le=30)

    @field_validator("cilj")
    @classmethod
    def _cilj(cls, v: str) -> str:
        return v.strip()


class Priporocilo(BaseModel):
    """Eno priporočilo, kot ga vrne model."""

    ime: str
    tip: Literal["ograjeno", "bela cona", "drugo"]
    razlog: str
    ocenjena_cena_eur: Optional[float] = None
    pes_minut: Optional[int] = None


class OdgovorLLM(BaseModel):
    """JSON, ki ga zahtevamo od modela. Vsak odgovor, ki se ne ujema, zavrnemo in model vprašamo še enkrat."""

    povzetek: str
    priporocila: List[Priporocilo] = Field(min_length=1, max_length=3)
    opozorilo: Optional[str] = None
