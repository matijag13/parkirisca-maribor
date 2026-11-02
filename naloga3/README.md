# Naloga 3: Odprti podatki Slovenije (PC-Axis)

Spletna aplikacija prikazuje podatke Statističnega urada RS (SURS) o prometu, motorizaciji in parkiranju, ki so v
končnem projektu (iskanje parkirnih prostorov v Mariboru) potrebni kot ozadje: koliko je avtomobilov, kako se vozimo
in kje parkirajo ljudje, ki z avtom pridejo v službo.

## Podatki

Vir: [SiStat](https://pxweb.stat.si/SiStatData/pxweb/sl/Data/), katalog odprtih podatkov
[podatki.gov.si](https://podatki.gov.si) (izdajatelj SURS; vsak zapis ima vir v formatu PCAXIS). Vse tabele so v formatu **PC-Axis (.px)**
in se prenesejo neposredno kot `https://pxweb.stat.si/SiStatData/Resources/PX/Databases/Data/<KODA>.PX`.

| Koda | Vsebina | Uporaba | Zapis na OPSI |
|---|---|---|---|
| 2222105S | cestna vozila konec leta po vrsti vozila, občinah in letih | trend vozil v občini, lestvica občin | [surs2222105s](https://podatki.gov.si/dataset/surs2222105s) |
| 2221110S | stopnja motorizacije (avtomobilov na 1.000 prebivalcev) po občinah | trend in lestvica | [surs2221110s](https://podatki.gov.si/dataset/surs2221110s) |
| 2222109S | vozila po vrsti pogona in goriva (Slovenija) | delež električnih, hibridnih ... | [surs2222109s](https://podatki.gov.si/dataset/surs2222109s) |
| 2281296S | letno število poti v MO Ljubljana in MO Maribor po prevoznem sredstvu | delež avta, pešcev, koles; zasedenost avta | [surs2281296s](https://podatki.gov.si/dataset/surs2281296s) |
| 2281931S | kraj parkiranja avtomobila, uporabljenega za pot na delo (Slovenija) | delež javnega parkiranja | [surs2281931s](https://podatki.gov.si/dataset/surs2281931s) |

## Zagon

Zahteva: Python 3.9 ali novejši.

```
py -m pip install -r requirements.txt
py app.py
```

Nato odpri http://127.0.0.1:8000. Prvi zagon prenese pet PX datotek (skupaj okoli 0,5 MB) v `.cache/px/` in jih 24 ur
uporablja iz predpomnilnika. Brez interneta: `py app.py --lokalno tests/fixtures` (majhne testne tabele).

## Kako deluje

```
SiStat .PX  ->  sistat.py (prenos + predpomnilnik)  ->  pcaxis.py (razčlenjevalnik)
            ->  analiza.py (filtriranje, združevanje)  ->  app.py (FastAPI, JSON)  ->  static/ (Chart.js)
```

1. **`pcaxis.py`**: lasten razčlenjevalnik PX. Glavo prebere kot stavke `KLJUČ=VREDNOST;` (podpičje v narekovajih ne
   zaključi stavka), upošteva `CODEPAGE` (windows-1250), prelomljene nize, dvojezične ključe (`TITLE[en]` preskoči) in
   `STUB`/`HEADING`. Podatke iz bloka `DATA=` pretvori v seznam števil; `"."`, `".."`, `"..."` postanejo `None`.
   Položaj celice se izračuna iz dimenzij (prva STUB spremenljivka se spreminja najpočasneje). Vrednosti se izberejo po
   oznaki, kodi ali začetku oznake (`"1.31"` najde `"1.31 Navadni osebni avtomobili"`).
2. **`sistat.py`**: prenos z `requests`, predpomnilnik na disku (24 ur) in v pomnilniku; ob izpadu omrežja uporabi starejšo kopijo.
3. **`analiza.py`**: filtriranje in združevanje. Primeri: izbira občine in obdobja, indeks rasti (prvo leto = 100),
   uvrstitev občin in delež Maribora v Sloveniji, delež pogona (del / vrstica »SKUPAJ«), delež prevoznih sredstev,
   zasedenost avta ((voznik + sopotnik) / voznik), združevanje sedmih krajev parkiranja v štiri skupine.
4. **`app.py`**: končne točke `/api/...`; parametri (`obcina`, `vrste`, `od`, `leto`, `top`, `spol` ...) določajo filter.
5. **`static/`**: ob odprtju strani JavaScript pokliče API in nariše grafe (Chart.js 4.4.7, shranjen lokalno, licenca MIT);
   sprememba kontrole ponovno naloži samo ta graf.

| Končna točka | Parametri |
|---|---|
| `/api/povzetek` | – |
| `/api/vozila/izbire`, `/api/vozila/trend` | `obcina`, `vrste` (večkrat), `od` |
| `/api/vozila/lestvica` | `leto`, `vrsta`, `top`, `obcina` |
| `/api/motorizacija/trend` | `obcine` (večkrat) |
| `/api/motorizacija/lestvica` | `leto`, `top`, `obcina` |
| `/api/pogon/izbire`, `/api/pogon` | `vrsta`, `meritev` |
| `/api/poti` | `leto` |
| `/api/parkiranje` | `leto`, `spol` (`TOT`, `1`, `2`) |
| `/api/meta` | viri, licenca, datum posodobitve |

Dokumentacijo končnih točk ponuja tudi http://127.0.0.1:8000/docs.

## Testi

```
py -m unittest discover -s tests
```

Testi ne potrebujejo interneta. Tabeli `2281296S` in `2281931S` v `tests/fixtures/` imata prave vrednosti SURS;
`2222105S`, `2222109S` in `2221110S` so **zmanjšane datoteke z enako zgradbo, a izmišljenimi števili**, da je test hiter.

## Omejitve

- SURS objavlja podatke o poteh (2281296S) in parkiranju (2281931S) samo za nekatera leta (2017, 2021, 2025 oziroma 2021, 2025);
  poti samo za MO Ljubljana in MO Maribor; parkiranje in pogon samo za celo Slovenijo.
- Podatki o parkiranju so iz ankete o poti na delo, ne o zasedenosti parkirišč, zato služijo kot ozadje, ne kot zasedenost.
- Oznake tabel določa SURS; ob spremembi besedila oznak je treba prilagoditi konstante v `analiza.py`.
