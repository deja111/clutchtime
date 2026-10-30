"""
model.py
---------
Procena verovatnoće da igrač pređe liniju (preko/ispod) za propove iz kvote.py.
Koristi ga sajt.py (stranica propovi.html).

Kako se računa očekivana vrednost (npr. poeni):
    1. Učinak po minutu ove sezone; skorije utakmice vrede više (poluživot 6 utakmica).
       Na početku sezone se meša sa prošlom sezonom, da 3-4 utakmice ne odluče sve.
    2. Očekivani minuti: mešavina skorih (poluživot 3) i sezonskog proseka (trend minutaže).
    3. Protivnik: koliko dozvoljava igračima te pozicije u toj kategoriji, u odnosu na
       prosek lige. Ublaženo prema 1 kad protivnik ima malo odigranih utakmica.
    4. Kod kuće / u gostima: igračev odnos, jako ublažen (najviše ±6%).
Raspodela: negativna binomna (brojevi poena/skokova su "rasutiji" od Poasonove),
rasipanje se procenjuje iz igračevih utakmica. P(preko 14.5) = P(X >= 15).

Kladionica: 1/kvota, normalizovano da preko + ispod = 100% (bez marže).
Konačna procena je pola model, pola kladionica (TEZINA_MODELA, objašnjenje niže).
Očekivani povraćaj (EV) = procena × kvota - 1. Rang je po EV.

Ovo je statistička procena, ne savet za klađenje. Tačnost se proverava kroz arhivu kvota.
"""

import math
from collections import defaultdict

POLUZIVOT_UCINAK = 6.0
POLUZIVOT_MINUTI = 3.0
PRIOR_UTAKMICA = 4.0          # koliko "utakmica" vredi prošla sezona kao početna procena
PROTIVNIK_UBLAZI = 8.0        # težina protivnika = n / (n + 8)
DOMACIN_MAX = 0.06
MALO_UTAKMICA = 5             # ispod ovoga: oznaka "malo podataka"
# Konačna procena = kladionica + TEZINA_MODELA × (model - kladionica).
# Provera na sezonama 2024-25 i 2025-26 (procena iz ranijih utakmica, poređenje sa stvarnim):
# očekivana vrednost je bez sistematske greške, ali na liniji blizu proseka model jedva bolje od 50/50
# (Brier 0,249). Kladionice postavljaju liniju baš tu i znaju više (sastavi, vesti), pa model
# ublažavamo dok arhiva kvota ne pokaže koliko mu se sme verovati.
TEZINA_MODELA = 0.5

# naš naziv tipa -> kolone iz tabele statistika koje se sabiraju
KOLONE = {
    "poeni": ("poeni",),
    "skokovi": ("skokovi_ukupno",),
    "asistencije": ("asistencije",),
    "trojke": ("sut3_pogodjeno",),
    "ukradene": ("ukradene",),
    "blokade": ("blokade",),
    "PSA": ("poeni", "skokovi_ukupno", "asistencije"),
    "PS": ("poeni", "skokovi_ukupno"),
    "PA": ("poeni", "asistencije"),
    "SA": ("skokovi_ukupno", "asistencije"),
}
NAZIV_TIPA = {"poeni": "Poeni", "skokovi": "Skokovi", "asistencije": "Asistencije", "trojke": "Trojke",
              "ukradene": "Ukradene", "blokade": "Blokade", "PSA": "Poeni+skok+asist",
              "PS": "Poeni+skokovi", "PA": "Poeni+asist", "SA": "Skok+asist"}


def vrednost(r, tip):
    return sum(r[k] or 0 for k in KOLONE[tip])


def tezine(n, poluzivot):
    """Najnovija utakmica (poslednja u listi) ima težinu 1, svaka starija manje."""
    return [0.5 ** ((n - 1 - i) / poluzivot) for i in range(n)]


