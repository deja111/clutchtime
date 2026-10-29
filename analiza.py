"""
analiza.py
-----------
Pravi najavu narednog kola Evrolige iz baze podaci/evroliga.db.
Rezultat je HTML stranica u folderu "izvestaji" (otvara se dvoklikom,
u pregledaču).

Pokretanje (Command Prompt, iz foldera Projekat):
    python analiza.py

Za svakog igrača oba tima u svakom meču narednog kola prikazuje:
    - sezonske proseke (minuti, poeni, skokovi, asistencije, PIR, TS%, eFG%)
    - formu (poslednjih 5 utakmica u odnosu na sezonu)
    - trend minutaže
    - proseke kod kuće i u gostima
    - učinak protiv narednog protivnika (sve sezone u bazi)
    - koliko protivnik dozvoljava igračima na toj poziciji (rang u ligi)
    - kratak automatski rezime
"""

import html
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# ----------------------------- PODEŠAVANJA -----------------------------
FOLDER = Path(__file__).parent
BAZA = FOLDER / "podaci" / "evroliga.db"
IZLAZ = FOLDER / "izvestaji"

FORMA_UTAKMICA = 5           # koliko poslednjih utakmica čini "formu"
MIN_MINUTA_ZA_KARTICU = 10   # igrači sa manje prosečnih minuta idu u kratku listu
PRAG_FORME = 0.15            # 15% iznad/ispod proseka = dobra forma / pad forme
PRAG_MINUTAZE = 3.0          # promena od 3+ minuta = minutaža raste/pada
MIN_PIR_ZA_FORMU = 5.0       # forma se ne ocenjuje igračima sa malim PIR-om (mnogo šuma)
MIN_RAZLIKA_FORME = 2.0      # i razlika mora biti bar 2 PIR-a

POZICIJA = {"Guard": "Bek", "Forward": "Krilo", "Center": "Centar"}
POZICIJA_MNOZINA = {"Guard": "bekovima", "Forward": "krilima", "Center": "centrima"}
# Ako je postavljeno (radi sajt.py), imena igrača postaju linkovi ka profilu
LINK_IGRACA = None   # funkcija: igrac_id -> adresa stranice
POVREDE = {}         # igrac_id -> podaci iz tabele povreda (postavlja sajt.py)

DANI = ["ponedeljak", "utorak", "sreda", "četvrtak", "petak", "subota", "nedelja"]


# ----------------------------- POMOĆNE -----------------------------
def broj(x, decimala=1):
    """18.43 -> '18,4' (srpski zapis)."""
    if x is None:
        return "–"
    return f"{x:.{decimala}f}".replace(".", ",")


def procenat(x):
    return "–" if x is None else f"{x * 100:.0f}%"


def lepo_ime(ime):
    """'MOTLEY, JOHNATHAN' -> 'Johnathan Motley'."""
    if not ime:
        return "?"
    if "," in ime:
        prezime, ime_ = [d.strip() for d in ime.split(",", 1)]
        return f"{ime_.title()} {prezime.title()}"
    return ime.title()


def mecevi_rec(n):
    """'u 1 meču', 'u 3 meča', 'u 7 mečeva'."""
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} meču"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return f"{n} meča"
    return f"{n} mečeva"


def utakmica_rec(n):
    """'1 utakmica', '3 utakmice', '7 utakmica'."""
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return f"{n} utakmice"
    return f"{n} utakmica"


def datum_srb(tekst):
    """'2026-02-06 20:45' -> '06.02.2026.'"""
    return datetime.strptime(tekst[:10], "%Y-%m-%d").strftime("%d.%m.%Y.")


def e(tekst):
    return html.escape(str(tekst))


def bedz(igrac_id):
    """Oznaka statusa (NE IGRA / UPITAN / VRAĆA SE) ako je igrač u tabeli povreda."""
    p = POVREDE.get(igrac_id)
    if not p:
        return ""
    opis = " · ".join(x for x in (p.get("razlog"), p.get("povratak") and f"povratak: {p['povratak']}") if x)
    return f'<span class="bedz {p["klasa"]}" title="{e(opis)}">{e(p["bedz"])}</span>'


