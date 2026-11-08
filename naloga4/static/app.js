// Obrazec -> POST /api/priporoci. Datum in ura se ob odprtju nastavita na trenutni čas v brskalniku.

const $ = (id) => document.getElementById(id);
const eur = (x) => (x == null ? "–" : Number(x).toLocaleString("sl-SI", { style: "currency", currency: "EUR" }));

function nastaviCas() {
  const zdaj = new Date();
  const p = (n) => String(n).padStart(2, "0");
  $("datum").value = `${zdaj.getFullYear()}-${p(zdaj.getMonth() + 1)}-${p(zdaj.getDate())}`;
  $("ura").value = `${p(zdaj.getHours())}:${p(zdaj.getMinutes())}`;
}

function pokaziNapako(sporocilo) {
  $("napaka").textContent = sporocilo;
  $("napaka").hidden = !sporocilo;
}

function izpisi(d) {
  const v = d.vreme;
  $("vreme").textContent = v ? `Vreme ob prihodu: ${v.opis}, ${v.temperatura_c} °C, verjetnost padavin ${v.verjetnost_padavin_pct} %` : "Vremenska napoved za ta termin ni na voljo.";
  $("povzetek").textContent = d.odgovor.povzetek;
  $("kartice").replaceChildren(...d.odgovor.priporocila.map((p, i) => {
    const k = document.createElement("div");
    k.className = "kartica";
    const naslov = document.createElement("h3");
    naslov.textContent = `${i + 1}. ${p.ime}`;
    const meta = document.createElement("div");
    meta.className = "meta";
    meta.textContent = `${p.tip} · ocena cene ${eur(p.ocenjena_cena_eur)} · hoja ${p.pes_minut == null ? "neznana" : p.pes_minut + " min"}`;
    const razlog = document.createElement("div");
    razlog.textContent = p.razlog;
    k.append(naslov, meta, razlog);
    return k;
  }));
  $("opozorilo").textContent = [d.odgovor.opozorilo, ...d.opozorila].filter(Boolean).join(" ");
  $("tabela").tBodies[0].replaceChildren(...d.opcije.map((o) => {
    const tr = document.createElement("tr");
    const celice = [o.ime, o.pes_minut == null ? "–" : `${o.pes_minut} min`, typeof o.cena_na_uro === "number" ? eur(o.cena_na_uro) : `${o.cena_na_uro} €`, eur(o.ocenjena_cena_eur), o.opomba || ""];
    celice.forEach((t, i) => { const td = document.createElement("td"); td.textContent = t; if (i >= 1 && i <= 3) td.className = "st"; tr.append(td); });
    return tr;
  }));
  $("prompt").textContent = d.prompt.map((m) => `[${m.role}]\n${m.content}`).join("\n\n");
  $("rezultat").hidden = false;
}

$("obrazec").addEventListener("submit", async (e) => {
  e.preventDefault();
  pokaziNapako("");
  $("gumb").disabled = true;
  $("gumb").textContent = "Razmišljam ...";
  try {
    const odgovor = await fetch("/api/priporoci", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        cilj: $("cilj").value, datum: $("datum").value, ura: $("ura").value, trajanje_ur: Number($("trajanje").value),
        namen: $("namen").value, vozilo: $("vozilo").value, max_pes_min: Number($("hoja").value),
      }),
    });
    const telo = await odgovor.json();
    if (!odgovor.ok) throw new Error(telo.napaka || (telo.detail ? "Neveljaven vnos v obrazcu." : `Napaka ${odgovor.status}`));
    izpisi(telo);
  } catch (napaka) {
    $("rezultat").hidden = true;
    pokaziNapako(napaka.message);
  } finally {
    $("gumb").disabled = false;
    $("gumb").textContent = "Predlagaj parkiranje";
  }
});

nastaviCas();
fetch("/api/stanje").then((r) => r.json()).then((s) => {
  if (!s.llmNastavljen) { $("opozorilo-llm").textContent = "API ključ za Groq ni nastavljen (datoteka .env, glej README)."; $("opozorilo-llm").hidden = false; }
});