# ----------------------------- RASPODELA -----------------------------
def p_preko(ocekivano, rasipanje, linija):
    """P(X > linija) za negativnu binomnu sa srednjom vrednošću i odnosom varijansa/srednja."""
    granica = math.floor(linija)  # preko 14.5 = bar 15
    if ocekivano <= 0:
        return 0.0
    if rasipanje <= 1.05:  # Poasonova
        cdf, pmf = 0.0, math.exp(-ocekivano)
        for k in range(granica + 1):
            if k:
                pmf *= ocekivano / k
            cdf += pmf
        return max(0.0, min(1.0, 1 - cdf))
    p = 1 / rasipanje
    r = ocekivano / (rasipanje - 1)
    cdf = 0.0
    for k in range(granica + 1):
        cdf += math.exp(math.lgamma(k + r) - math.lgamma(r) - math.lgamma(k + 1)
                        + r * math.log(p) + k * math.log(1 - p))
    return max(0.0, min(1.0, 1 - cdf))


# ----------------------------- PROTIVNIK -----------------------------
def faktori_protivnika(statistika, igraci, sezona):
    """{(protivnik, pozicija, tip): (odnos prema proseku lige, broj utakmica)} za tekuću sezonu."""
    po_mecu = defaultdict(lambda: defaultdict(float))  # (protivnik, poz, tip) -> {utakmica: zbir}
    for r in statistika:
        if r["sezona"] != sezona or not r["igrao"]:
            continue
        poz = (igraci.get(r["igrac_id"]) or {}).get("pozicija")
        if not poz:
            continue
        for tip in KOLONE:
            po_mecu[(r["protivnik"], poz, tip)][r["sifra_utakmice"]] += vrednost(r, tip)
    proseci = {k: sum(v.values()) / len(v) for k, v in po_mecu.items()}
    liga = defaultdict(list)
    for (tim, poz, tip), x in proseci.items():
        liga[(poz, tip)].append(x)
    liga = {k: sum(v) / len(v) for k, v in liga.items()}
    return {k: (x / liga[(k[1], k[2])] if liga[(k[1], k[2])] else 1.0, len(po_mecu[k]))
            for k, x in proseci.items()}


# ----------------------------- PROCENA -----------------------------
def proceni_igraca(ut_sezona, ut_prosla, tip, kod_kuce, protivnik_faktor):
    """Očekivana vrednost, rasipanje i objašnjenja za jednog igrača i jedan tip."""
    n = len(ut_sezona)
    vr = [vrednost(r, tip) for r in ut_sezona]
    mi = [r["minuti"] or 0 for r in ut_sezona]

    w = tezine(n, POLUZIVOT_UCINAK)
    min_w = sum(a * b for a, b in zip(w, mi))
    po_minutu = sum(a * b for a, b in zip(w, vr)) / min_w if min_w else 0
    n_ef = sum(w)
    min_prosla = sum(r["minuti"] or 0 for r in ut_prosla)
    prosla_prosek = sum(vrednost(r, tip) for r in ut_prosla) / len(ut_prosla) if min_prosla >= 100 else None
    if min_prosla >= 100:
        po_minutu_prosla = sum(vrednost(r, tip) for r in ut_prosla) / min_prosla
        po_minutu = (n_ef * po_minutu + PRIOR_UTAKMICA * po_minutu_prosla) / (n_ef + PRIOR_UTAKMICA)

    wm = tezine(n, POLUZIVOT_MINUTI)
    min_skoro = sum(a * b for a, b in zip(wm, mi)) / sum(wm)
    min_sezona = sum(mi) / n
    minuti = 0.6 * min_skoro + 0.4 * min_sezona

    # Kod kuće / u gostima (po minutu), jako ublaženo
    dom = [(v, m) for v, m, r in zip(vr, mi, ut_sezona) if r["domacin"] == (1 if kod_kuce else 0)]
    f_dom = 1.0
    if len(dom) >= 3 and po_minutu and sum(m for _, m in dom) and sum(vr):
        odnos = (sum(v for v, _ in dom) / sum(m for _, m in dom)) / (sum(vr) / sum(mi) if sum(mi) else 1)
        f_dom = max(1 - DOMACIN_MAX, min(1 + DOMACIN_MAX, 1 + 0.25 * (odnos - 1)))

    odnos_p, n_p = protivnik_faktor or (1.0, 0)
    f_prot = 1 + (odnos_p - 1) * n_p / (n_p + PROTIVNIK_UBLAZI)

    ocekivano = po_minutu * minuti * f_dom * f_prot

    # Rasipanje: varijansa/srednja vrednost iz utakmica ove i prošle sezone (između 1 i 3)
    sve = vr + [vrednost(r, tip) for r in ut_prosla]
    sr = sum(sve) / len(sve)
    var = sum((x - sr) ** 2 for x in sve) / max(len(sve) - 1, 1)
    rasipanje = max(1.0, min(3.0, var / sr if sr else 1.0))

    return {"ocekivano": ocekivano, "rasipanje": rasipanje, "minuti": minuti, "min_sezona": min_sezona,
            "sezona_prosek": sum(vr) / n, "poslednjih5": sum(vr[-5:]) / len(vr[-5:]),
            "prosla_prosek": prosla_prosek if n_ef < 3 * PRIOR_UTAKMICA else None,  # pomenuti samo kad dosta utiče
            "f_dom": f_dom, "f_prot": f_prot, "n_prot": n_p, "vrednosti": vr}


