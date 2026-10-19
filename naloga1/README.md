# Naloga 1: XML in JSON – parkirišča v Mariboru

Projekt je del predmeta TIDS. Tema: **pomoč pri iskanju parkirnih prostorov in načrtovanju poti** (Maribor).
Program prebere tri medsebojno povezane XML datoteke, jih poveže prek ID-jev, filtrira po uporabnikovih
pogojih ter rezultat izpiše v konzolo in shrani v JSON in nov XML.

## Podatki (mapa `data/`)

| Datoteka | Glavna entiteta | Št. elementov | Povezave |
|---|---|---|---|
| `cone.xml` | `cona` (tarifna cona: tip, cena na uro, čas plačljivosti) | 11 | – |
| `parkirisca.xml` | `parkirisce` (naslov, koordinate, kapaciteta) | 14 | `idCone` → `cona/@id` |
| `cilji.xml` | `cilj` (točka, kamor gre voznik) | 11 | `idParkirisca` → `parkirisce/@id` |

Vsaka entiteta ima unikaten atribut `id` (`Z01`, `P01`, `C01` …). V podatkih so:
- **datumska polja** (`datumVira`, `datumVnosa`, oblika `YYYY-MM-DD`),
- **številčna polja** (`cenaNaUro`, `kapaciteta`, `lat`, `lon`) in **besedilna polja** (`ime`, `naslov`, `tip`, `opomba`),
- **prazne in manjkajoče vrednosti**: `kapaciteta` manjka pri parkirišču P10 in je prazna pri P14,
  `placljivoOd`/`placljivoDo` manjkata pri ograjenih parkiriščih, `idParkirisca` je prazen pri cilju C10.
  Program jih prebere kot `None` (v JSON `null`, v XML prazen element).

**Opomba o podatkih:** podatki so vzorčni, narejeni za študijski projekt. Imena ulic so resnična, cene so iz javnih objav
iz leta 2023 (datum je naveden v `datumVira`) in jih je treba pred uporabo preveriti. Koordinate in kapacitete so okvirne
vrednosti za demonstracijo, zasedenost v živo ni vključena, ker za Maribor ni javno dostopna.

## Zagon

Zahteva: Python 3.9 ali novejši, dodatnih knjižnic ni.

```
python app.py [filtri]
```

| Filter | Pomen |
|---|---|
| `--cilj C02` | izbere cilj in izračuna razdaljo do vsakega parkirišča (zračna linija) |
| `--radij 700` | samo parkirišča v radiju (m) od cilja (zahteva `--cilj`) |
| `--max-cena 1.00` | največja cena na uro (€) |
| `--min-kapaciteta 100` | najmanj parkirnih mest |
| `--tip ograjeno` | `ograjeno` ali `ob cesti` |
| `--brezplacen-vikend` | samo cone, brezplačne ob vikendih |
| `--razvrsti razdalja` | `ime`, `cena`, `kapaciteta` ali `razdalja` |
| `--seznam-ciljev` | izpiše vse cilje |
| `--izhod mapa` | mapa za `filtrirano.json` in `filtrirano.xml` (privzeto trenutna) |

### Primeri zagona

```
py app.py --seznam-ciljev
py app.py --cilj C02 --radij 700 --max-cena 1.00 --razvrsti razdalja
py app.py --tip ograjeno --min-kapaciteta 100
py app.py --brezplacen-vikend --max-cena 0.6 --razvrsti cena
```

### Primer izpisa (`--cilj C02 --radij 700 --max-cena 1.00 --razvrsti razdalja`)

```
Cilj: Univerza v Mariboru (rektorat) (Slomškov trg 15)

ID  | Ime                             | Tip      | Cona | €/h  | Mest | Razdalja
----+---------------------------------+----------+------+------+------+---------
P08 | Trg Leona Štuklja               | ob cesti | Z01  | 1.00 | 30   | 63 m
P07 | Vetrinjska ulica                | ob cesti | Z01  | 1.00 | 22   | 251 m
...
```

## Delovanje programa

1. **Branje:** `xml.etree.ElementTree` prebere vse tri datoteke, podatke deserializira v objekte (`dataclass`: `Cona`, `Parkirisce`, `Cilj`). Program preveri, da so ID-ji unikatni.
2. **Povezovanje:** parkirišče dobi svojo cono prek `idCone`, cilj pa privzeto parkirišče prek `idParkirisca`. Neveljavna povezava se izpiše kot opozorilo.
3. **Filtriranje:** po razdalji (Haversine), ceni, kapaciteti, tipu in brezplačnem vikendu.
4. **Izvoz v JSON:** `filtrirano.json` je seznam objektov, vsak vsebuje podatke parkirišča in vgnezdeno cono.
5. **Izvoz v XML:** `filtrirano.xml` vsebuje iste filtrirane zapise.

## Struktura

```
data/cone.xml, data/parkirisca.xml, data/cilji.xml
app.py
filtrirano.json, filtrirano.xml   (primer izhoda)
README.md
```
