import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pcaxis  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"

MALA = """CHARSET="ANSI";
CODEPAGE="windows-1250";
LANGUAGE="sl";
LANGUAGES="sl","en";
TITLE="Primer po: MESTO, LETO";
TITLE[en]="Example";
UNITS="število";
STUB="MESTO";
HEADING="LETO";
VALUES("MESTO")="Maribor","Celje";
VALUES[en]("CITY")="Maribor","Celje";
VALUES("LETO")="2024","2025";
NOTE="Opomba s podpičjem; in z enačajem = v besedilu";
DATA=
1 2
3 "..";
"""


def beri(ime):
    return pcaxis.razcleni_bajte((FIXTURES / ime).read_bytes())


class TestGlava(unittest.TestCase):
    def test_osnovna_tabela(self):
        t = pcaxis.razcleni(MALA)
        self.assertEqual(t.naslov, "Primer po: MESTO, LETO")
        self.assertEqual((t.stub, t.heading), (["MESTO"], ["LETO"]))
        self.assertEqual(t.oznake["MESTO"], ["Maribor", "Celje"])
        self.assertEqual(t.podatki, [1, 2, 3, None])

    def test_podpicje_v_opombi_ne_konca_stavka(self):
        t = pcaxis.razcleni(MALA)
        self.assertEqual(len(t.podatki), 4)

    def test_angleska_beseda_se_preskoci(self):
        t = pcaxis.razcleni(MALA)
        self.assertNotIn("CITY", t.oznake)
        self.assertEqual(t.naslov, "Primer po: MESTO, LETO")

    def test_prelomljen_niz_se_zdruzi(self):
        self.assertEqual(pcaxis.razcleni_seznam('"abc "\r\n"def","x"'), ["abc def", "x"])

    def test_nenarekovan_element(self):
        self.assertEqual(pcaxis.razcleni_seznam('YES'), ["YES"])
        self.assertEqual(pcaxis.razcleni_seznam('TLIST(A1,"2017"),"2021"'), ['TLIST(A1,"2017")', "2021"])

    def test_vrednosti_z_vejico_v_nizu(self):
        self.assertEqual(pcaxis.razcleni_seznam('"Peš, tek","Kombi, avtodom"'), ["Peš, tek", "Kombi, avtodom"])


class TestNapake(unittest.TestCase):
    def test_brez_data(self):
        with self.assertRaises(pcaxis.PxNapaka):
            pcaxis.razcleni('TITLE="x";STUB="A";HEADING="B";')

    def test_napacno_stevilo_podatkov(self):
        with self.assertRaises(pcaxis.PxNapaka):
            pcaxis.razcleni(MALA.replace('3 "..";', "3;"))

    def test_manjka_values(self):
        with self.assertRaises(pcaxis.PxNapaka):
            pcaxis.razcleni(MALA.replace('VALUES("LETO")="2024","2025";\n', ""))

    def test_neveljavno_stevilo(self):
        with self.assertRaises(pcaxis.PxNapaka):
            pcaxis.razcleni(MALA.replace("1 2", "1 abc"))

    def test_codes_in_values_razlicne_dolzine(self):
        with self.assertRaises(pcaxis.PxNapaka):
            pcaxis.razcleni(MALA.replace("DATA=", 'CODES("MESTO")="1";\nDATA='))


class TestIndeksiranje(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.t = pcaxis.razcleni(MALA)

    def test_vrstni_red_podatkov(self):
        self.assertEqual(self.t.vrednost({"MESTO": "Maribor", "LETO": "2025"}), 2)
        self.assertEqual(self.t.vrednost({"MESTO": "Celje", "LETO": "2024"}), 3)
        self.assertIsNone(self.t.vrednost({"MESTO": "Celje", "LETO": "2025"}))

    def test_serija(self):
        self.assertEqual(self.t.serija("LETO", {"MESTO": "Maribor"}), [("2024", 1), ("2025", 2)])

    def test_neznana_vrednost(self):
        with self.assertRaises(KeyError):
            self.t.vrednost({"MESTO": "Ptuj", "LETO": "2025"})

    def test_manjkajoca_dimenzija(self):
        with self.assertRaises(KeyError):
            self.t.vrednost({"MESTO": "Maribor"})

    def test_vrstice_pokrijejo_vse(self):
        self.assertEqual(len(list(self.t.vrstice())), 4)


class TestDejanskeTabele(unittest.TestCase):
    """Zgradba kot jo objavlja SURS: windows-1250, CRLF, več STUB/HEADING, kode, DATANOTECELL."""

    def test_sumniki(self):
        t = beri("2281296S.px")
        self.assertIn("Peš, tek", t.oznake["GLAVNO PREVOZNO SREDSTVO"])
        self.assertEqual(t.oznake["MESTNA OBČINA"], ["Ljubljana", "Maribor"])

    def test_resnicne_vrednosti_mariborske_poti(self):
        t = beri("2281296S.px")
        izb = {"MESTNA OBČINA": "Maribor", "GLAVNO PREVOZNO SREDSTVO": "Osebni avto - skupaj"}
        self.assertEqual(t.serija("LETO", izb), [("2017", 89654), ("2021", 65628), ("2025", 79153)])

    def test_koda_namesto_oznake(self):
        t = beri("2281296S.px")
        self.assertEqual(t.vrednost({"MESTNA OBČINA": "2", "GLAVNO PREVOZNO SREDSTVO": "AVTO", "LETO": "2025"}), 79153)

    def test_dva_heading(self):
        t = beri("2281931S.px")
        self.assertEqual(t.heading, ["LETO", "SPOL"])
        # prva vrstica: LETO 2021 (SKUPAJ, Moški, Ženske), LETO 2025 (...)
        self.assertEqual(t.vrednost({"KRAJ PARKIRANJA": "TOT", "LETO": "2025", "SPOL": "Moški"}), 227983)
        self.assertIsNone(t.vrednost({"KRAJ PARKIRANJA": "3", "LETO": "2021", "SPOL": "TOT"}))

    def test_dva_stub_in_manjkajoc_podatek(self):
        t = beri("2222105S.px")
        self.assertIsNone(t.vrednost({"VRSTA VOZILA": "1.4", "OBČINE": "Murska Sobota", "LETO": "2021"}))

    def test_predpona_1_3_in_1_31_se_ne_zamenjata(self):
        t = beri("2222105S.px")
        self.assertTrue(t.oznake["VRSTA VOZILA"][t.indeks_vrednosti("VRSTA VOZILA", "1.3")].startswith("1.3 "))
        self.assertTrue(t.oznake["VRSTA VOZILA"][t.indeks_vrednosti("VRSTA VOZILA", "1.31")].startswith("1.31 "))

    def test_meta(self):
        t = beri("2281296S.px")
        self.assertEqual(t.meta["last_updated"], "20260925 10:30")


if __name__ == "__main__":
    unittest.main()