def glavne_linije(propovi):
    """Superbet nudi više linija po igraču i tipu; zadržavamo onu sa najujednačenijim kvotama."""
    najbolje = {}
    for p in propovi:
        k = (p["igrac_id"], p["sifra_utakmice"], p["tip"])
        razlika = abs(1 / p["preko"] - 1 / p["ispod"])
        if k not in najbolje or razlika < najbolje[k][0]:
            najbolje[k] = (razlika, p)
    return [p for _, p in najbolje.values()]


def proceni(propovi, statistika, igraci, sezona, utakmice, povrede=None):
    """Za svaki prop (glavna linija): verovatnoće, predlog strane, EV i objašnjenja."""
    povrede = povrede or {}
    po_igracu = defaultdict(list)
    po_igracu_prosla = defaultdict(list)
    for r in statistika:
        if not r["igrao"]:
            continue
        if r["sezona"] == sezona:
            po_igracu[r["igrac_id"]].append(r)
        elif r["sezona"] == sezona - 1:
            po_igracu_prosla[r["igrac_id"]].append(r)
    protivnik = faktori_protivnika(statistika, igraci, sezona)
    mecevi = {(u["sezona"], u["sifra_utakmice"]): u for u in utakmice}

    rezultati = []
    for p in glavne_linije(propovi):
        if p["tip"] not in KOLONE:
            continue
        u = mecevi.get((p["sezona"], p["sifra_utakmice"]))
        ut = po_igracu.get(p["igrac_id"], [])
        if not u or u["odigrana"] or len(ut) < 2:
            continue
        status = povrede.get(p["igrac_id"])
        if status and status.get("klasa") == "st-ne":
            continue  # ne igra
        kod_kuce = u["domacin"] == p["tim"]
        prot = u["gost"] if kod_kuce else u["domacin"]
        poz = (igraci.get(p["igrac_id"]) or {}).get("pozicija")

        x = proceni_igraca(ut, po_igracu_prosla.get(p["igrac_id"], []), p["tip"], kod_kuce,
                           protivnik.get((prot, poz, p["tip"])))
        kladionica = (1 / p["preko"]) / (1 / p["preko"] + 1 / p["ispod"])
        model = p_preko(x["ocekivano"], x["rasipanje"], p["linija"])
        verovatnoca = kladionica + TEZINA_MODELA * (model - kladionica)
        ev_preko = verovatnoca * p["preko"] - 1
        ev_ispod = (1 - verovatnoca) * p["ispod"] - 1
        preko = ev_preko >= ev_ispod
        poslednjih10 = x["vrednosti"][-10:]
        rezultati.append({
            **p, "protivnik": prot, "kod_kuce": kod_kuce, "pozicija": poz,
            "strana": "preko" if preko else "ispod",
            "kvota": p["preko"] if preko else p["ispod"],
            "p_model": verovatnoca if preko else 1 - verovatnoca,
            "p_cist_model": model if preko else 1 - model,
            "p_kladionica": kladionica if preko else 1 - kladionica,
            "ev": ev_preko if preko else ev_ispod,
            "presao": sum(1 for v in poslednjih10 if (v > p["linija"]) == preko),
            "od": len(poslednjih10),
            "malo_podataka": len(ut) < MALO_UTAKMICA,
            "upitan": bool(status) and status.get("klasa") == "st-up",
            **x,
        })
    rezultati.sort(key=lambda r: -r["ev"])
    return rezultati
