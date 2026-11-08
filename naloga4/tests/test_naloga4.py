import json
import sys
import unittest
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fastapi.testclient import TestClient  # noqa: E402

import app as aplikacija  # noqa: E402
import geo  # noqa: E402
import kontekst  # noqa: E402
import llm  # noqa: E402
import prompt  # noqa: E402
from modeli import Vnos  # noqa: E402

CENIK = kontekst.nalozi_cenik()
CILJ = (46.5547, 15.6459)

TOCKE = {"Rakušev trg": (46.5551, 15.6470), "Mlinska ulica": (46.5570, 15.6420), "Sodna ulica/Ulica talcev": (46.5600, 15.6500)}


def vnos(**kw):
    osnova = dict(cilj="Glavni trg", datum=date(2026, 11, 9), ura="10:00", trajanje_ur=2, namen="nakupovanje")
    osnova.update(kw)
    return Vnos(**osnova)


def gk(naslov):
    return CILJ if naslov == "Glavni trg" else TOCKE.get(naslov)


VELJAVEN = {"povzetek": "Parkiraj na Rakuševem trgu.",
            "priporocila": [{"ime": "Rakušev trg", "tip": "ograjeno", "razlog": "blizu", "ocenjena_cena_eur": 99, "pes_minut": 99}]}


class TestPlacljivost(unittest.TestCase):
    def test_delavnik(self):
        self.assertEqual(kontekst.placljive_ure(datetime(2026, 11, 9, 10), 2, CENIK), 2)   # ponedeljek

    def test_sobota_popoldne_brezplacno(self):
        self.assertEqual(kontekst.placljive_ure(datetime(2026, 11, 14, 14), 3, CENIK), 0)

    def test_sobota_delno(self):
        self.assertEqual(kontekst.placljive_ure(datetime(2026, 11, 14, 11), 4, CENIK), 2)   # 11–13

    def test_nedelja(self):
        self.assertEqual(kontekst.placljive_ure(datetime(2026, 11, 15, 10), 5, CENIK), 0)

    def test_pred_sesto_zjutraj(self):
        self.assertEqual(kontekst.placljive_ure(datetime(2026, 11, 9, 5), 2, CENIK), 1)

    def test_prek_polnoci(self):
        self.assertEqual(kontekst.placljive_ure(datetime(2026, 11, 9, 21), 10, CENIK), 1 + 1)   # pon 21–22, tor 6–7 (konec ob 7:00)


class TestOpcije(unittest.TestCase):
    def test_cena_in_razdalja(self):
        o = {x["ime"]: x for x in kontekst.zberi_opcije(vnos(), CILJ, CENIK, gk)}
        r = o["Rakušev trg"]
        self.assertEqual(r["ocenjena_cena_eur"], 3.2)
        self.assertEqual(r["razdalja_m"], round(geo.razdalja_m(CILJ, TOCKE["Rakušev trg"])))
        self.assertEqual(o["Mlinska ulica"]["mesta_za_ev"], 4)
        self.assertIn("Bela cona (ob cesti)", o)

    def test_nedelja_je_brezplacna(self):
        o = kontekst.zberi_opcije(vnos(datum=date(2026, 11, 15)), CILJ, CENIK, gk)
        self.assertTrue(all(x["ocenjena_cena_eur"] == 0 for x in o))

    def test_manjka_geokodiranje(self):
        o = kontekst.zberi_opcije(vnos(), CILJ, CENIK, lambda n: None)
        self.assertIsNone(o[0]["pes_minut"])


class TestHaversine(unittest.TestCase):
    def test_znana_razdalja(self):
        # 0,01° zemljepisne širine ≈ 1112 m
        self.assertAlmostEqual(geo.razdalja_m((46.0, 15.0), (46.01, 15.0)), 1112, delta=5)


class TestPrompt(unittest.TestCase):
    def test_vsebuje_vnos_in_vreme(self):
        o = kontekst.zberi_opcije(vnos(), CILJ, CENIK, gk)
        vreme = {"opis": "dež", "temperatura_c": 7.5, "verjetnost_padavin_pct": 80, "padavine_mm": 1.2}
        s = prompt.sestavi(vnos(cilj="UKC Maribor", namen="obisk zdravnika"), vreme, o, "delavnik 6–22")
        besedilo = s[1]["content"]
        for v in ("UKC Maribor", "ponedeljek", "10:00", "obisk zdravnika", "dež", "7.5 °C", "Rakušev trg"):
            self.assertIn(v, besedilo)

    def test_razlicen_vnos_razlicen_prompt(self):
        o = kontekst.zberi_opcije(vnos(), CILJ, CENIK, gk)
        a = prompt.sestavi(vnos(), None, o, "x")[1]["content"]
        b = prompt.sestavi(vnos(cilj="FERI", datum=date(2026, 11, 14), vozilo="električni avto"), None, o, "x")[1]["content"]
        self.assertNotEqual(a, b)
        self.assertIn("sobota", b)
        self.assertIn("napoved ni na voljo", a)


