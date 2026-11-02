// Stran ob odprtju pridobi podatke iz /api/* (strežnik jih filtrira in združuje iz PX tabel SURS)
// in nariše grafe s knjižnjico Chart.js. Ob vsaki spremembi kontrole se podatki ponovno naložijo.

const MARIBOR = "Maribor";
const BARVE = ["#2f6f9f", "#c2410c", "#2f855a", "#8a5cc2", "#b7791f", "#0e7490", "#9b2c5b", "#64748b"];
const graf = {}; // id canvasa -> Chart (da ga lahko uničimo pred ponovnim risanjem)

const $ = (id) => document.getElementById(id);
const st = (x, mest = 0) => (x == null ? "–" : Number(x).toLocaleString("sl-SI", { maximumFractionDigits: mest, minimumFractionDigits: mest }));

function css(ime) { return getComputedStyle(document.documentElement).getPropertyValue(ime).trim(); }

async function api(pot, parametri = {}) {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(parametri)) {
    if (Array.isArray(v)) v.forEach((x) => q.append(k, x));
    else if (v != null && v !== "") q.set(k, v);
  }
  const odgovor = await fetch(`/api/${pot}${q.toString() ? "?" + q : ""}`);
  const telo = await odgovor.json().catch(() => ({}));
  if (!odgovor.ok) throw new Error(telo.napaka || `Napaka ${odgovor.status}`);
  return telo;
}

function napaka(sporocilo) {
  const el = document.createElement("div");
  el.className = "napaka";
  el.textContent = sporocilo;
  $("kartice").after(el);
  setTimeout(() => el.remove(), 8000);
}

// obdela napako ene plošče, da ostale grafe še vedno narišemo
async function varno(fn) {
  try { await fn(); } catch (e) { napaka(e.message); console.error(e); }
}

function narisi(id, config) {
  if (graf[id]) graf[id].destroy();
  Chart.defaults.color = css("--tiho");
  Chart.defaults.borderColor = css("--os");
  graf[id] = new Chart($(id), config);
}

function napolni(select, vrednosti, izbrana, oznake) {
  select.replaceChildren(...vrednosti.map((v, i) => {
    const o = document.createElement("option");
    o.value = v; o.textContent = oznake ? oznake[i] : v;
    if (v === izbrana) o.selected = true;
    return o;
  }));
}

// ---------------------------------------------------------------- kartice
async function kartice() {
  const p = await api("povzetek");
  const k = [
    [st(p.vozila.stevilo), `navadnih osebnih avtomobilov v Mariboru (${p.vozila.leto}); ${p.vozila.rang}. mesto, ${st(p.vozila.delezVSloveniji, 1)} % vseh v Sloveniji`],
    [st(p.motorizacija.vrednost, 0), `avtomobilov na 1.000 prebivalcev (${p.motorizacija.leto}); Slovenija ${st(p.motorizacija.slovenija, 0)}`],
    [st(p.elektrika.delez, 1) + " %", `osebnih avtomobilov z električnim pogonom v Sloveniji (${p.elektrika.leto})`],
    [st(p.poti.delezAvto, 1) + " %", `poti v MO Maribor z osebnim avtomobilom (${p.poti.leto}), v avtu je v povprečju ${st(p.poti.zasedenostAvta, 2)} oseb`],
    [st(p.parkiranje.delezJavno, 1) + " %", `vozačev na delo parkira na javnem mestu (${p.parkiranje.leto}), ostali pri delodajalcu`],
  ];
  $("kartice").replaceChildren(...k.map(([v, o]) => {
    const d = document.createElement("div");
    d.className = "kartica";
    d.innerHTML = `<div class="vrednost"></div><div class="oznaka"></div>`;
    d.firstChild.textContent = v; d.lastChild.textContent = o;
    return d;
  }));
}

// ---------------------------------------------------------------- vozni park
async function trend() {
  const vrste = [...document.querySelectorAll("#v-vrste input:checked")].map((c) => c.value);
  if (!vrste.length) { napaka("Izberi vsaj eno vrsto vozil."); return; }
  const d = await api("vozila/trend", { obcina: $("v-obcina").value, vrste, od: $("v-od").value });
  const polje = $("v-nacin").value;
  narisi("g-trend", {
    type: "line",
    data: {
      labels: d.leta,
      datasets: d.serije.map((s, i) => ({ label: s.vrsta, data: s[polje], borderColor: BARVE[i % BARVE.length], backgroundColor: BARVE[i % BARVE.length], tension: 0.2, spanGaps: true })),
    },
    options: { maintainAspectRatio: false, plugins: { title: { display: true, text: `${d.obcina}: ${polje === "indeks" ? "indeks rasti" : "število vozil"}` } }, scales: { y: { beginAtZero: polje !== "indeks" } } },
  });
  const prva = d.serije[0];
  const zadnja = prva.vrednosti.at(-1), zacetna = prva.vrednosti.find((x) => x != null);
  $("o-trend").textContent = zacetna ? `${prva.vrsta}: ${st(zacetna)} (${d.leta[0]}) → ${st(zadnja)} (${d.leta.at(-1)}), ${st(100 * (zadnja / zacetna - 1), 1)} %.` : "";
}

