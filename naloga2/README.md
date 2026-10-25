# Naloga 2: Parser – cenik parkiranja v Mariboru

Razčlenjevalnik (parser) prebere dve javni strani podjetja Marprom (upravljavec javnih parkirišč v Mariboru)
in iz njiju izlušči uradni cenik parkiranja. Rezultat shrani v `cenik.json` in `cenik.xml`, ki ju uporabi
končni izdelek (iskanje parkirišč in načrtovanje poti) namesto ročno vnesenih cen.

## Viri

| Stran | Kaj vsebuje | Oblika na strani |
|---|---|---|
| [Javna parkirišča in pajek](https://www.marprom.si/ceniki-in-vozovnice/javna-parkirisca-in-pajek/) | cene po območnih kodah bele cone (311–318), mesečni najem, vrednostne kartice, cene ograjenih parkirišč, odvoz vozil, datum veljavnosti | 4 HTML tabele + odstavek z datumom |
| [Ograjena parkirišča](https://www.marprom.si/ograjena-parkirisca/) | parkirišča z zapornicami (ime, število mest), čas plačljivosti, enotna urna cena, mesečni najem | naštevni seznam in besedilo |

Pogoji uporabe: `robots.txt` strani ne prepoveduje dostopa (`User-agent: *`, `Disallow:` je prazen). Program zato
med zahtevama počaka 1 sekundo in prenesene strani shrani v predpomnilnik (privzeto 6 ur), da strežnika ne obremenjuje.
Podatki so last podjetja Marprom; v projektu se uporabljajo samo v študijske namene.

## Namestitev in zagon

Zahteva: Python 3.9 ali novejši.

```
py -m pip install -r requirements.txt
py marprom_parser.py
```

Izhod (`cenik.json`, `cenik.xml`) se shrani v trenutno mapo.

| Možnost | Pomen |
|---|---|
| `--izhod mapa` | mapa za izhodne datoteke |
| `--osvezi` | prezri predpomnilnik in ponovno prenesi strani |
| `--max-starost-ur 6` | največja starost predpomnilnika (ure) |
| `--cache-mapa mapa` | mapa predpomnilnika (privzeto `.cache`) |
| `--html-mapa mapa` | prebere HTML iz lokalne mape, brez omrežja (npr. `tests/fixtures`) |

Primer izpisa:

```
Berem strani Marprom ...
  preneseno: https://www.marprom.si/ceniki-in-vozovnice/javna-parkirisca-in-pajek/
  preneseno: https://www.marprom.si/ograjena-parkirisca/

Povzetek:
  cenik velja od: 2026-04-01
  območne kode bele cone: 8
    311: 1.80 €/h
    312: 1.00 €/h
    ...
    315: 1.60 €/h (avtodomi)
  ograjena parkirišča: 3, 1.60 €/h
    Rakušev trg: 86 mest
    Mlinska ulica: 53 mest
    Sodna ulica/Ulica talcev: 121 mest
```

## Kako deluje

1. **Prenos** (`prenesi`): `requests` prenese stran, rezultat shrani v `.cache/`.
2. **Stran A** (`razcleni_cenik`): `BeautifulSoup` poišče vse tabele in jih prepozna po naslovu (ne po vrstnem redu),
   zato so odporne na spremembo razporeditve. Vrstica, ki velja za več območnih kod
   (»območne kode 312, 314, 318«), se razširi v en zapis za vsako kodo. Cena se razčleni z regularnim izrazom
   (`1,60 € (max. 15,70 €/dan)` → cena 1.6, največ na dan 15.7; `brezplačno` → 0).
3. **Stran B** (`razcleni_ograjena`): iz seznama prebere ime in število mest (vključno s polnilnimi mesti za električna vozila),
   iz besedila pa čas plačljivosti (delavniki 6–22, sobote 8–13) in urno ceno.
4. **Združevanje** (`sestavi`): obe strani se združita. Cena ograjenih parkirišč je navedena na obeh straneh, zato se
   primerja; če se razlikuje, se v `meta.opozorila` zapiše opozorilo.
5. **Izvoz** (`izvozi`): `cenik.json` in `cenik.xml` z isto vsebino.

Če stran nima pričakovane strukture (npr. tabela manjka), program ne zapiše napačnih podatkov, ampak se ustavi
z jasnim sporočilom.

## Struktura izhoda

```
meta                 vir, naslovi strani, čas pridobitve, veljaOd, opozorila
belaCona
  urnaCena[]         koda, cenaNaUro, avtodomi, maxNaDan
  mesecniNajemInKartice[]
ograjenaParkirisca
  parkirisca[]       ime, steviloMest, steviloMestEl
  placljivost        delavnik {od, do}, sobota {od, do}
  cenaNaUro, cenik[], mesecniNajem[], prostaMestaZaMesecniNajem
pajek[]              odvoz in hramba vozila
```

## Testi

```
py -m unittest discover -s tests
```

Testi uporabljajo shranjena HTML vzorca v `tests/fixtures/` (izseka obeh strani s tabelami, seznami in besedilom, kot so bili objavljeni 25. 10. 2026)
in lokalni strežnik za preizkus prenosa in predpomnilnika, zato ne potrebujejo interneta.

## Omejitve

- Strani ne navajata, katere ulice spadajo v katero območno kodo, zato povezava kod z ulicami ni del izhoda.
- Zasedenost parkirišč ni objavljena, zato je izhod samo cenik in statični podatki.
- Cene in strukturo strani določa Marprom; ob spremembi strani je treba prilagoditi regularne izraze.
- Primerjava s prejšnjim, ročno vnesenim ceniščem (2023) pokaže, da so se cene spremenile (npr. ograjena parkirišča 1,50 € → 1,60 €).
