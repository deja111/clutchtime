"""
model.py
---------
Procena verovatnoće da igrač pređe liniju (preko/ispod) za propove iz kvote.py.
Koristi ga sajt.py (stranica propovi.html).

Kako se računa očekivana vrednost (npr. poeni):
    1. Učinak po minutu u poslednjih 5 utakmica (prošla sezona se ne koristi).
    2. Očekivani minuti: prosek poslednjih 5 utakmica.
    3. Protivnik: koliko dozvoljava igračima te pozicije u toj kategoriji, u odnosu na
       prosek lige. Ublaženo prema 1 kad protivnik ima malo odigranih utakmica.
    4. Kod kuće / u gostima: igračev odnos, jako ublažen (najviše ±6%).
Raspodela: negativna binomna (brojevi poena/skokova su "rasutiji" od Poasonove),
rasipanje se procenjuje iz igračevih utakmica. P(preko 14.5) = P(X >= 15).

Kladionica: 1/kvota, normalizovano da preko + ispod = 100% (bez marže).
Konačna procena je 30% model, 70% kladionica (TEZINA_MODELA, objašnjenje niže).
Očekivani povraćaj (EV) = procena × kvota - 1. Rang je po EV.

Ovo je statistička procena, ne savet za klađenje. Tačnost se proverava kroz arhivu kvota.
"""

import math
from collections import defaultdict

# Učinak i minuti iz poslednjih UZORAK utakmica tekuće sezone, bez prošle sezone (Dejanova odluka 30.10.2026).
# Provera na 9.562 utakmice: ponderisana cela sezona (+ prošla) imala je manju grešku (poeni 5,49 prema 5,78),
# ali je izabrano jednostavnije i "svežije" pravilo; kalibracija je ponovo naučena za ovaj način.
UZORAK = 5
PROTIVNIK_UBLAZI = 8.0        # težina protivnika = n / (n + 8)
DOMACIN_MAX = 0.06
MALO_UTAKMICA = 5             # ispod ovoga: oznaka "malo podataka"
# Tipično rasipanje (varijansa/srednja vrednost) u ligi: medijana igrača sa 15+ utakmica (10+ min), 2023-2026
RASIPANJE_LIGA = {"poeni": 2.73, "skokovi": 1.14, "asistencije": 1.11, "trojke": 1.04, "ukradene": 1.02,
                  "blokade": 1.03, "PSA": 2.64, "PS": 2.74, "PA": 2.60, "SA": 1.31}
RASIPANJE_UTAKMICA = 10       # koliko "utakmica" vredi tipična vrednost lige
VELIKA_RAZLIKA = 0.25         # očekivano se razlikuje od linije za 25%+ -> upozorenje "proveri vesti"
# Konačna procena = kladionica + TEZINA_MODELA × (model - kladionica).
# Provera na sezonama 2024-25 i 2025-26 (procena iz ranijih utakmica, poređenje sa stvarnim):
# očekivana vrednost je bez sistematske greške, ali na liniji blizu proseka model jedva bolje od 50/50
# (Brier 0,249). Kladionice postavljaju liniju baš tu i znaju više (sastavi, vesti), pa model
# ublažavamo dok arhiva kvota ne pokaže koliko mu se sme verovati.
# 30.10.2026: smanjeno sa 0,5 na 0,3 (sa 0,5 je 124 od 406 propova imalo "prednost" 5%+, nerealno).
TEZINA_MODELA = 0.3
# Ocena predloga prema očekivanom povraćaju (EV); "sumnjivi" (linija daleko od procene) su najviše "slaba"
OCENA_JAKA = 0.08
OCENA_SREDNJA = 0.04


def ocena(ev, sumnjivo):
    if ev <= 0:
        return "nema"
    if sumnjivo or ev < OCENA_SREDNJA:
        return "slaba"
    return "jaka" if ev >= OCENA_JAKA else "srednja"

