import json
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import marprom_parser as p  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def beri(ime):
    return (FIXTURES / ime).read_text(encoding="utf-8")


class TestCene(unittest.TestCase):
    def test_navadna_cena(self):
        self.assertEqual(p.razcleni_ceno("1,80 €")["cena"], 1.8)

    def test_cena_z_dnevnim_maksimumom(self):
        c = p.razcleni_ceno("1,60 € (max. 15,70 €/dan)")
        self.assertEqual((c["cena"], c["maxNaDan"]), (1.6, 15.7))

    def test_brezplacno(self):
        self.assertEqual(p.razcleni_ceno("brezplačno")["cena"], 0.0)

    def test_celo_stevilo(self):
        self.assertEqual(p.razcleni_ceno("100 €")["cena"], 100.0)

    def test_neznano_besedilo(self):
        self.assertIsNone(p.razcleni_ceno("po dogovoru")["cena"])


class TestCenik(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = p.razcleni_cenik(beri("javna-parkirisca-in-pajek.html"))

    def test_datum_veljavnosti(self):
        self.assertEqual(self.r["veljaOd"].isoformat(), "2026-04-01")

    def test_osem_obmocnih_kod(self):
        kode = {o["koda"]: o for o in self.r["belaCona"]["urnaCena"]}
        self.assertEqual(sorted(kode), ["311", "312", "313", "314", "315", "316", "317", "318"])

    def test_cene_po_kodah(self):
        kode = {o["koda"]: o["cenaNaUro"] for o in self.r["belaCona"]["urnaCena"]}
        self.assertEqual(kode["311"], 1.8)
        for k in ("312", "314", "318"):
            self.assertEqual(kode[k], 1.0)
        for k in ("313", "316", "317"):
            self.assertEqual(kode[k], 0.6)

    def test_avtodomi(self):
        o = next(o for o in self.r["belaCona"]["urnaCena"] if o["koda"] == "315")
        self.assertTrue(o["avtodomi"])
        self.assertEqual((o["cenaNaUro"], o["maxNaDan"]), (1.6, 15.7))

    def test_ostale_tabele(self):
        self.assertEqual(len(self.r["belaCona"]["mesecniNajemInKartice"]), 9)
        self.assertEqual(len(self.r["ograjenaCenik"]), 6)
        self.assertEqual([x["cena"] for x in self.r["pajek"]], [100.0, 5.0])
        brezplacno = [x for x in self.r["belaCona"]["mesecniNajemInKartice"] if x["cena"] == 0.0]
        self.assertEqual(len(brezplacno), 1)

    def test_brez_opozoril(self):
        self.assertEqual(self.r["opozorila"], [])

    def test_manjkajoca_tabela_sproži_napako(self):
        html = "<html><body><table><tr><th>Neznana</th><th>EUR</th></tr><tr><td>x</td><td>1 €</td></tr></table></body></html>"
        with self.assertRaises(p.ParserNapaka):
            p.razcleni_cenik(html)

    def test_stran_brez_tabel(self):
        with self.assertRaises(p.ParserNapaka):
            p.razcleni_cenik("<html><body><p>Pozdravljeni</p></body></html>")


class TestOgrajena(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = p.razcleni_ograjena(beri("ograjena-parkirisca.html"))

    def test_parkirisca(self):
        self.assertEqual(
            [(x["ime"], x["steviloMest"], x["steviloMestEl"]) for x in self.r["parkirisca"]],
            [("Rakušev trg", 86, None), ("Mlinska ulica", 53, 4), ("Sodna ulica/Ulica talcev", 121, None)],
        )

    def test_placljivost(self):
        self.assertEqual(self.r["placljivost"], {"delavnik": {"od": 6, "do": 22}, "sobota": {"od": 8, "do": 13}})

    def test_cena(self):
        self.assertEqual(self.r["cenaNaUro"], 1.6)

    def test_mesecni_najem(self):
        self.assertEqual([x["cena"] for x in self.r["mesecniNajem"]], [68.02, 61.22, 57.82])

    def test_ni_prostih_mest(self):
        self.assertIs(self.r["prostaMestaZaMesecniNajem"], False)

    def test_stran_brez_seznama(self):
        with self.assertRaises(p.ParserNapaka):
            p.razcleni_ograjena("<html><body><p>nič</p></body></html>")


class TestPrenos(unittest.TestCase):
    """Preizkusi prenos in predpomnilnik z lokalnim strežnikom (brez dostopa do interneta)."""

    @classmethod
    def setUpClass(cls):
        import functools
        import http.server
        import threading

        class Tih(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *a):
                pass

        handler = functools.partial(Tih, directory=str(FIXTURES))
        cls.streznik = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.url = f"http://127.0.0.1:{cls.streznik.server_port}/ograjena-parkirisca.html"
        threading.Thread(target=cls.streznik.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.streznik.shutdown()

    def test_prenos_in_predpomnilnik(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            mapa = Path(d)
            html, iz_cacha = p.prenesi(self.url, mapa, 6, False)
            self.assertFalse(iz_cacha)
            self.assertIn("Rakušev trg", html)
            html2, iz_cacha2 = p.prenesi(self.url, mapa, 6, False)
            self.assertTrue(iz_cacha2)
            self.assertEqual(html, html2)
            _, iz_cacha3 = p.prenesi(self.url, mapa, 6, True)
            self.assertFalse(iz_cacha3)

    def test_neobstojeca_stran(self):
        import tempfile
        import requests
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(requests.HTTPError):
                p.prenesi(self.url.replace("ograjena", "ni-je"), Path(d), 6, False)


class TestIzvoz(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.mapa = Path(self.tmp.name)
        cenik = p.razcleni_cenik(beri("javna-parkirisca-in-pajek.html"))
        ograjena = p.razcleni_ograjena(beri("ograjena-parkirisca.html"))
        self.podatki = p.sestavi(cenik, ograjena, "2026-10-25T10:00:00+01:00")
        p.izvozi(self.podatki, self.mapa)

    def tearDown(self):
        self.tmp.cleanup()

    def test_json_je_veljaven_in_enak(self):
        z_datoteke = json.loads((self.mapa / "cenik.json").read_text(encoding="utf-8"))
        self.assertEqual(z_datoteke, self.podatki)

    def test_xml_je_veljaven(self):
        koren = ET.parse(self.mapa / "cenik.xml").getroot()
        self.assertEqual(koren.tag, "cenik")
        self.assertEqual(len(koren.findall("./belaCona/urnaCena/obmocje")), 8)
        self.assertEqual(len(koren.findall("./ograjenaParkirisca/parkirisca/parkirisce")), 3)
        self.assertEqual(koren.findtext("./meta/veljaOd"), "2026-04-01")
        self.assertEqual(koren.findtext("./ograjenaParkirisca/prostaMestaZaMesecniNajem"), "false")

    def test_cene_na_obeh_straneh_se_ujemajo(self):
        self.assertEqual(self.podatki["meta"]["opozorila"], [])

    def test_razlika_cen_je_opozorilo(self):
        cenik = p.razcleni_cenik(beri("javna-parkirisca-in-pajek.html"))
        ograjena = p.razcleni_ograjena(beri("ograjena-parkirisca.html"))
        ograjena["cenaNaUro"] = 2.0
        r = p.sestavi(cenik, ograjena, "x")
        self.assertTrue(any("razlikuje" in o for o in r["meta"]["opozorila"]))


if __name__ == "__main__":
    unittest.main()