def ime_html(a, podebljano=False):
    """Ime igrača; ako sajt postoji, kao link ka njegovom profilu (+ oznaka povrede)."""
    ime = e(a["ime"])
    if podebljano:
        ime = f"<b>{ime}</b>"
    if LINK_IGRACA:
        ime = f'<a href="{LINK_IGRACA(a["id"])}">{ime}</a>'
    return ime + bedz(a["id"])


# ----------------------------- RAČUNANJE -----------------------------
def zbirno(redovi):
    """Proseci i procenti za listu utakmica jednog igrača (samo gde je igrao)."""
    n = len(redovi)
    if n == 0:
        return None
    s = lambda k: sum(r[k] or 0 for r in redovi)
    fga = s("sut2_pokusano") + s("sut3_pokusano")
    fgm = s("sut2_pogodjeno") + s("sut3_pogodjeno")
    fta = s("slobodna_pokusano")
    ts_imenilac = 2 * (fga + 0.44 * fta)
    return {
        "gp": n,
        "min": s("minuti") / n,
        "pts": s("poeni") / n,
        "reb": s("skokovi_ukupno") / n,
        "ast": s("asistencije") / n,
        "pir": s("pir") / n,
        "ts": s("poeni") / ts_imenilac if ts_imenilac else None,
        "efg": (fgm + 0.5 * s("sut3_pogodjeno")) / fga if fga else None,
    }


def ucitaj(baza):
    baza.row_factory = sqlite3.Row
    sezona = baza.execute("SELECT MAX(sezona) FROM utakmice").fetchone()[0]

    kolo = baza.execute(
        "SELECT kolo FROM utakmice WHERE sezona=? AND odigrana=0 ORDER BY datum LIMIT 1",
        (sezona,)).fetchone()
    if not kolo:
        return None
    kolo = kolo[0]
    mecevi = [dict(r) for r in baza.execute(
        "SELECT * FROM utakmice WHERE sezona=? AND kolo=? AND odigrana=0 ORDER BY datum",
        (sezona, kolo))]

    timovi = {r["sifra"]: r["naziv"] for r in baza.execute("SELECT sifra, naziv FROM timovi")} \
        if baza.execute("SELECT name FROM sqlite_master WHERE name='timovi'").fetchone() else {}
    igraci = {r["igrac_id"]: dict(r) for r in baza.execute("SELECT * FROM igraci")}

    statistika = [dict(r) for r in baza.execute(
        """SELECT s.*, u.datum, u.kolo, u.faza, u.domacin AS u_domacin,
                  u.poeni_domacin, u.poeni_gost FROM statistika s
           JOIN utakmice u ON u.sezona=s.sezona AND u.sifra_utakmice=s.sifra_utakmice
           ORDER BY u.datum""")]

    # Skor timova u tekućoj sezoni (pobede-porazi)
    skor = defaultdict(lambda: [0, 0])
    for u in baza.execute("SELECT * FROM utakmice WHERE sezona=? AND odigrana=1", (sezona,)):
        dom_pobedio = u["poeni_domacin"] > u["poeni_gost"]
        skor[u["domacin"]][0 if dom_pobedio else 1] += 1
        skor[u["gost"]][1 if dom_pobedio else 0] += 1

    return sezona, kolo, mecevi, timovi, igraci, statistika, skor