# Kalibracija (Platt): p_kal = sigmoid(a + b * logit(p_model)), po kategoriji.
# Naučeno na sezonama 2024-25 i 2025-26 (linije na proseku ±2), provereno: učeno na 2024-25,
# testirano na 2025-26 -> Brier bolji u svim kategorijama. b < 1 = model je bio previše samouveren.
KALIBRACIJA = {
    # Naučeno ponovo 30.10.2026. za model "poslednjih 5 utakmica" (b manje = taj model je samouvereniji)
    "poeni": (0.034, 0.731), "skokovi": (-0.043, 0.836), "asistencije": (-0.091, 0.824),
    "trojke": (-0.181, 0.805), "ukradene": (-0.368, 0.803), "blokade": (-0.557, 0.865),
    "PSA": (0.030, 0.764), "PS": (0.027, 0.747), "PA": (0.041, 0.764), "SA": (-0.016, 0.842),
}


def kalibrisi(p, tip):
    a, b = KALIBRACIJA.get(tip, (0.0, 1.0))
    p = min(max(p, 1e-4), 1 - 1e-4)
    return 1 / (1 + math.exp(-(a + b * math.log(p / (1 - p)))))

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


# ----------------------------- SAIGRAČI -----------------------------
# Koliko minuta izostalog saigrača "pripada" igraču druge pozicije (ista pozicija = 1)
BLISKOST_POZICIJA = {frozenset(("Guard", "Forward")): 0.4, frozenset(("Forward", "Center")): 0.4,
                     frozenset(("Guard", "Center")): 0.1}
MIN_ZA_SAIGRACA = 10.0        # saigrač se računa ako igra bar ovoliko minuta
ISTORIJA_UBLAZI = 5.0         # težina istorije "bez njega" = n / (n + 5)
MAKS_MINUTA = 36.0
# Izmereno na 4.334 utakmice (2024-25 i 2025-26) u kojima je izostao igrač sa 15+ min:
# od "pravedno raspodeljenih" minuta igrač stvarno dobije oko trećine (0,31 / 0,36 po sezoni),
# a kod poena je najmanja greška kad se uračuna oko polovine efekta (deo dolazi kroz više šuteva).
SKALA_MINUTA = 0.35
SKALA_UCINKA = 0.15           # dodatni učinak po minutu = 1 + 0,15 × (dodatni minuti / igračevi minuti)
BEZ_UCINKA = {"skokovi", "ukradene", "blokade"}  # ne rastu sa preuzimanjem šuteva (provera: bez ovoga gore)


def bliskost(poz1, poz2):
    return 1.0 if poz1 == poz2 else BLISKOST_POZICIJA.get(frozenset((poz1, poz2)), 0.2)