async function lestvica() {
  const d = await api("vozila/lestvica", { leto: $("l-leto").value, vrsta: $("l-vrsta").value, top: $("l-top").value });
  narisi("g-lestvica", {
    type: "bar",
    data: {
      labels: d.postavke.map((p) => `${p.rang}. ${p.obcina}`),
      datasets: [{ label: d.vrsta, data: d.postavke.map((p) => p.vrednost), backgroundColor: d.postavke.map((p) => (p.obcina === MARIBOR ? css("--poudarek") : css("--osnova"))) }],
    },
    options: { indexAxis: "y", maintainAspectRatio: false, plugins: { legend: { display: false }, title: { display: true, text: `${d.vrsta}, ${d.leto}` } } },
  });
  const m = d.postavke.find((p) => p.obcina === MARIBOR);
  $("o-lestvica").textContent = m ? `Maribor je ${m.rang}. od ${d.steviloObcin} občin (${st(m.delezVSloveniji, 1)} % od ${st(d.slovenija)} vozil v Sloveniji).` : "";
}

// ---------------------------------------------------------------- motorizacija
async function motorizacija() {
  const prim = $("m-primerjava").value;
  const d = await api("motorizacija/trend", { obcine: [MARIBOR, prim, "SLOVENIJA"].filter((x, i, a) => a.indexOf(x) === i) });
  narisi("g-motorizacija", {
    type: "line",
    data: { labels: d.leta, datasets: d.serije.map((s, i) => ({ label: s.obcina, data: s.vrednosti, borderColor: s.obcina === MARIBOR ? css("--poudarek") : BARVE[(i + 2) % BARVE.length], backgroundColor: s.obcina === MARIBOR ? css("--poudarek") : BARVE[(i + 2) % BARVE.length], tension: 0.2, spanGaps: true })) },
    options: { maintainAspectRatio: false, scales: { y: { title: { display: true, text: "avtomobilov na 1.000 prebivalcev" } } } },
  });
}

async function motLestvica() {
  const d = await api("motorizacija/lestvica", { leto: $("ml-leto").value, top: 10 });
  narisi("g-motlestvica", {
    type: "bar",
    data: {
      labels: d.postavke.map((p) => `${p.rang}. ${p.obcina}`),
      datasets: [{ data: d.postavke.map((p) => p.vrednost), backgroundColor: d.postavke.map((p) => (p.obcina === MARIBOR ? css("--poudarek") : css("--osnova"))) }],
    },
    options: { indexAxis: "y", maintainAspectRatio: false, plugins: { legend: { display: false }, title: { display: true, text: `Avtomobilov na 1.000 prebivalcev, ${d.leto}` } } },
  });
  const m = d.postavke.find((p) => p.obcina === MARIBOR);
  $("o-motlestvica").textContent = m ? `Maribor: ${st(m.vrednost, 0)} (${m.rang}. od ${d.steviloObcin}); povprečje Slovenije ${st(d.slovenija, 0)}.` : "";
}

// ---------------------------------------------------------------- pogon
async function pogon() {
  const d = await api("pogon", { vrsta: $("p-vrsta").value, meritev: $("p-meritev").value });
  const polje = $("p-nacin").value;
  narisi("g-pogon", {
    type: "bar",
    data: { labels: d.leta, datasets: d.serije.map((s, i) => ({ label: s.pogon, data: s[polje], backgroundColor: BARVE[i % BARVE.length] })) },
    options: {
      maintainAspectRatio: false,
      plugins: { title: { display: true, text: `${d.vrsta} (${d.meritev})` } },
      scales: { x: { stacked: true }, y: { stacked: true, max: polje === "delez" ? 100 : undefined, title: { display: true, text: polje === "delez" ? "%" : "število" } } },
    },
  });
}

// ---------------------------------------------------------------- poti
async function poti() {
  const d = await api("poti", { leto: $("t-leto").value });
  const imena = d.obcine[0].nacini.map((n) => n.nacin);
  narisi("g-poti", {
    type: "bar",
    data: { labels: imena, datasets: d.obcine.map((o, i) => ({ label: `MO ${o.mestnaObcina}`, data: o.nacini.map((n) => n.delez), backgroundColor: o.mestnaObcina === MARIBOR ? css("--poudarek") : css("--osnova") })) },
    options: { maintainAspectRatio: false, plugins: { title: { display: true, text: `Delež poti po glavnem prevoznem sredstvu, ${d.leto}` } }, scales: { y: { title: { display: true, text: "% vseh poti" } } } },
  });
  $("o-poti").textContent = d.obcine.map((o) => `${o.mestnaObcina}: ${st(o.skupaj)} tisoč poti, v avtu je v povprečju ${st(o.zasedenostAvta, 2)} oseb`).join(" · ") + ". Podatki so na voljo samo za izbrana leta.";
}