def pripremi(sezona, igraci, statistika):
    """Grupiše utakmice po igraču i računa šta protivnici dozvoljavaju po poziciji."""
    po_igracu_sezona = defaultdict(list)    # samo tekuća sezona, gde je igrao
    po_igracu_sve = defaultdict(list)       # sve sezone, gde je igrao
    poslednji_tim = {}                      # tim u poslednjoj utakmici tekuće sezone

    # (protivnik, pozicija) -> {utakmica: [poeni, pir]}
    dozvoljeno = defaultdict(lambda: defaultdict(lambda: [0, 0]))

    for r in statistika:
        if r["sezona"] == sezona:
            poslednji_tim[r["igrac_id"]] = r["tim"]
        if not r["igrao"]:
            continue
        po_igracu_sve[r["igrac_id"]].append(r)
        if r["sezona"] == sezona:
            po_igracu_sezona[r["igrac_id"]].append(r)
            poz = (igraci.get(r["igrac_id"]) or {}).get("pozicija")
            if poz:
                d = dozvoljeno[(r["protivnik"], poz)][r["sifra_utakmice"]]
                d[0] += r["poeni"] or 0
                d[1] += r["pir"] or 0

    # Prosek po utakmici i rang (1 = dozvoljava najviše PIR-a toj poziciji)
    dozvoljeno_prosek = {}
    for (tim, poz), mecevi in dozvoljeno.items():
        n = len(mecevi)
        dozvoljeno_prosek[(tim, poz)] = {
            "pts": sum(m[0] for m in mecevi.values()) / n,
            "pir": sum(m[1] for m in mecevi.values()) / n,
        }
    rang = {}
    for poz in POZICIJA:
        lista = sorted([t for (t, p) in dozvoljeno_prosek if p == poz],
                       key=lambda t: -dozvoljeno_prosek[(t, poz)]["pir"])
        for i, t in enumerate(lista, start=1):
            rang[(t, poz)] = (i, len(lista))

    return po_igracu_sezona, po_igracu_sve, poslednji_tim, dozvoljeno_prosek, rang


def analiziraj_igraca(igrac_id, tim, protivnik, kod_kuce, igraci, po_sezona, po_sve,
                      dozvoljeno, rang):
    redovi = po_sezona[igrac_id]
    info = igraci.get(igrac_id) or {}
    sezona_z = zbirno(redovi)
    forma_redovi = redovi[-FORMA_UTAKMICA:]
    forma_z = zbirno(forma_redovi)
    poslednje3 = zbirno(redovi[-3:])

    dom = zbirno([r for r in redovi if r["domacin"] == 1])
    gost = zbirno([r for r in redovi if r["domacin"] == 0])
    protiv_redovi = [r for r in po_sve[igrac_id] if r["protivnik"] == protivnik]
    protiv = zbirno(protiv_redovi)
    karijera = zbirno(po_sve[igrac_id])

    poz = info.get("pozicija")
    doz = dozvoljeno.get((protivnik, poz))
    rng = rang.get((protivnik, poz))

    a = {
        "id": igrac_id,
        "ime": lepo_ime(info.get("ime")),
        "poz": POZICIJA.get(poz, "?"),
        "poz_kod": poz,
        "sezona": sezona_z,
        "forma": forma_z,
        "forma_pir": [r["pir"] or 0 for r in forma_redovi],
        "forma_protivnici": [r["protivnik"] for r in forma_redovi],
        "min_trend": (poslednje3["min"] - sezona_z["min"]) if len(redovi) >= 4 else None,
        "dom": dom,
        "gost": gost,
        "kod_kuce": kod_kuce,
        "protiv": protiv,
        "protiv_poslednja": protiv_redovi[-1] if protiv_redovi else None,
        "karijera": karijera,
        "doz": doz,
        "rang": rng,
    }
    return a


def ocena_forme(forma_pir, sezona_pir):
    """1 = dobra forma, -1 = pad forme, 0 = stabilno (ili premalo podataka)."""
    if forma_pir is None or sezona_pir is None or sezona_pir < MIN_PIR_ZA_FORMU:
        return 0
    razlika = forma_pir - sezona_pir
    if abs(razlika) < MIN_RAZLIKA_FORME:
        return 0
    if razlika >= sezona_pir * PRAG_FORME:
        return 1
    if razlika <= -sezona_pir * PRAG_FORME:
        return -1
    return 0