class Saigraci:
    """Ko je s kim igrao u kojoj utakmici (sve sezone u bazi), za procenu uticaja odsustva."""

    def __init__(self, statistika, igraci, sezona):
        self.igraci, self.sezona = igraci, sezona
        self.igrali = defaultdict(set)    # (sezona, utakmica, tim) -> igrači koji su igrali
        self.po_igracu = defaultdict(list)  # (igrač, sezona, tim) -> utakmice (hronološki)
        self.stintovi = defaultdict(list)   # igrač -> [(sezona, tim, utakmice)]
        for r in statistika:
            if r["igrao"]:
                self.igrali[(r["sezona"], r["sifra_utakmice"], r["tim"])].add(r["igrac_id"])
                self.po_igracu[(r["igrac_id"], r["sezona"], r["tim"])].append(r)
        for (igrac, sezona, t), ut in self.po_igracu.items():
            self.stintovi[igrac].append((sezona, t, ut))
        self.tim_sezona = defaultdict(list)  # (sezona, tim) -> igrači
        for (igrac, sezona, t) in self.po_igracu:
            self.tim_sezona[(sezona, t)].append(igrac)

    def tim_sezona_skup(self, sezona, tim):
        return set(self.tim_sezona[(sezona, tim)])

    def poz(self, igrac_id):
        return (self.igraci.get(igrac_id) or {}).get("pozicija")

    def igrao(self, igrac_id, r):
        return igrac_id in self.igrali[(r["sezona"], r["sifra_utakmice"], r["tim"])]

    def istorija(self, x, y, tim, tip, do_datuma=None):
        """Igrač x kad je saigrač y igrao / nije igrao (sezone kad su bili u istom timu, samo u periodu
        kad je y bio u timu). Vraća (n bez njega, razlika minuta, odnos učinka po minutu) ili None."""
        sa, bez = [], []
        for sezona, t, ut_y in self.stintovi[y]:
            if sezona == self.sezona and t != tim:
                continue
            od, do = ut_y[0]["datum"], ut_y[-1]["datum"]
            for r in self.po_igracu.get((x, sezona, t), []):
                if do_datuma and r["datum"] >= do_datuma:
                    continue
                if od <= r["datum"] <= do or (sezona == self.sezona and r["datum"] > do):
                    (sa if self.igrao(y, r) else bez).append(r)
        if len(bez) < 2 or len(sa) < 4:
            return None
        m = lambda l: sum(r["minuti"] or 0 for r in l)
        s = lambda l: sum(vrednost(r, tip) for r in l)
        odnos = (s(bez) / m(bez)) / (s(sa) / m(sa)) if m(bez) and m(sa) and s(sa) else 1.0
        return len(bez), m(bez) / len(bez) - m(sa) / len(sa), odnos

    def korekcija(self, x, tim, ut_x, odsutni, tip, do_datuma=None):
        """Dodatni minuti i množilac učinka zbog odsutnih saigrača.
        odsutni: {igrač: verovatnoća da ne igra}. Uračunava se samo deo odsustva koji NIJE već
        u igračevim skorim utakmicama (ako y ne igra već 5 utakmica, forma to već sadrži)."""
        if not odsutni or not ut_x:
            return 0.0, 1.0, []
        # Isto kao procena igrača: gleda se samo poslednjih UZORAK utakmica, jednako
        w = [1.0 if i >= len(ut_x) - UZORAK else 0.0 for i in range(len(ut_x))]
        poz_x = self.poz(x)
        min_tima = {}
        for igrac in self.tim_sezona[(self.sezona, tim)]:
            ut = [r for r in self.po_igracu[(igrac, self.sezona, tim)] if not do_datuma or r["datum"] < do_datuma]
            if ut:
                min_tima[igrac] = sum(r["minuti"] or 0 for r in ut[-UZORAK:]) / len(ut[-UZORAK:])
        m_x = min_tima.get(x, 0)
        dodatno, mnozilac, opis = 0.0, 1.0, []
        for y, q in odsutni.items():
            m_y = min_tima.get(y, 0)
            if y == x or m_y < MIN_ZA_SAIGRACA:
                continue
            prisustvo = sum(a for a, r in zip(w, ut_x) if self.igrao(y, r)) / sum(w)
            ista_pozicija = bliskost(poz_x, self.poz(y)) == 1
            if prisustvo < 0.2:
                if ista_pozicija:
                    opis.append((y, q, None))  # već dugo ne igra: igračeva forma to već sadrži
                continue
            # Raspodela: zdravi saigrači, po minutaži i bliskosti pozicije
            # (samo oni koji su igrali u nekoj od igračevih poslednjih 5 utakmica - ne i oni koji su otišli)
            skoro = {z for r in ut_x[-5:] for z in self.igrali[(r["sezona"], r["sifra_utakmice"], r["tim"])]}
            zdravi = {z: m for z, m in min_tima.items()
                      if z != y and z in skoro and odsutni.get(z, 0) < 1 and m >= 5}
            imenilac = sum(bliskost(self.poz(z), self.poz(y)) * m for z, m in zdravi.items())
            udeo = bliskost(poz_x, self.poz(y)) * m_x / imenilac if imenilac else 0
            dm = m_y * udeo
            odnos = 1.0
            ist = self.istorija(x, y, tim, tip, do_datuma)
            if ist:
                n, dm_ist, odnos_ist = ist
                t_ist = n / (n + ISTORIJA_UBLAZI)
                dm = t_ist * dm_ist + (1 - t_ist) * dm
                odnos = 1 + t_ist * (max(0.8, min(1.25, odnos_ist)) - 1)
            k = q * prisustvo
            dodatno += k * dm * SKALA_MINUTA
            ucinak = k * dm * SKALA_UCINKA / m_x if m_x and tip not in BEZ_UCINKA else 0
            mnozilac *= 1 + k * (odnos - 1) + ucinak
            # U objašnjenju: saigrač iste pozicije uvek (i kad je efekat mali), ostali od 0,2 min
            if dm > 0 and (ista_pozicija or k * dm * SKALA_MINUTA >= 0.2):
                opis.append((y, q, k * dm * SKALA_MINUTA))
        return dodatno, mnozilac, opis


