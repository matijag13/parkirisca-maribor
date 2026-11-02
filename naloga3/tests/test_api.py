import functools
import http.server
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fastapi.testclient import TestClient  # noqa: E402

import app as aplikacija  # noqa: E402
import sistat  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"


class TestApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        vir = sistat.Vir(Path(tempfile.mkdtemp()), lokalna_mapa=FIXTURES)
        cls.c = TestClient(aplikacija.ustvari_app(vir))

    def test_domov_vrne_stran(self):
        r = self.c.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Promet in parkiranje", r.text)

    def test_chart_js_je_lokalen(self):
        self.assertEqual(self.c.get("/static/vendor/chart.umd.js").status_code, 200)

    def test_povzetek(self):
        d = self.c.get("/api/povzetek").json()
        self.assertEqual(d["vozila"]["leto"], "2025")
        self.assertEqual(d["poti"]["delezAvto"], 67.5)
        self.assertIsNotNone(d["elektrika"]["delez"])

    def test_vozila_trend_filtri(self):
        r = self.c.get("/api/vozila/trend", params={"obcina": "Celje", "vrste": ["1.31", "1.5"], "od": "2024"})
        d = r.json()
        self.assertEqual(d["leta"], ["2024", "2025"])
        self.assertEqual(len(d["serije"]), 2)

    def test_privzeti_parametri(self):
        d = self.c.get("/api/vozila/trend").json()
        self.assertEqual(d["obcina"], "Maribor")
        self.assertEqual(len(d["serije"]), 3)

    def test_lestvica_top(self):
        d = self.c.get("/api/vozila/lestvica", params={"top": 2}).json()
        self.assertEqual(len(d["postavke"]), 2)

    def test_neznana_obcina_je_404_s_sporocilom(self):
        r = self.c.get("/api/vozila/trend", params={"obcina": "Atlantida"})
        self.assertEqual(r.status_code, 404)
        self.assertIn("Atlantida", r.json()["napaka"])

    def test_neveljaven_top_je_422(self):
        self.assertEqual(self.c.get("/api/vozila/lestvica", params={"top": 0}).status_code, 422)

    def test_ostale_koncne_tocke(self):
        for pot in ("/api/meta", "/api/vozila/izbire", "/api/motorizacija/trend", "/api/motorizacija/lestvica",
                    "/api/pogon/izbire", "/api/pogon", "/api/poti", "/api/parkiranje"):
            with self.subTest(pot=pot):
                self.assertEqual(self.c.get(pot).status_code, 200)

    def test_parkiranje_spol(self):
        d = self.c.get("/api/parkiranje", params={"leto": "2021", "spol": "2"}).json()
        self.assertEqual(d["skupaj"], 179102)

    def test_meta_vsebuje_vse_vire(self):
        d = self.c.get("/api/meta").json()
        self.assertEqual({v["koda"] for v in d["viri"]}, {"2222105S", "2222109S", "2221110S", "2281296S", "2281931S"})


class TestPrenos(unittest.TestCase):
    """Prenos in predpomnilnik s pravim HTTP strežnikom na lokalnem računalniku (brez interneta)."""

    @classmethod
    def setUpClass(cls):
        class Tih(http.server.SimpleHTTPRequestHandler):
            stevec = 0

            def do_GET(self):
                Tih.stevec += 1
                super().do_GET()

            def log_message(self, *a):
                pass

        cls.Tih = Tih
        cls.streznik = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Tih, directory=str(FIXTURES)))
        threading.Thread(target=cls.streznik.serve_forever, daemon=True).start()
        cls.stari_url = sistat.URL
        sistat.URL = f"http://127.0.0.1:{cls.streznik.server_port}/{{koda}}.px"

    @classmethod
    def tearDownClass(cls):
        sistat.URL = cls.stari_url
        cls.streznik.shutdown()

    def test_prenos_nato_pomnilnik_in_disk(self):
        with tempfile.TemporaryDirectory() as d:
            self.Tih.stevec = 0
            vir = sistat.Vir(Path(d))
            t1 = vir.tabela("2281931S")
            t2 = vir.tabela("2281931S")
            self.assertIs(t1, t2)
            self.assertEqual(self.Tih.stevec, 1)
            self.assertTrue((Path(d) / "2281931S.px").exists())
            # nov Vir (nov zagon aplikacije) prebere disk, ne omrežja
            sistat.Vir(Path(d)).tabela("2281931S")
            self.assertEqual(self.Tih.stevec, 1)

    def test_neobstojeca_tabela(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(sistat.ViraNapaka):
                sistat.Vir(Path(d)).tabela("0000000S")

    def test_stari_predpomnilnik_ob_izpadu_omrezja(self):
        import os
        import time
        with tempfile.TemporaryDirectory() as d:
            vir = sistat.Vir(Path(d), max_starost_ur=1)
            vir.tabela("2281931S")
            pot = Path(d) / "2281931S.px"
            star = time.time() - 7200
            os.utime(pot, (star, star))
            sistat.URL = "http://127.0.0.1:1/{koda}.px"   # nedosegljiv strežnik
            try:
                t = sistat.Vir(Path(d), max_starost_ur=1).tabela("2281931S")
            finally:
                sistat.URL = f"http://127.0.0.1:{self.streznik.server_port}/{{koda}}.px"
            self.assertEqual(t.heading, ["LETO", "SPOL"])


if __name__ == "__main__":
    unittest.main()
