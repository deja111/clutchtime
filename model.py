"""
model.py
---------
Procena verovatnoće da igrač pređe granicu (preko/ispod) na sledećoj utakmici.
Koristi ga sajt.py (stranica granice.html: posetilac bira igrača, kategoriju i granicu).

Kako se računa očekivana vrednost (npr. poeni):
    1. Učinak po minutu u poslednjih 5 utakmica (prošla sezona se ne koristi).
    2. Očekivani minuti: prosek poslednjih 5 utakmica.
    3. Protivnik: koliko dozvoljava igračima te pozicije u toj kategoriji, u odnosu na
       prosek lige - samo za asistencije i trojke (za ostalo je provera pokazala da je šum).
    4. Kod kuće / u gostima: igračev odnos, jako ublažen (najviše ±6%).
Raspodela: negativna binomna (brojevi poena/skokova su "rasutiji" od Poasonove),
rasipanje se procenjuje iz igračevih utakmica. P(preko 14.5) = P(X >= 15).

Verovatnoća se kalibriše (KALIBRACIJA) na prethodnim sezonama. Kvote kladionica se više ne koriste
(31.10.2026: propovi iz kladionice ugašeni, sajt prikazuje granice koje bira posetilac).

Ovo je statistička procena, ne savet za klađenje.
"""

import math
from collections import defaultdict

# Učinak i minuti iz poslednjih UZORAK utakmica tekuće sezone, bez prošle sezone (Dejanova odluka 30.10.2026).
# Provera na 9.562 utakmice: ponderisana cela sezona (+ prošla) imala je manju grešku (poeni 5,49 prema 5,78),
# ali je izabrano jednostavnije i "svežije" pravilo; kalibracija je ponovo naučena za ovaj način.
UZORAK = 5
# Matchup (koliko protivnik dozvoljava poziciji): težina = n / (n + ublaži), samo gde je provera pokazala korist.
# Provera 30.10.2026. na 9.379 utakmica (protivnik računat samo iz ranijih utakmica): kod poena, skokova i PSA
# svaki matchup povećava grešku (šum), kod asistencija i trojki blag matchup (ublaži 16) malo pomaže.
PROTIVNIK_UBLAZI = {"asistencije": 16.0, "trojke": 16.0}
DOMACIN_MAX = 0.06
MALO_UTAKMICA = 5             # ispod ovoga: oznaka "malo podataka"
# Tipično rasipanje (varijansa/srednja vrednost) u ligi: medijana igrača sa 15+ utakmica (10+ min), 2023-2026
RASIPANJE_LIGA = {"poeni": 2.73, "skokovi": 1.14, "asistencije": 1.11, "trojke": 1.04, "ukradene": 1.02,
                  "blokade": 1.03, "PSA": 2.64, "PS": 2.74, "PA": 2.60, "SA": 1.31}
RASIPANJE_UTAKMICA = 10       # koliko "utakmica" vredi tipična vrednost lige