class TestJson(unittest.TestCase):
    def test_ograja_s_kodo(self):
        self.assertEqual(llm.izlusci_json('```json\n{"a": 1}\n```'), {"a": 1})

    def test_besedilo_okoli(self):
        self.assertEqual(llm.izlusci_json('Tukaj: {"a": {"b": 2}} lp'), {"a": {"b": 2}})

    def test_brez_jsona(self):
        with self.assertRaises(ValueError):
            llm.izlusci_json("ni jsona")

    def test_ponovni_poskus_ob_napaki(self):
        odgovori = ["to ni json", json.dumps(VELJAVEN)]
        klici = []

        def lazni(sporocila):
            klici.append(len(sporocila))
            return odgovori[len(klici) - 1]

        r = llm.pridobi_odgovor(lazni, [{"role": "user", "content": "x"}])
        self.assertEqual(r.priporocila[0].ime, "Rakušev trg")
        self.assertEqual(klici, [1, 3])   # drugič je pogovor daljši (napaka + opomba)

    def test_napacen_tip_je_zavrnjen(self):
        slab = json.loads(json.dumps(VELJAVEN))
        slab["priporocila"][0]["tip"] = "garaža"
        with self.assertRaises(llm.LlmNapaka):
            llm.pridobi_odgovor(lambda s: json.dumps(slab), [{"role": "user", "content": "x"}])

    def test_prazen_seznam_priporocil(self):
        with self.assertRaises(llm.LlmNapaka):
            llm.pridobi_odgovor(lambda s: '{"povzetek":"x","priporocila":[]}', [])


class TestGroqKlic(unittest.TestCase):
    class Odgovor:
        def __init__(self, koda, telo):
            self.status_code, self._telo, self.text = koda, telo, str(telo)

        def json(self):
            return self._telo

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(self.status_code)

    class Seja:
        def __init__(self, odg):
            self.odg, self.zadnji = odg, None

        def post(self, url, **kw):
            self.zadnji = (url, kw)
            return self.odg

    def test_zahtevek_in_odgovor(self):
        seja = self.Seja(self.Odgovor(200, {"choices": [{"message": {"content": "{}"}}]}))
        self.assertEqual(llm.groq_klic("k", "m", seja)([{"role": "user", "content": "x"}]), "{}")
        url, kw = seja.zadnji
        self.assertIn("groq.com", url)
        self.assertEqual(kw["headers"]["Authorization"], "Bearer k")
        self.assertEqual(kw["json"]["response_format"], {"type": "json_object"})

    def test_model_se_izbere_iz_seznama(self):
        class S(self.Seja):
            def get(self, url, **kw):
                return TestGroqKlic.Odgovor(200, {"data": [{"id": "whisper-large-v3"}, {"id": "llama-guard-4-12b"},
                                                           {"id": "llama-3.1-8b-instant"}, {"id": "llama-4-70b-x"}, {"id": "gpt-x"}]})
        self.assertEqual(llm.izberi_model("k", S(None)), "llama-4-70b-x")

    def test_seznam_modelov_ni_dosegljiv(self):
        class S(self.Seja):
            def get(self, url, **kw):
                raise RuntimeError("omrežje")
        with self.assertRaisesRegex(llm.LlmNapaka, "seznama modelov"):
            llm.izberi_model("k", S(None))

    def test_seznam_modelov_napaka_kljuca(self):
        class S(self.Seja):
            def get(self, url, **kw):
                return TestGroqKlic.Odgovor(401, "nepooblascen")
        with self.assertRaisesRegex(llm.LlmNapaka, "401"):
            llm.izberi_model("k", S(None))

    def test_brez_llame_vzame_prvi_pogovorni(self):
        class S(self.Seja):
            def get(self, url, **kw):
                return TestGroqKlic.Odgovor(200, {"data": [{"id": "whisper-large"}, {"id": "mixtral-x"}]})
        self.assertEqual(llm.izberi_model("k", S(None)), "mixtral-x")

    def test_klic_uporabi_izbrani_model_enkrat(self):
        stevec = {"get": 0}

        class S(self.Seja):
            def get(self, url, **kw):
                stevec["get"] += 1
                return TestGroqKlic.Odgovor(200, {"data": [{"id": "llama-9-70b"}]})
        seja = S(self.Odgovor(200, {"choices": [{"message": {"content": "{}"}}]}))
        k = llm.groq_klic("k", None, seja)
        k([]); k([])
        self.assertEqual(seja.zadnji[1]["json"]["model"], "llama-9-70b")
        self.assertEqual(stevec["get"], 1)

    def test_napacen_kljuc(self):
        with self.assertRaisesRegex(llm.LlmNapaka, "ključ"):
            llm.groq_klic("k", "m", self.Seja(self.Odgovor(401, {})))([])

    def test_omejitev(self):
        with self.assertRaisesRegex(llm.LlmNapaka, "omejitev"):
            llm.groq_klic("k", "m", self.Seja(self.Odgovor(429, {})))([])