// ---------------------------------------------------------------- parkiranje
async function parkiranje() {
  const d = await api("parkiranje", { leto: $("k-leto").value, spol: $("k-spol").value });
  narisi("g-parkiranje", {
    type: "doughnut",
    data: { labels: d.skupine.map((s) => s.skupina), datasets: [{ data: d.skupine.map((s) => s.stevilo), backgroundColor: BARVE, borderColor: css("--kartica") }] },
    options: { maintainAspectRatio: false, plugins: { title: { display: true, text: `Kraj parkiranja, ${d.leto}` } } },
  });
  $("t-parkiranje").tBodies[0].replaceChildren(...d.podrobno.map((p) => {
    const tr = document.createElement("tr");
    tr.innerHTML = "<td></td><td class='st'></td><td class='st'></td>";
    tr.children[0].textContent = p.kraj;
    tr.children[1].textContent = st(p.stevilo);
    tr.children[2].textContent = p.delez == null ? "–" : st(p.delez, 1) + " %";
    return tr;
  }));
  $("o-parkiranje").textContent = `Skupaj ${st(d.skupaj)} oseb, ki so na delo prišle z avtom. »–« pomeni, da SURS podatka ne objavlja.`;
}

// ---------------------------------------------------------------- zagon
async function zagon() {
  await varno(kartice);

  await varno(async () => {
    const iz = await api("vozila/izbire");
    napolni($("v-obcina"), iz.obcine, iz.privzeto.obcina);
    napolni($("v-od"), iz.leta, iz.leta[0]);
    $("v-vrste").append(...iz.vrste.map((v) => {
      const l = document.createElement("label");
      l.innerHTML = "<input type='checkbox'> <span></span>";
      l.firstChild.value = v; l.firstChild.checked = iz.privzeto.vrste.includes(v);
      l.lastChild.textContent = v;
      return l;
    }));
    napolni($("l-leto"), iz.leta, iz.leta.at(-1));
    napolni($("l-vrsta"), iz.vrste, iz.privzeto.vrste[0]);
    napolni($("m-primerjava"), iz.obcine.filter((o) => o !== MARIBOR && o !== "SLOVENIJA"), "Ljubljana");
    await Promise.all([varno(trend), varno(lestvica)]);
  });

  await varno(async () => {
    const t = await api("motorizacija/trend", { obcine: [MARIBOR] });
    napolni($("ml-leto"), t.leta, t.leta.at(-1));
    await Promise.all([varno(motorizacija), varno(motLestvica)]);
  });

  await varno(async () => {
    const iz = await api("pogon/izbire");
    napolni($("p-vrsta"), iz.vrste, iz.privzeto.vrsta);
    napolni($("p-meritev"), iz.meritve, iz.privzeto.meritev);
    await pogon();
  });

  await varno(async () => {
    const d = await api("poti");
    napolni($("t-leto"), d.leta, d.leta.at(-1));
    await poti();
  });

  await varno(async () => {
    const d = await api("parkiranje");
    napolni($("k-leto"), d.leta, d.leta.at(-1));
    napolni($("k-spol"), ["TOT", "1", "2"], "TOT", d.spoli);
    await parkiranje();
  });

  await varno(async () => {
    const m = await api("meta");
    $("noga").textContent = `Viri: ${m.izdajatelj}, licenca ${m.licenca}. Tabele: ` + m.viri.map((v) => v.koda).join(", ") + ". Zadnja posodobitev podatkov: " + m.viri.map((v) => v.zadnjaPosodobitev?.slice(0, 8)).filter(Boolean).sort().at(-1) + ".";
  });

  // ob spremembi kontrole se ustrezen graf ponovno naloži
  const povezi = (ids, fn) => ids.forEach((id) => $(id).addEventListener("change", () => varno(fn)));
  povezi(["v-obcina", "v-od", "v-nacin"], trend);
  $("v-vrste").addEventListener("change", () => varno(trend));
  povezi(["l-leto", "l-vrsta", "l-top"], lestvica);
  povezi(["m-primerjava"], motorizacija);
  povezi(["ml-leto"], motLestvica);
  povezi(["p-vrsta", "p-meritev", "p-nacin"], pogon);
  povezi(["t-leto"], poti);
  povezi(["k-leto", "k-spol"], parkiranje);
}

document.addEventListener("DOMContentLoaded", zagon);
