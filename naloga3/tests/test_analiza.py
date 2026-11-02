import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import analiza as a  # noqa: E402
import pcaxis  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def beri(koda):
    return pcaxis.razcleni_bajte((FIXTURES / f"{koda}.px").read_bytes())


class TestVozila(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.t = beri(a.T_VOZILA)

    def test_trend_filtrira_po_obcini_in_letu(self):
        d = a.vozni_park(self.t, "Maribor", ["1.31"], "2023")
        self.assertEqual(d["leta"], ["2023", "2024", "2025"])
        self.assertEqual(d["obcina"], "Maribor")
        self.assertEqual(len(d["serije"][0]["vrednosti"]), 3)

    def test_indeks_zacne_pri_100(self):
        d = a.vozni_park(self.t, "Maribor", ["1.31", "1.5"])
        for s in d["serije"]:
            self.assertEqual(s["indeks"][0], 100.0)

    def test_manjkajoc_podatek_je_null_in_indeks_ostane_veljaven(self):
        d = a.vozni_park(self.t, "Murska Sobota", ["1.4"])
        self.assertIsNone(d["serije"][0]["vrednosti"][0])
        self.assertIsNone(d["serije"][0]["indeks"][0])
        self.assertEqual(d["serije"][0]["indeks"][1], 100.0)

    def test_lestvica_urejena_padajoce_brez_slovenije(self):
        d = a.lestvica_vozil(self.t, "2025", "1.31", top=3)
        imena = [p["obcina"] for p in d["postavke"]]
        self.assertNotIn("SLOVENIJA", imena)
        self.assertEqual(imena[:2], ["Ljubljana", "Maribor"])
        self.assertEqual(d["postavke"][1]["rang"], 2)
        self.assertEqual(d["steviloObcin"], 6)

    def test_izpostavljena_obcina_je_vedno_vkljucena(self):
        d = a.lestvica_vozil(self.t, "2025", "1.31", top=1, izpostavi="Maribor")
        self.assertEqual([p["obcina"] for p in d["postavke"]], ["Ljubljana", "Maribor"])

    def test_delez_v_sloveniji(self):
        d = a.lestvica_vozil(self.t, "2025", "1.31", top=2)
        mar = d["postavke"][1]
        self.assertAlmostEqual(mar["delezVSloveniji"], 100.0 * mar["vrednost"] / d["slovenija"], places=1)

    def test_neznana_obcina(self):
        with self.assertRaises(a.NapacenVnos):
            a.vozni_park(self.t, "Atlantida", ["1.31"])

    def test_izbire(self):
        iz = a.izbire_vozil(self.t)
        self.assertEqual(iz["privzeto"]["obcina"], "Maribor")
        self.assertEqual(len(iz["privzeto"]["vrste"]), 3)


class TestMotorizacija(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.t = beri(a.T_MOTORIZACIJA)

    def test_trend_vec_obcin(self):
        d = a.motorizacija(self.t, ["Maribor", "SLOVENIJA"])
        self.assertEqual([s["obcina"] for s in d["serije"]], ["Maribor", "SLOVENIJA"])
        self.assertEqual(len(d["leta"]), 5)

    def test_lestvica_ima_slovenijo_kot_povprecje(self):
        d = a.lestvica_motorizacije(self.t, "2025", top=2)
        self.assertEqual(d["steviloObcin"], 6)
        self.assertIsNotNone(d["slovenija"])
        rangi = [p["rang"] for p in d["postavke"]]
        self.assertEqual(rangi[:2], [1, 2])


class TestPogon(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.t = beri(a.T_POGON)

    def test_privzeta_vrsta_je_osebni_avtomobil(self):
        self.assertIn("Osebni avtomobili", a.izbire_pogona(self.t)["privzeto"]["vrsta"])

    def test_deleži_brez_skupaj_in_vsota_blizu_100(self):
        d = a.pogon(self.t, a.izbire_pogona(self.t)["privzeto"]["vrsta"])
        self.assertNotIn("Vrsta pogona in goriva - SKUPAJ", [s["pogon"] for s in d["serije"]])
        for i in range(len(d["leta"])):
            self.assertAlmostEqual(sum(s["delez"][i] for s in d["serije"]), 100.0, delta=0.5)

    def test_elektricni_delez_narasca(self):
        d = a.pogon(self.t, "1.3")
        el = next(s for s in d["serije"] if "lektri" in s["pogon"])
        self.assertEqual(el["delez"], sorted(el["delez"]))

    def test_druga_meritev(self):
        d = a.pogon(self.t, "1.3", "Prve registracije vozil - skupaj")
        self.assertLess(d["skupaj"][0], 200000)


class TestPoti(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.t = beri(a.T_POTI)

    def test_delez_avta_v_mariboru_2025(self):
        d = a.potovanja(self.t, "2025")
        mar = next(o for o in d["obcine"] if o["mestnaObcina"] == "Maribor")
        avto = next(n for n in mar["nacini"] if n["nacin"] == "Osebni avto - skupaj")
        self.assertEqual(avto["stevilo"], 79153)
        self.assertEqual(avto["delez"], 67.5)   # 79153 / 117290

    def test_zasedenost_avta(self):
        mar = next(o for o in a.potovanja(self.t, "2025")["obcine"] if o["mestnaObcina"] == "Maribor")
        self.assertEqual(mar["zasedenostAvta"], round((64123 + 15030) / 64123, 2))

    def test_manjkajoci_nacin_je_null(self):
        mar = next(o for o in a.potovanja(self.t, "2025")["obcine"] if o["mestnaObcina"] == "Maribor")
        taksi = next(n for n in mar["nacini"] if n["nacin"] == "Taksi")
        self.assertIsNone(taksi["stevilo"])
        self.assertIsNone(taksi["delez"])

    def test_nezanano_leto(self):
        with self.assertRaises(a.NapacenVnos):
            a.potovanja(self.t, "2019")


class TestParkiranje(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.t = beri(a.T_PARKIRANJE)

    def test_skupine_in_deleži(self):
        d = a.parkiranje(self.t, "2025")
        sk = {s["skupina"]: s for s in d["skupine"]}
        self.assertEqual(d["skupaj"], 395773)
        self.assertEqual(sk["Pri delodajalcu"]["stevilo"], 318860 + 17521)
        self.assertEqual(sk["Javno (ob cesti, javno parkirišče)"]["stevilo"], 39181 + 16752)

    def test_filter_po_spolu(self):
        z = a.parkiranje(self.t, "2025", "Ženske")
        self.assertEqual(z["skupaj"], 167790)

    def test_spol_po_kodi(self):
        self.assertEqual(a.parkiranje(self.t, "2025", "1")["skupaj"], 227983)

    def test_manjkajoce_je_null(self):
        d = a.parkiranje(self.t, "2025")
        pr = next(p for p in d["podrobno"] if "P&R" in p["kraj"])
        self.assertIsNone(pr["stevilo"])
        self.assertIsNone(pr["delez"])


if __name__ == "__main__":
    unittest.main()