# ----------------------------- OČEKIVANA RAZLIKA (BLOWOUT) -----------------------------
# Izmereno na 11.164 utakmice (2024-25, 2025-26): kad je unapred očekivana razlika 8+ poena, starteri
# igraju ~1,7-1,9 min manje od procene, klupa ~0,2-0,5 min više. Odmor (dani između utakmica) nije
# pokazao efekat (±1,5%, u bazi nema domaćeg prvenstva), pa nije uključen.
PREDNOST_DOMACINA = 3.0
RAZLIKA_PRAG = 4.0            # do ove očekivane razlike nema efekta


def rejtinzi_timova(statistika, sezona):
    """Prosečna razlika u poenima po utakmici (ova sezona), na početku sezone ublažena ka pola prošlosezonske."""
    mecevi = {}
    for r in statistika:
        if r["sezona"] in (sezona, sezona - 1) and r["poeni_domacin"] is not None:
            gost = r["protivnik"] if r["domacin"] else r["tim"]
            mecevi[(r["sezona"], r["sifra_utakmice"])] = (r["u_domacin"], gost, r["poeni_domacin"], r["poeni_gost"])
    zbir = defaultdict(lambda: [0.0, 0])
    for (s, _), (dom, gost, pd, pg) in mecevi.items():
        for tim, raz in ((dom, pd - pg), (gost, pg - pd)):
            zbir[(s, tim)][0] += raz
            zbir[(s, tim)][1] += 1
    timovi = {t for (s, t) in zbir if s == sezona}
    rejting = {}
    for t in timovi:
        z, n = zbir[(sezona, t)]
        zp, np_ = zbir.get((sezona - 1, t), (0.0, 0))
        prosla = zp / np_ if np_ else 0.0
        rejting[t] = (z + 5 * 0.5 * prosla) / (n + 5)
    return rejting


def minuti_zbog_razlike(minuti, ocekivana_razlika):
    """Starteri (28+ min) gube do 0,25 min po poenu razlike iznad praga, klupa (15- min) dobija 0,08."""
    visak = max(0.0, abs(ocekivana_razlika) - RAZLIKA_PRAG)
    koef = 0.08 - 0.33 * max(0.0, min(1.0, (minuti - 15) / 13))
    return max(-3.0, min(1.5, koef * visak))