# Kalibracija (Platt): p_kal = sigmoid(a + b * logit(p_model)), po kategoriji.
# Naučeno na sezonama 2024-25 i 2025-26 (linije na proseku ±2), provereno: učeno na 2024-25,
# testirano na 2025-26 -> Brier bolji u svim kategorijama. b < 1 = model je bio previše samouveren.
KALIBRACIJA = {
    # Naučeno ponovo 30.10.2026. za model "poslednjih 5 utakmica" (b manje = taj model je samouvereniji)
    # (ponovo posle izmene matchupa, 30.10.2026)
    "poeni": (0.031, 0.740), "skokovi": (-0.045, 0.831), "asistencije": (-0.092, 0.823),
    "trojke": (-0.181, 0.807), "ukradene": (-0.377, 0.797), "blokade": (-0.567, 0.868),
    "PSA": (0.019, 0.734), "PS": (0.020, 0.744), "PA": (0.038, 0.768), "SA": (-0.019, 0.843),
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
# Provera 31.10.2026. na 9.379 utakmica (2024-25, 2025-26), model "poslednjih 5":
#   POVRATAK (saigrač koji je propustio deo poslednjih 5 a sada igra uzima minute) - greška manja u SVIM
#   kategorijama (poeni 5,822 -> 5,765, PSA 7,243 -> 7,171). Uključeno.
#   USAGE (raspodela po učešću u napadu) - malo gore. Tempo utakmice - bez efekta. Isključeno.
POVRATAK = True
USAGE = False


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

    def korekcija(self, x, tim, ut_x, odsutni, tip, do_datuma=None, povratak=POVRATAK, usage=USAGE):
        """Dodatni minuti i množilac učinka zbog odsutnih saigrača.
        odsutni: {igrač: verovatnoća da ne igra}. Uračunava se samo razlika između odsustva u sledećoj
        utakmici i odsustva u igračevih poslednjih 5 (ako y ne igra već 5 utakmica, forma to već sadrži).
        povratak: i obrnuto - saigrač koji je propustio deo tih 5 a sada igra uzima igraču minute.
        usage: oslobođeni minuti/šutevi se dele po minutaži × učešću u napadu, a ne samo po minutaži."""
        if not ut_x or not (odsutni or povratak):
            return 0.0, 1.0, []
        # Isto kao procena igrača: gleda se samo poslednjih UZORAK utakmica, jednako
        w = [1.0 if i >= len(ut_x) - UZORAK else 0.0 for i in range(len(ut_x))]
        poz_x = self.poz(x)
        min_tima, usg_tima = {}, {}
        for igrac in self.tim_sezona[(self.sezona, tim)]:
            ut = [r for r in self.po_igracu[(igrac, self.sezona, tim)] if not do_datuma or r["datum"] < do_datuma]
            if ut:
                min_tima[igrac] = sum(r["minuti"] or 0 for r in ut[-UZORAK:]) / len(ut[-UZORAK:])
                mins = sum(r["minuti"] or 0 for r in ut)
                napadi = sum((r["sut2_pokusano"] or 0) + (r["sut3_pokusano"] or 0)
                             + 0.44 * (r["slobodna_pokusano"] or 0) + (r["izgubljene"] or 0) for r in ut)
                usg_tima[igrac] = napadi / mins if mins >= 30 else None
        usg_lige = [u for u in usg_tima.values() if u]
        usg_lige = sum(usg_lige) / len(usg_lige) if usg_lige else 0.4
        tezina = (lambda z: min_tima[z] * (usg_tima.get(z) or usg_lige) / usg_lige) if usage else (lambda z: min_tima[z])
        m_x = min_tima.get(x, 0)
        kandidati = dict(odsutni)
        if povratak:
            skoro5 = {z for r in ut_x[-UZORAK:] for z in self.igrali[(r["sezona"], r["sifra_utakmice"], r["tim"])]}
            for y in skoro5:
                kandidati.setdefault(y, 0.0)  # igrao je u nekoj od poslednjih 5, a sada nije na listi odsutnih
        dodatno, mnozilac, opis = 0.0, 1.0, []
        for y, q in kandidati.items():
            m_y = min_tima.get(y, 0)
            if y == x or m_y < MIN_ZA_SAIGRACA:
                continue
            prisustvo = sum(a for a, r in zip(w, ut_x) if self.igrao(y, r)) / sum(w)
            ista_pozicija = bliskost(poz_x, self.poz(y)) == 1
            if q and prisustvo < 0.2:
                if ista_pozicija:
                    opis.append((y, q, None))  # već dugo ne igra: igračeva forma to već sadrži
                continue
            k = (q - (1 - prisustvo)) if povratak else q * prisustvo
            if abs(k) < 0.05:
                continue
            # Raspodela: zdravi saigrači, po minutaži i bliskosti pozicije
            # (samo oni koji su igrali u nekoj od igračevih poslednjih 5 utakmica - ne i oni koji su otišli)
            skoro = {z for r in ut_x[-5:] for z in self.igrali[(r["sezona"], r["sifra_utakmice"], r["tim"])]}
            zdravi = {z: m for z, m in min_tima.items()
                      if z != y and z in skoro and odsutni.get(z, 0) < 1 and m >= 5}
            imenilac = sum(bliskost(self.poz(z), self.poz(y)) * tezina(z) for z in zdravi)
            udeo = bliskost(poz_x, self.poz(y)) * tezina(x) / imenilac if imenilac and x in min_tima else 0
            dm = m_y * udeo
            odnos = 1.0
            ist = self.istorija(x, y, tim, tip, do_datuma)
            if ist:
                n, dm_ist, odnos_ist = ist
                t_ist = n / (n + ISTORIJA_UBLAZI)
                dm = t_ist * dm_ist + (1 - t_ist) * dm
                odnos = 1 + t_ist * (max(0.8, min(1.25, odnos_ist)) - 1)
            dodatno += k * dm * SKALA_MINUTA
            ucinak = k * dm * SKALA_UCINKA / m_x if m_x and tip not in BEZ_UCINKA else 0
            mnozilac *= 1 + k * (odnos - 1) + ucinak
            # U objašnjenju: saigrač iste pozicije uvek (i kad je efekat mali), ostali od 0,2 min
            if dm > 0 and (ista_pozicija or abs(k * dm * SKALA_MINUTA) >= 0.2):
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


TEMPO_JACINA = 0.0            # tempo utakmice: provera 31.10.2026. bez efekta, isključeno (0)


def tempo_timova(statistika, sezona, do_datuma=None):
    """Napadi po utakmici (FGA + 0,44·FTA − OREB + TO, prosek oba tima) za utakmice u kojima je tim igrao,
    u odnosu na prosek lige. Vraća {tim: (odnos, broj utakmica)}."""
    tim_mec = defaultdict(float)
    for r in statistika:
        if r["sezona"] != sezona or not r["igrao"] or (do_datuma and r["datum"] >= do_datuma):
            continue
        tim_mec[(r["sifra_utakmice"], r["tim"])] += ((r["sut2_pokusano"] or 0) + (r["sut3_pokusano"] or 0)
                                                     + 0.44 * (r["slobodna_pokusano"] or 0)
                                                     - (r["skokovi_napad"] or 0) + (r["izgubljene"] or 0))
    po_mecu = defaultdict(list)
    for (s, t), napadi in tim_mec.items():
        po_mecu[s].append((t, napadi))
    tempo = defaultdict(list)
    for s, timovi in po_mecu.items():
        if len(timovi) == 2:
            prosek = (timovi[0][1] + timovi[1][1]) / 2
            for t, _ in timovi:
                tempo[t].append(prosek)
    if not tempo:
        return {}
    liga = sum(sum(v) for v in tempo.values()) / sum(len(v) for v in tempo.values())
    return {t: (sum(v) / len(v) / liga, len(v)) for t, v in tempo.items()}


def faktor_tempa(tempo, tim, protivnik):
    """Očekivani tempo utakmice (prosek oba tima, ublaženo kad ima malo utakmica) prema proseku lige."""
    def ublazi(t):
        odnos, n = tempo.get(t, (1.0, 0))
        return 1 + (odnos - 1) * n / (n + 5)
    return 1 + TEMPO_JACINA * ((ublazi(tim) + ublazi(protivnik)) / 2 - 1)


def minuti_zbog_razlike(minuti, ocekivana_razlika):
    """Starteri (28+ min) gube do 0,25 min po poenu razlike iznad praga, klupa (15- min) dobija 0,08."""
    visak = max(0.0, abs(ocekivana_razlika) - RAZLIKA_PRAG)
    koef = 0.08 - 0.33 * max(0.0, min(1.0, (minuti - 15) / 13))
    return max(-3.0, min(1.5, koef * visak))


# ----------------------------- PROCENA -----------------------------
def proceni_igraca(ut_sezona, ut_prosla, tip, kod_kuce, protivnik_faktor, saigraci=(0.0, 1.0, []),
                   ocekivana_razlika=None, f_tempo=1.0):
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
    po_minutu *= f_tempo
    pre, sad = sad, po_minutu * minuti
    koraci.append(("tempo", sad - pre))

    # Kod kuće / u gostima (po minutu), jako ublaženo
    dom = [(v, m) for v, m, r in zip(vr, mi, ut_sezona) if r["domacin"] == (1 if kod_kuce else 0)]
    f_dom = 1.0
    if len(dom) >= 3 and po_minutu and sum(m for _, m in dom) and sum(vr):
        odnos = (sum(v for v, _ in dom) / sum(m for _, m in dom)) / (sum(vr) / sum(mi) if sum(mi) else 1)
        f_dom = max(1 - DOMACIN_MAX, min(1 + DOMACIN_MAX, 1 + 0.25 * (odnos - 1)))

    odnos_p, n_p = (protivnik_faktor or (1.0, 0)) if tip in PROTIVNIK_UBLAZI else (1.0, 0)
    f_prot = 1 + (odnos_p - 1) * n_p / (n_p + PROTIVNIK_UBLAZI.get(tip, 1.0))

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

def procene_kola(statistika, igraci, sezona, mecevi, povrede=None):
    """Za svakog igrača timova iz narednih utakmica: očekivana vrednost i rasipanje po kategoriji
    (sa saigračima, povratkom, očekivanom razlikom, protivnikom i domaćim terenom).
    Vraća {igrac_id: {"tim", "protivnik", "kod_kuce", "datum", "tipovi": {tip: rezultat proceni_igraca}}}.
    Igrači sa statusom "ne igra" se preskaču."""
    povrede = povrede or {}
    po_igracu = defaultdict(list)
    poslednji_tim = {}
    for r in statistika:
        if r["sezona"] == sezona and r["igrao"]:
            po_igracu[r["igrac_id"]].append(r)
            poslednji_tim[r["igrac_id"]] = r["tim"]
    protivnik = faktori_protivnika(statistika, igraci, sezona)
    saigraci = Saigraci(statistika, igraci, sezona)
    rejting = rejtinzi_timova(statistika, sezona)
    verovatnoca_odsustva = {i: {"st-ne": 1.0, "st-up": 0.5}.get(p.get("klasa"), 0.0) for i, p in povrede.items()}

    rezultat = {}
    for m in mecevi:
        for tim, prot in ((m["domacin"], m["gost"]), (m["gost"], m["domacin"])):
            kod_kuce = tim == m["domacin"]
            razlika = (rejting.get(tim, 0) - rejting.get(prot, 0)
                       + (PREDNOST_DOMACINA if kod_kuce else -PREDNOST_DOMACINA))
            clanovi = saigraci.tim_sezona_skup(sezona, tim)
            for x, ut in po_igracu.items():
                if poslednji_tim.get(x) != tim or len(ut) < 2 or verovatnoca_odsustva.get(x, 0) >= 1:
                    continue
                odsutni = {y: q for y, q in verovatnoca_odsustva.items() if q and y != x and y in clanovi}
                poz = (igraci.get(x) or {}).get("pozicija")
                tipovi = {}
                for tip in KOLONE:
                    tipovi[tip] = proceni_igraca(ut, [], tip, kod_kuce, protivnik.get((prot, poz, tip)),
                                                 saigraci.korekcija(x, tim, ut, odsutni, tip), razlika)
                rezultat[x] = {"tim": tim, "protivnik": prot, "kod_kuce": kod_kuce, "datum": m["datum"],
                               "tipovi": tipovi}
    return rezultat