class TestApi(unittest.TestCase):
    def odjemalec(self, klic, geokodiraj=gk):
        napoved = lambda lat, lon, dan, ura: {"opis": "dež", "temperatura_c": 8.0, "verjetnost_padavin_pct": 70, "padavine_mm": 1.0}
        return TestClient(aplikacija.ustvari_app(klic, geokodiraj, napoved, CENIK))

    TELO = {"cilj": "Glavni trg", "datum": "2026-11-09", "ura": "10:00", "trajanje_ur": 2, "namen": "nakupovanje",
            "vozilo": "osebni avto", "max_pes_min": 10}

    def test_uspesno_in_stevilke_iz_izracuna(self):
        shranjeno = {}

        def klic(sporocila):
            shranjeno["sporocila"] = sporocila
            return json.dumps(VELJAVEN)

        d = self.odjemalec(klic).post("/api/priporoci", json=self.TELO).json()
        p = d["odgovor"]["priporocila"][0]
        self.assertEqual(p["ocenjena_cena_eur"], 3.2)       # model je napisal 99, strežnik popravi
        self.assertNotEqual(p["pes_minut"], 99)
        self.assertIn("Glavni trg", shranjeno["sporocila"][1]["content"])
        self.assertEqual(d["vreme"]["opis"], "dež")
        self.assertEqual(len(d["opcije"]), 4)

    def test_neobstojece_parkirisce_je_izpuscano(self):
        odg = {"povzetek": "x", "priporocila": [
            {"ime": "Izmišljena garaža", "tip": "drugo", "razlog": "r"},
            {"ime": "Mlinska ulica", "tip": "ograjeno", "razlog": "r"}]}
        d = self.odjemalec(lambda s: json.dumps(odg)).post("/api/priporoci", json=self.TELO).json()
        self.assertEqual([p["ime"] for p in d["odgovor"]["priporocila"]], ["Mlinska ulica"])
        self.assertTrue(any("Izmišljena" in o for o in d["opozorila"]))

    def test_samo_neobstojece_je_napaka(self):
        odg = {"povzetek": "x", "priporocila": [{"ime": "Nekje", "tip": "drugo", "razlog": "r"}]}
        r = self.odjemalec(lambda s: json.dumps(odg)).post("/api/priporoci", json=self.TELO)
        self.assertEqual(r.status_code, 502)

    def test_brez_kljuca(self):
        r = self.odjemalec(None).post("/api/priporoci", json=self.TELO)
        self.assertEqual(r.status_code, 502)
        self.assertIn("GROQ_API_KEY", r.json()["napaka"])

    def test_naslov_ni_najden(self):
        r = self.odjemalec(lambda s: "{}", lambda n: None).post("/api/priporoci", json=self.TELO)
        self.assertEqual(r.status_code, 404)

    def test_neveljaven_vnos(self):
        r = self.odjemalec(lambda s: "{}").post("/api/priporoci", json={**self.TELO, "ura": "25:99"})
        self.assertEqual(r.status_code, 422)

    def test_vreme_odpove_nadaljujemo(self):
        def napoved(*a):
            raise RuntimeError("omrežje")
        c = TestClient(aplikacija.ustvari_app(lambda s: json.dumps(VELJAVEN), gk, napoved, CENIK))
        d = c.post("/api/priporoci", json=self.TELO).json()
        self.assertIsNone(d["vreme"])

    def test_stanje_in_stran(self):
        c = self.odjemalec(lambda s: "{}")
        self.assertTrue(c.get("/api/stanje").json()["llmNastavljen"])
        self.assertEqual(c.get("/").status_code, 200)

    def test_env(self):
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / ".env"
            p.write_text('# komentar\nTESTNI_KLJUC_X="abc"\n', encoding="utf-8")
            os.environ.pop("TESTNI_KLJUC_X", None)
            aplikacija.nalozi_env(p)
            self.assertEqual(os.environ["TESTNI_KLJUC_X"], "abc")


if __name__ == "__main__":
    unittest.main()