# ----------------------------- PROCENA -----------------------------
def proceni_igraca(ut_sezona, ut_prosla, tip, kod_kuce, protivnik_faktor, saigraci=(0.0, 1.0, []),
                   ocekivana_razlika=None):
    """Očekivana vrednost, rasipanje i objašnjenja za jednog igrača i jedan tip.
    saigraci: (dodatni minuti, množilac učinka, opis) iz Saigraci.korekcija.
    ocekivana_razlika: očekivana razlika u poenima za igračev tim (+ = favorit)."""
    n = len(ut_sezona)
    vr = [vrednost(r, tip) for r in ut_sezona]
    mi = [r["minuti"] or 0 for r in ut_sezona]

    # Učinak po minutu i minuti: samo poslednjih UZORAK utakmica, jednako (Dejanova odluka 30.10.2026;
    # prošla sezona se ne koristi). ut_prosla se više ne koristi, ostaje zbog poziva.
    vr5, mi5 = vr[-UZORAK:], mi[-UZORAK:]
    po_minutu = sum(vr5) / sum(mi5) if sum(mi5) else 0
    prosla_prosek = None
    min_sezona = sum(mi) / n
    minuti = sum(mi5) / len(mi5)
    # Koraci od sezonskog proseka do očekivanog (za objašnjenje: koliko koji faktor dodaje/oduzima)
    sezona_prosek = sum(vr) / n
    koraci = []
    pre = po_minutu * min_sezona
    koraci.append(("ucinak", pre - sezona_prosek))        # učinak po minutu u poslednjih 5
    sad = po_minutu * minuti
    koraci.append(("minuti", sad - pre))                  # trend minutaže

    dodatno, mnozilac, opis_saigraca = saigraci
    minuti_bez_saigraca = minuti
    minuti = max(0.0, min(max(MAKS_MINUTA, minuti), minuti + dodatno))
    po_minutu *= mnozilac
    pre, sad = sad, po_minutu * minuti
    koraci.append(("saigraci", sad - pre))
    razlika_min = minuti_zbog_razlike(minuti, ocekivana_razlika) if ocekivana_razlika is not None else 0.0
    minuti = max(0.0, minuti + razlika_min)
    pre, sad = sad, po_minutu * minuti
    koraci.append(("razlika", sad - pre))

    # Kod kuće / u gostima (po minutu), jako ublaženo
    dom = [(v, m) for v, m, r in zip(vr, mi, ut_sezona) if r["domacin"] == (1 if kod_kuce else 0)]
    f_dom = 1.0
    if len(dom) >= 3 and po_minutu and sum(m for _, m in dom) and sum(vr):
        odnos = (sum(v for v, _ in dom) / sum(m for _, m in dom)) / (sum(vr) / sum(mi) if sum(mi) else 1)
        f_dom = max(1 - DOMACIN_MAX, min(1 + DOMACIN_MAX, 1 + 0.25 * (odnos - 1)))

    odnos_p, n_p = protivnik_faktor or (1.0, 0)
    f_prot = 1 + (odnos_p - 1) * n_p / (n_p + PROTIVNIK_UBLAZI)

    ocekivano = po_minutu * minuti * f_dom * f_prot
    koraci.append(("dom", sad * f_dom - sad))
    koraci.append(("protivnik", ocekivano - sad * f_dom))

    # Rasipanje: varijansa/srednja vrednost iz utakmica ove i prošle sezone, ublaženo ka
    # tipičnoj vrednosti u ligi (iz malo utakmica procena je nepouzdana, obično preuska)
    sve = vr
    sr = sum(sve) / len(sve)
    var = sum((x - sr) ** 2 for x in sve) / max(len(sve) - 1, 1)
    igracevo = var / sr if sr else RASIPANJE_LIGA[tip]
    rasipanje = (len(sve) * igracevo + RASIPANJE_UTAKMICA * RASIPANJE_LIGA[tip]) / (len(sve) + RASIPANJE_UTAKMICA)
    rasipanje = max(1.0, min(3.5, rasipanje))

    return {"ocekivano": ocekivano, "rasipanje": rasipanje, "minuti": minuti, "min_sezona": min_sezona,
            "sezona_prosek": sum(vr) / n, "poslednjih5": sum(vr[-5:]) / len(vr[-5:]),
            "prosla_prosek": prosla_prosek,
            "f_dom": f_dom, "f_prot": f_prot, "n_prot": n_p, "vrednosti": vr,
            "saigraci": opis_saigraca, "minuti_bez_saigraca": minuti_bez_saigraca, "mnozilac": mnozilac,
            "ocekivana_razlika": ocekivana_razlika, "razlika_min": razlika_min, "koraci": dict(koraci)}


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
    saigraci = Saigraci(statistika, igraci, sezona)
    rejting = rejtinzi_timova(statistika, sezona)
    # Iz tabele povreda: "ne igra" = sigurno odsustvo, "upitan" = pola
    verovatnoca_odsustva = {i: {"st-ne": 1.0, "st-up": 0.5}.get(p.get("klasa"), 0.0) for i, p in povrede.items()}

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

        odsutni = {y: q for y, q in verovatnoca_odsustva.items()
                   if q and y != p["igrac_id"] and y in saigraci.tim_sezona_skup(sezona, p["tim"])}
        x = proceni_igraca(ut, po_igracu_prosla.get(p["igrac_id"], []), p["tip"], kod_kuce,
                           protivnik.get((prot, poz, p["tip"])),
                           saigraci.korekcija(p["igrac_id"], p["tim"], ut, odsutni, p["tip"]),
                           rejting.get(p["tim"], 0) - rejting.get(prot, 0)
                           + (PREDNOST_DOMACINA if kod_kuce else -PREDNOST_DOMACINA))
        kladionica = (1 / p["preko"]) / (1 / p["preko"] + 1 / p["ispod"])
        model = kalibrisi(p_preko(x["ocekivano"], x["rasipanje"], p["linija"]), p["tip"])
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
            # Linija daleko od naše procene: kladionica verovatno zna nešto (uloga, povrede saigrača)
            "sumnjivo": abs(x["ocekivano"] - p["linija"]) > VELIKA_RAZLIKA * max(p["linija"], 6),
            "upitan": bool(status) and status.get("klasa") == "st-up",
            **x,
        })
        rezultati[-1]["ocena"] = ocena(rezultati[-1]["ev"], rezultati[-1]["sumnjivo"])
    rezultati.sort(key=lambda r: -r["ev"])
    return rezultati