def rezime(a, protivnik_naziv):
    """2-3 rečenice na osnovu jednostavnih pravila."""
    s, f = a["sezona"], a["forma"]
    recenice = []

    if s["gp"] < 3:
        recenice.append(f"Tek {utakmica_rec(s['gp'])} ove sezone, procene su nepouzdane.")
    elif ocena_forme(f["pir"], s["pir"]) != 0:
        if ocena_forme(f["pir"], s["pir"]) > 0:
            recenice.append(f"U dobroj formi: {broj(f['pir'])} PIR u poslednjih {f['gp']}, "
                            f"iznad sezonskog proseka ({broj(s['pir'])}).")
        else:
            recenice.append(f"Pad forme: {broj(f['pir'])} PIR u poslednjih {f['gp']}, "
                            f"ispod sezonskog proseka ({broj(s['pir'])}).")

    if a["min_trend"] is not None:
        if a["min_trend"] >= PRAG_MINUTAZE:
            recenice.append(f"Minutaža raste (+{broj(a['min_trend'])} min u poslednje 3).")
        elif a["min_trend"] <= -PRAG_MINUTAZE:
            recenice.append(f"Minutaža pada ({broj(a['min_trend'])} min u poslednje 3).")

    if a["rang"] and a["poz_kod"]:
        r, ukupno = a["rang"]
        mn = POZICIJA_MNOZINA[a["poz_kod"]]
        if r <= 5:
            recenice.append(f"{protivnik_naziv} je među najpopustljivijim odbranama prema "
                            f"{mn} ({r}. od {ukupno}).")
        elif r > ukupno - 5:
            recenice.append(f"{protivnik_naziv} je među najtvrđim odbranama prema "
                            f"{mn} ({r}. od {ukupno}).")

    p, k = a["protiv"], a["karijera"]
    if p and p["gp"] >= 2 and k and k["pir"] > 0:
        odnos = p["pir"] / k["pir"] - 1
        if odnos >= 0.2:
            recenice.append(f"Prija mu ovaj protivnik: {broj(p['pir'])} PIR u "
                            f"{mecevi_rec(p['gp'])} (inače {broj(k['pir'])}).")
        elif odnos <= -0.2:
            recenice.append(f"Ne snalazi se protiv ovog tima: {broj(p['pir'])} PIR u "
                            f"{mecevi_rec(p['gp'])} (inače {broj(k['pir'])}).")

    ds, gs = a["dom"], a["gost"]
    if ds and gs and ds["gp"] >= 2 and gs["gp"] >= 2 and max(ds["pir"], gs["pir"]) > 5:
        if a["kod_kuce"] and ds["pir"] >= gs["pir"] * 1.25:
            recenice.append(f"Igra kod kuće, gde je znatno bolji ({broj(ds['pir'])} PIR "
                            f"prema {broj(gs['pir'])} u gostima).")
        elif not a["kod_kuce"] and gs["pir"] >= ds["pir"] * 1.25:
            recenice.append(f"Igra u gostima, gde je čak bolji ({broj(gs['pir'])} PIR "
                            f"prema {broj(ds['pir'])} kod kuće).")
        elif not a["kod_kuce"] and ds["pir"] >= gs["pir"] * 1.25:
            recenice.append(f"Igra u gostima, gde je slabiji ({broj(gs['pir'])} PIR "
                            f"prema {broj(ds['pir'])} kod kuće).")

    if not recenice:
        recenice.append("Bez izraženih odstupanja: očekuje se učinak blizu sezonskog proseka.")
    return recenice[:3]


