# Naloga 4: Podatki iz LLM (Groq, Llama)

Aplikacija pomaga izbrati parkirišče v Mariboru. Uporabnik v obrazec vnese cilj, datum, uro, trajanje, namen,
vozilo in največjo razdaljo hoje. Strežnik iz tega **dinamično sestavi vprašanje (prompt)** za jezikovni model, model
vrne **JSON**, ki ga aplikacija prebere v razred in prikaže.

## Kako deluje

```
obrazec  ->  POST /api/priporoci
   |-- geo.py       cilj in parkirišča -> koordinate (Nominatim), razdalje (haversine)
   |-- vreme.py     vreme za izbrani dan in uro (Open-Meteo)
   |-- kontekst.py  plačljivost (delavnik 6–22, sobota 8–13, nedelja brezplačno), ocena cene iz cenika (Naloga 2)
   |-- prompt.py    iz vsega zgoraj sestavi sporočila za model
   |-- llm.py       klic Groq (model Llama), razčlenitev odgovora v OdgovorLLM, ponovni poskus ob napaki
   `-- app.py       preveri odgovor, številke vzame iz izračuna, vrne JSON strani
```

- **Prompt ni statičen:** vsebuje cilj, dan v tednu, uro, namen, vozilo, vreme in izračunane podatke za vsako parkirišče.
  Ob vsakem vnosu je drugačen; na strani ga vidiš pod »Vprašanje, poslano modelu«.
- **Vhodni podatki:** polja obrazca, dropdown meniji ter trenutni čas v brskalniku (datum in ura se ob odprtju nastavita
  na zdaj). Vreme je odvisno od izbranega termina.
- **JSON in razred:** model mora vrniti obliko iz `modeli.py` (`OdgovorLLM` s seznamom `Priporocilo`). Groq dobi
  `response_format: json_object`, odgovor pa še preveri Pydantic. Če oblika ni pravilna (manjka polje, napačen tip),
  model dobi opis napake in vprašamo ga še enkrat; po dveh neuspehih aplikacija javi napako.
- **Zaščita pred izmišljotinami:** model sme izbirati le med možnostmi, ki jih poda strežnik. Imena, ki jih ni na
  seznamu, se izpustijo, cena in čas hoje pa se vedno vzameta iz izračuna, ne iz besedila modela.

## Zagon

1. Brezplačen račun in ključ: https://console.groq.com (API Keys).
2. V mapi `naloga4` ustvari datoteko `.env` (vzorec je `.env.example`):
   ```
   GROQ_API_KEY=tvoj_kljuc
   ```
   `.env` je v `.gitignore`, zato ključ ne konča na GitHubu. Model se ob prvem klicu izbere
   sam iz Groqovega seznama (prednost ima Llama 70b); po želji ga določiš z `GROQ_MODEL`
   (seznam: https://console.groq.com/docs/models).
3. Namestitev in zagon:
   ```
   py -m pip install -r requirements.txt
   py app.py
   ```
   Odpri http://127.0.0.1:8000.

## Testi

```
py -m unittest discover -s tests
```

Testi ne potrebujejo interneta ali ključa: model, geokodiranje in vreme zamenja lažna funkcija.

## Omejitve

- Marprom ne objavlja, katere ulice spadajo v katero območno kodo bele cone, zato je pri beli coni cena le spodnja
  ocena, razdalja pa ni znana.
- Koordinate parkirišč pridejo iz Nominatim (OpenStreetMap) in so lahko približne (središče ulice); hoja je
  izračunana iz zračne razdalje ×1,3 pri 80 m/min.
- Zasedenosti parkirišč ni; model ne ve, ali je prosto mesto.
- Praznikov aplikacija ne pozna (plačljivost po koledarju tedna).
- Vreme je na voljo za okoli 16 dni vnaprej; za druge datume model dobi »napoved ni na voljo«.