# ----------------------------- HTML -----------------------------
CSS = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#16191d;--ink2:#4a5058;--muted:#7a818b;--line:#e3e6ea;
--accent:#2a62d4;--accent-soft:#e8effc;--good:#1f7a4a;--bad:#b3372b;--bar:#2a62d4;--bar-avg:#9aa3ad}
@media (prefers-color-scheme:dark){:root{--bg:#121417;--card:#1b1e23;--ink:#eceef1;--ink2:#b5bbc3;
--muted:#8a919b;--line:#2c3138;--accent:#7aa4f5;--accent-soft:#1f2a40;--good:#5cc28a;--bad:#ef7d70;
--bar:#7aa4f5;--bar-avg:#5d6570}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:1100px;margin:0 auto;padding:24px 16px 48px}
h1{font-size:26px;margin:0 0 4px}
.sub{color:var(--muted);margin:0 0 24px}
h2{font-size:18px;margin:28px 0 12px}
.highlights{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px}
.box{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.box h3{margin:0 0 8px;font-size:15px}
.box ol{margin:0;padding-left:20px}
.box li{margin:3px 0}
.up{color:var(--good);font-weight:600}.down{color:var(--bad);font-weight:600}
details.mec{background:var(--card);border:1px solid var(--line);border-radius:10px;margin:10px 0}
details.mec>summary{cursor:pointer;padding:14px 16px;list-style:none;display:flex;flex-wrap:wrap;
gap:6px 16px;align-items:baseline}
details.mec>summary::-webkit-details-marker{display:none}
details.mec>summary::before{content:"▸";color:var(--muted);margin-right:-8px}
details.mec[open]>summary::before{content:"▾"}
.mec-naslov{font-weight:700;font-size:17px}
.mec-meta{color:var(--muted);font-size:14px}
.mec-telo{padding:0 16px 16px;display:grid;grid-template-columns:1fr 1fr;gap:20px}
@media (max-width:820px){.mec-telo{grid-template-columns:1fr}}
.tim h3{margin:4px 0 10px;font-size:16px}
.tim h3 small{color:var(--muted);font-weight:400}
.kartica{border:1px solid var(--line);border-radius:8px;padding:12px;margin-bottom:10px}
.k-glava{display:flex;justify-content:space-between;gap:8px;align-items:baseline}
.k-ime{font-weight:700}
.k-poz{color:var(--muted);font-size:13px}
.tiles{display:grid;grid-template-columns:repeat(7,1fr);gap:4px;margin:10px 0}
.tile{text-align:center;background:var(--accent-soft);border-radius:6px;padding:5px 2px}
.tile b{display:block;font-size:15px}
.tile span{font-size:11px;color:var(--ink2);text-transform:uppercase;letter-spacing:.03em}
@media (max-width:420px){.tiles{grid-template-columns:repeat(4,1fr)}}
.forma{display:flex;gap:12px;align-items:center;margin:6px 0 8px}
.forma svg{flex:none}
.forma-tekst{font-size:13px;color:var(--ink2)}
table.det{width:100%;border-collapse:collapse;font-size:13px}
table.det td{padding:4px 0;border-top:1px solid var(--line);vertical-align:top}
table.det td:first-child{color:var(--ink2);padding-right:8px;width:48%}
.rezime{margin:8px 0 0;padding:8px 10px;border-left:3px solid var(--accent);background:var(--accent-soft);
border-radius:0 6px 6px 0;font-size:13.5px}
.rezime p{margin:2px 0}
.bedz{display:inline-block;font-size:10.5px;font-weight:800;letter-spacing:.04em;padding:1px 6px;border-radius:4px;
margin-left:6px;vertical-align:1px;white-space:nowrap}
.st-ne{background:#fde2df;color:#9b2c20}.st-up{background:#fdf0cf;color:#7a5600}.st-vr{background:#dcf3e5;color:#1d6b40}
@media (prefers-color-scheme:dark){.st-ne{background:#4a1f1b;color:#ffb4a9}.st-up{background:#45390f;color:#f5d27a}
.st-vr{background:#173d29;color:#8fdcae}}
.van{font-size:13px;margin:-4px 0 10px;color:var(--ink2)}
.ostali{font-size:13px;color:var(--ink2);margin-top:6px}
footer{margin-top:36px;color:var(--muted);font-size:12.5px}
"""


def svg_forma(vrednosti, prosek, protivnici):
    """Mali stubičasti grafikon PIR-a u poslednjih 5 utakmica + linija proseka."""
    sirina, visina, sb, razmak = 150, 46, 22, 6
    vrh = max([abs(v) for v in vrednosti] + [prosek or 0, 1])
    nula = visina - 12
    skala = (nula - 4) / vrh
    delovi = [f'<svg width="{sirina}" height="{visina}" role="img" '
              f'aria-label="PIR u poslednjih {len(vrednosti)} utakmica">']
    for i, (v, prot) in enumerate(zip(vrednosti, protivnici)):
        x = i * (sb + razmak) + 2
        h = max(abs(v) * skala, 2)
        y = nula - h if v >= 0 else nula
        delovi.append(f'<rect x="{x}" y="{y:.1f}" width="{sb}" height="{h:.1f}" rx="3" '
                      f'fill="var(--bar)"><title>PIR {v} protiv {e(prot)}</title></rect>')
        delovi.append(f'<text x="{x + sb / 2}" y="{visina - 1}" font-size="10" '
                      f'text-anchor="middle" fill="var(--muted)">{v}</text>')
    if prosek is not None:
        y = nula - prosek * skala
        delovi.append(f'<line x1="0" x2="{sirina}" y1="{y:.1f}" y2="{y:.1f}" stroke="var(--bar-avg)" '
                      f'stroke-width="1.5" stroke-dasharray="3 3"><title>Sezonski prosek PIR '
                      f'{broj(prosek)}</title></line>')
    delovi.append("</svg>")
    return "".join(delovi)


def strelica(novo, staro):
    ocena = ocena_forme(novo, staro)
    if ocena > 0:
        return '<span class="up">▲ forma</span>'
    if ocena < 0:
        return '<span class="down">▼ forma</span>'
    return '<span class="k-poz">● stabilno</span>'


def html_kartica(a, protivnik_naziv):
    s, f = a["sezona"], a["forma"]
    tiles = [("min", broj(s["min"])), ("poeni", broj(s["pts"])), ("skok", broj(s["reb"])),
             ("asist", broj(s["ast"])), ("PIR", broj(s["pir"])), ("TS%", procenat(s["ts"])),
             ("eFG%", procenat(s["efg"]))]

    def kratko(z):
        return "–" if not z else f"{broj(z['pts'])} p · {broj(z['pir'])} PIR ({z['gp']})"

    redovi = []
    oznaka_dom = " ← sledeći meč" if a["kod_kuce"] else ""
    oznaka_gost = "" if a["kod_kuce"] else " ← sledeći meč"
    redovi.append(("Kod kuće" + oznaka_dom, kratko(a["dom"])))
    redovi.append(("U gostima" + oznaka_gost, kratko(a["gost"])))
    if a["protiv"]:
        p, pos = a["protiv"], a["protiv_poslednja"]
        redovi.append((f"Protiv: {protivnik_naziv} (sve sezone)",
                       f"{kratko(p)}<br><span class='k-poz'>poslednji put {datum_srb(pos['datum'])}: "
                       f"{pos['poeni']} p, {pos['pir']} PIR</span>"))
    else:
        redovi.append((f"Protiv: {protivnik_naziv}", "nisu igrali u poslednje 4 sezone"))
    if a["doz"] and a["poz_kod"]:
        r, uk = a["rang"]
        redovi.append((f"{protivnik_naziv} dozvoljava {POZICIJA_MNOZINA[a['poz_kod']]} (zbirno)",
                       f"{broj(a['doz']['pts'])} p · {broj(a['doz']['pir'])} PIR po meču "
                       f"<span class='k-poz'>({r}. najviše od {uk})</span>"))

    min_trend = ""
    if a["min_trend"] is not None:
        znak = "+" if a["min_trend"] > 0 else ""
        min_trend = f" · minuti poslednje 3: {znak}{broj(a['min_trend'])}"

    return f"""
<div class="kartica">
  <div class="k-glava"><span class="k-ime">{ime_html(a)}</span>
    <span class="k-poz">{e(a['poz'])} · {utakmica_rec(s['gp'])}</span></div>
  <div class="tiles">{''.join(f'<div class="tile"><b>{v}</b><span>{k}</span></div>' for k, v in tiles)}</div>
  <div class="forma">{svg_forma(a['forma_pir'], s['pir'], a['forma_protivnici'])}
    <div class="forma-tekst">Poslednjih {f['gp']}: <b>{broj(f['pts'])}</b> p, <b>{broj(f['pir'])}</b> PIR
      {strelica(f['pir'], s['pir'])}<br>{broj(f['min'])} min{min_trend}</div></div>
  <table class="det">{''.join(f'<tr><td>{k}</td><td>{v}</td></tr>' for k, v in redovi)}</table>
  <div class="rezime">{''.join(f'<p>{e(r)}</p>' for r in a['rezime'])}</div>
</div>"""


def html_tim(tim, naziv, skor, analize, protivnik_naziv, kod_kuce):
    glavni = [a for a in analize if a["sezona"]["min"] >= MIN_MINUTA_ZA_KARTICU]
    ostali = [a for a in analize if a["sezona"]["min"] < MIN_MINUTA_ZA_KARTICU]
    w, l = skor[tim]
    delovi = [f'<div class="tim"><h3>{e(naziv)} <small>{w}-{l} · '
              f'{"domaćin" if kod_kuce else "gost"}</small></h3>']
    statusi = [a for a in analize if a["id"] in POVREDE]
    if statusi:
        delovi.append('<p class="van"><b>Status:</b> ' + ", ".join(ime_html(a) for a in statusi) + "</p>")
    delovi += [html_kartica(a, protivnik_naziv) for a in glavni]
    if ostali:
        delovi.append('<div class="ostali"><b>Ostali</b> (manje od '
                      f'{MIN_MINUTA_ZA_KARTICU} min): ' + ", ".join(
                          f"{ime_html(a)} ({broj(a['sezona']['min'])} min, "
                          f"{broj(a['sezona']['pts'])} p)" for a in ostali) + "</div>")
    delovi.append("</div>")
    return "".join(delovi)


def telo_najave(sezona, kolo, mecevi, timovi, skor, analize_po_mecu, sve_analize):
    """Sadržaj najave (bez zaglavlja stranice) - koristi ga i sajt.py."""
    naziv = lambda t: timovi.get(t, t)

    # Istaknuto: najveći skok i pad forme (bar 4 utakmice i 15 min)
    kandidati = [a for a in sve_analize if a["sezona"]["gp"] >= 4 and a["sezona"]["min"] >= 15]
    razlika = lambda a: a["forma"]["pir"] - a["sezona"]["pir"]
    u_formi = sorted(kandidati, key=razlika, reverse=True)[:5]
    pad = sorted(kandidati, key=razlika)[:5]

    def lista(igraci, klasa):
        return "<ol>" + "".join(
            f"<li>{ime_html(a, True)} ({e(naziv(a['tim']))}): {broj(a['forma']['pir'])} PIR u "
            f"poslednjih {a['forma']['gp']}, prosek {broj(a['sezona']['pir'])} "
            f"<span class='{klasa}'>{'+' if razlika(a) > 0 else ''}{broj(razlika(a))}</span></li>"
            for a in igraci) + "</ol>"

    delovi = [f"""<h1>Najava {kolo}. kola</h1>
<p class="sub">Evroliga {sezona}-{str(sezona + 1)[-2:]} · {len(mecevi)} utakmica ·
napravljeno {datetime.now().strftime('%d.%m.%Y. %H:%M')}</p>
<div class="highlights">
  <div class="box"><h3>U najboljoj formi</h3>{lista(u_formi, 'up')}</div>
  <div class="box"><h3>Najveći pad forme</h3>{lista(pad, 'down')}</div>
</div>
<h2>Utakmice</h2>"""]

    for m in mecevi:
        dt = datetime.strptime(m["datum"], "%Y-%m-%d %H:%M")
        dom, gost = m["domacin"], m["gost"]
        delovi.append(f"""<details class="mec"><summary>
<span class="mec-naslov">{e(naziv(dom))} – {e(naziv(gost))}</span>
<span class="mec-meta">{DANI[dt.weekday()]} {dt.strftime('%d.%m. u %H:%M')} ·
skor {skor[dom][0]}-{skor[dom][1]} / {skor[gost][0]}-{skor[gost][1]}</span></summary>
<div class="mec-telo">
{html_tim(dom, naziv(dom), skor, analize_po_mecu[(m['sifra_utakmice'], dom)], naziv(gost), True)}
{html_tim(gost, naziv(gost), skor, analize_po_mecu[(m['sifra_utakmice'], gost)], naziv(dom), False)}
</div></details>""")
    return "".join(delovi)


FOOTER = """<footer>EuroCourt je nezavisan sajt i nije povezan sa Euroleague Basketball.
Statistički podaci: Euroleague Basketball (javno dostupna statistika). PIR = indeks korisnosti; TS% = pravi procenat šuta; eFG% = efektivni procenat
šuta iz igre. "Dozvoljava" = prosečan zbir svih igrača te pozicije protiv tog tima u ovoj sezoni,
rang 1 = najviše dozvoljava.</footer>"""


def napravi_stranicu(sezona, kolo, mecevi, timovi, skor, analize_po_mecu, sve_analize):
    """Samostalna HTML stranica najave (folder izvestaji)."""
    return f"""<!doctype html><html lang="sr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Najava {kolo}. kola · Evroliga {sezona}-{str(sezona + 1)[-2:]}</title>
<style>{CSS}</style></head><body><div class="wrap">
{telo_najave(sezona, kolo, mecevi, timovi, skor, analize_po_mecu, sve_analize)}
{FOOTER}</div></body></html>"""


# ----------------------------- GLAVNI DEO -----------------------------
def analiziraj_kolo(baza):
    """Učita bazu i analizira sve igrače narednog kola. Vraća rečnik sa svim podacima."""
    podaci = ucitaj(baza)
    if not podaci:
        return None
    sezona, kolo, mecevi, timovi, igraci, statistika, skor = podaci
    po_sezona, po_sve, poslednji_tim, dozvoljeno, rang = pripremi(sezona, igraci, statistika)

    analize_po_mecu, sve_analize = {}, []
    for m in mecevi:
        for tim, protivnik, kod_kuce in ((m["domacin"], m["gost"], True),
                                         (m["gost"], m["domacin"], False)):
            sastav = [i for i, t in poslednji_tim.items() if t == tim and po_sezona[i]]
            analize = []
            for igrac_id in sastav:
                a = analiziraj_igraca(igrac_id, tim, protivnik, kod_kuce, igraci, po_sezona,
                                      po_sve, dozvoljeno, rang)
                a["rezime"] = rezime(a, timovi.get(protivnik, protivnik))
                a["tim"] = tim
                analize.append(a)
            analize.sort(key=lambda a: -a["sezona"]["min"])
            analize_po_mecu[(m["sifra_utakmice"], tim)] = analize
            sve_analize += analize

    return dict(sezona=sezona, kolo=kolo, mecevi=mecevi, timovi=timovi, igraci=igraci,
                statistika=statistika, skor=skor, po_sezona=po_sezona, po_sve=po_sve,
                poslednji_tim=poslednji_tim, dozvoljeno=dozvoljeno, rang=rang,
                analize_po_mecu=analize_po_mecu, sve_analize=sve_analize)


def main():
    if not BAZA.exists():
        print(f"Nema baze: {BAZA}. Prvo pokreni azuriraj_bazu.py.")
        return
    baza = sqlite3.connect(BAZA)
    k = analiziraj_kolo(baza)
    baza.close()
    if not k:
        print("Nema zakazanih utakmica u tekućoj sezoni.")
        return
    sezona, kolo, mecevi, sve_analize = k["sezona"], k["kolo"], k["mecevi"], k["sve_analize"]

    IZLAZ.mkdir(exist_ok=True)
    stranica = napravi_stranicu(sezona, kolo, mecevi, k["timovi"], k["skor"],
                                k["analize_po_mecu"], sve_analize)
    putanja = IZLAZ / f"najava_{sezona}_kolo{kolo:02d}.html"
    putanja.write_text(stranica, encoding="utf-8")
    (IZLAZ / "najava.html").write_text(stranica, encoding="utf-8")  # uvek poslednja najava
    print(f"Gotovo! Najava {kolo}. kola: {len(mecevi)} utakmica, {len(sve_analize)} igrača.")
    print(f"Otvori fajl: {putanja}")


if __name__ == "__main__":
    main()
