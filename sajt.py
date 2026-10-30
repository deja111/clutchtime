"""
sajt.py
--------
Pravi ceo sajt (statičke HTML stranice) iz baze podaci/evroliga.db
u folder "sajt". Početna stranica je sajt/index.html.

Pokretanje (Command Prompt, iz foldera Projekat):
    python sajt.py

Stranice:
    index.html          - početna: pretraga, MVP kola, lideri, forma, rezultati
    utakmice.html       - naredno kolo (samo mečevi) i rezultati po kolima
    propovi.html        - propovi kola: linije (kvote.py) + procena modela (model.py)
    forma.html          - forma igrača: poslednjih 5 utakmica prema sezoni
    najava.html         - samo preusmerava na utakmice.html (stara adresa)
    lideri.html         - lideri sezone po kategorijama
    utakmica/<id>.html  - box score svake odigrane utakmice tekuće sezone
    igraci.html         - svi igrači tekuće sezone (pretraga i sortiranje) + kartice igrača narednog kola
    igrac/<id>.html     - profil igrača: proseci, grafikoni, utakmice, po sezonama
    timovi.html         - tabela lige
    tim/<sifra>.html    - tim: igrači, rezultati i raspored

Računanje (forma, TS%, protivnik...) koristi funkcije iz analiza.py.
"""

import json
import math
import shutil
import sqlite3
from datetime import date, datetime
from pathlib import Path

import analiza as A
import model as M
import povrede as POV
from analiza import broj, procenat, e, zbirno, datum_srb, utakmica_rec

FOLDER = Path(__file__).parent
BAZA = FOLDER / "podaci" / "evroliga.db"
KVOTE = FOLDER / "podaci" / "kvote" / "kvote_poslednje.json"  # pravi ga kvote.py
PREDLOZI = FOLDER / "podaci" / "kvote" / "predlozi.json"      # predlozi pre utakmica, za praćenje rezultata
TIKETI = FOLDER / "podaci" / "kvote" / "tiketi.json"          # tiket dana (do 3 predloga), za praćenje
SAJT = FOLDER / "sajt"
NAZIV_SAJTA = "ClutchTime"

ZNAK = '<span class="znak">Clutch<b>Time</b></span>'  # naziv u logou, "Time" u boji akcenta

# Logo: lopta kao štoperica (dugme na vrhu) - "clutch" = poslednje sekunde meča.
# Isti crtež je i ikonica u kartici pregledača (sajt/logo.svg).
LOGO_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" aria-hidden="true">
<rect x="12.5" y="0.5" width="7" height="3" rx="1.2" fill="#ff7a1a"/>
<rect x="15" y="3" width="2" height="3.5" fill="#ff7a1a"/>
<rect x="24.6" y="5.2" width="4" height="2.4" rx="1" transform="rotate(45 26.6 6.4)" fill="#ff7a1a"/>
<circle cx="16" cy="19" r="12.3" fill="#ff7a1a"/>
<g fill="none" stroke="#1a120b" stroke-width="1.5" stroke-linecap="round">
<path d="M3.9 19h24.2M16 6.9v24.2"/>
<path d="M7.6 10.2c3.6 4.2 3.6 13.4 0 17.6M24.4 10.2c-3.6 4.2-3.6 13.4 0 17.6"/></g>
</svg>"""

DODATNI_CSS = """
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
.nav{background:var(--card);border-bottom:2px solid var(--accent);position:sticky;top:0;z-index:50}
.nav .in{max-width:1100px;margin:0 auto;padding:10px 16px;display:flex;gap:18px;align-items:center}
.nav .logo{display:flex;align-items:center;gap:8px;font-weight:900;font-size:19px;letter-spacing:-.02em;
color:var(--ink);margin-right:auto;white-space:nowrap}
.nav .logo svg{width:28px;height:28px;flex:none}
.nav .logo:hover{text-decoration:none}
.znak b{color:var(--accent);font-weight:inherit}
.hero .naslov{display:flex;align-items:center;gap:12px}
.hero .naslov svg{width:46px;height:46px;flex:none}
.nav .meni{display:flex;gap:4px;overflow-x:auto;white-space:nowrap;scrollbar-width:none}
.nav .meni::-webkit-scrollbar{display:none}
.nav .meni a{color:var(--ink2);font-weight:600;padding:6px 10px;border-radius:6px}
.nav .meni a:hover{color:var(--ink);background:var(--card2);text-decoration:none}
.nav .meni a.akt{color:var(--on-accent);background:var(--accent)}
@media (max-width:640px){.nav .in{flex-direction:column;align-items:flex-start;gap:6px;padding:8px 16px}
.nav .meni{width:100%;gap:2px}.nav .meni a{padding:5px 8px}}
.hero{background:linear-gradient(135deg,var(--accent-soft),var(--card) 60%);border:1px solid var(--line);
border-radius:12px;padding:22px 18px;margin:8px 0 14px}
.hero h1{margin:0 0 4px}
.pretraga{position:relative;margin-top:14px}
.pretraga input{width:100%;font:inherit;font-size:17px;padding:12px 14px;border:1px solid var(--line);
border-radius:10px;background:var(--bg);color:var(--ink)}
.pretraga input:focus{outline:2px solid var(--accent);outline-offset:1px}
.rezultati{position:absolute;left:0;right:0;top:100%;margin-top:4px;background:var(--card);border:1px solid var(--line);
border-radius:10px;box-shadow:0 8px 24px rgba(0,0,0,.15);z-index:40;max-height:360px;overflow:auto}
.rezultati a{display:flex;justify-content:space-between;gap:10px;padding:9px 14px;border-bottom:1px solid var(--line);color:var(--ink)}
.rezultati a:hover,.rezultati a.izabran{background:var(--accent-soft);text-decoration:none}
.rezultati span{color:var(--muted);font-size:13px}
.mvp{display:flex;gap:16px;align-items:center;background:linear-gradient(135deg,var(--accent-soft),var(--card));
border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin:14px 0}
:root{--on-accent:#140d06}
@media (prefers-color-scheme:light){:root{--on-accent:#fff}}
.mvp .krug{flex:none;width:64px;height:64px;border-radius:50%;background:var(--accent);color:var(--on-accent);display:flex;
align-items:center;justify-content:center;font-weight:800;font-size:22px}
.mvp .oznaka{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--ink2);font-weight:700}
.mvp .ime{font-size:22px;font-weight:800;margin:2px 0}
.mvp .brojke{color:var(--ink2);font-size:14px}
.mvp .brojke b{color:var(--ink);font-size:16px}
.mreza{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}
.mini{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.mini h3{margin:0 0 8px;font-size:14px;display:flex;justify-content:space-between}
.mini h3 a{font-weight:400;font-size:12.5px}
.mini ol{margin:0;padding:0;list-style:none;counter-reset:r}
.mini li{display:flex;justify-content:space-between;gap:8px;padding:5px 0;border-top:1px solid var(--line);font-size:14px}
.mini li:first-child{border-top:0}
.mini li::before{counter-increment:r;content:counter(r);color:var(--muted);width:16px;flex:none}
.mini li .ko{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.mini li .ko small{color:var(--muted)}
.mini li b{font-variant-numeric:tabular-nums}
.traka{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:10px}
@media (max-width:640px){.traka{display:flex;overflow-x:auto;padding-bottom:6px}}
.mec-k{flex:none;min-width:160px;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px;
color:var(--ink);font-size:14px}
a.mec-k:hover{border-color:var(--accent);text-decoration:none}
.mec-k .r{display:flex;justify-content:space-between;gap:10px;font-variant-numeric:tabular-nums}
.mec-k .r.pob{font-weight:700}
.mec-k .d{color:var(--muted);font-size:12px;margin-bottom:4px}
.naslov-sekcije{display:flex;justify-content:space-between;align-items:baseline;margin:22px 0 10px}
.naslov-sekcije h2{margin:0;font-size:18px;padding-left:10px;border-left:4px solid var(--accent)}
.mecevi{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}
.mec-red{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.mec-red .d{color:var(--muted);font-size:12.5px;margin-bottom:6px}
.mec-red .t{display:flex;justify-content:space-between;gap:10px;font-weight:700;font-size:16px}
.mec-red .t small{color:var(--muted);font-weight:400;font-size:13px}
.mec-red .st{font-size:12.5px;color:var(--ink2);margin-top:8px}
.mec-red .vise{display:inline-block;margin-top:8px;font-size:13.5px;font-weight:600}
.upozorenje{display:flex;gap:12px;align-items:center;background:var(--card);border:1px solid var(--line);
border-left:4px solid var(--bad);border-radius:10px;padding:10px 14px;margin:0 0 14px;font-size:13.5px;color:var(--ink2)}
.upozorenje .g18{flex:none;font-weight:900;font-size:15px;color:var(--bad);border:2px solid var(--bad);border-radius:50%;
width:38px;height:38px;display:flex;align-items:center;justify-content:center}
table.tab td.zasto{white-space:normal;min-width:260px;max-width:380px}
.zasto .ime{font-weight:700}.zasto small{display:block;color:var(--muted);font-size:12px;line-height:1.4;margin-top:2px}
.strana{font-weight:800;text-transform:uppercase;font-size:12px;letter-spacing:.04em}
.strana.preko{color:var(--good)}.strana.ispod{color:var(--bad)}
.ocena{display:inline-block;font-size:11.5px;font-weight:800;padding:2px 8px;border-radius:999px;letter-spacing:.02em}
.o-jaka{background:var(--good);color:var(--on-accent)}.o-srednja{border:1px solid var(--good);color:var(--good)}
.o-slaba{color:var(--ink2)}.o-nema{color:var(--muted)}
.tiket{background:linear-gradient(135deg,var(--accent-soft),var(--card) 70%);border:1px solid var(--accent);
border-radius:12px;padding:14px 16px;margin:14px 0}
.tiket-glava{display:flex;justify-content:space-between;align-items:baseline;gap:10px;flex-wrap:wrap}
.tiket-glava h2{margin:0 0 8px;font-size:18px}
.tiket-zbir{display:flex;gap:24px;flex-wrap:wrap;margin-top:10px;font-size:15px}
.tiket-zbir b{font-size:20px;color:var(--accent);margin-left:6px}
.svi-propovi{margin:14px 0}.svi-propovi>summary{cursor:pointer;font-weight:700;padding:10px 14px;background:var(--card);
border:1px solid var(--line);border-radius:10px}.svi-propovi[open]>summary{border-color:var(--accent)}
.napomena{font-size:12.5px;color:var(--muted)}
.box-glava{display:flex;justify-content:center;align-items:center;gap:22px;flex-wrap:wrap;text-align:center}
.box-glava .tim-n{font-size:20px;font-weight:800}
.box-glava .skor{font-size:34px;font-weight:800;font-variant-numeric:tabular-nums}
.box-glava .pob{color:var(--ink)}.box-glava .por{color:var(--muted)}
tr.ukupno td{font-weight:700;border-top:2px solid var(--line)}
.karta{display:flex;gap:16px;align-items:center;margin:8px 0 6px}
.karta .krug{flex:none;width:72px;height:72px;border-radius:50%;background:var(--accent);color:var(--on-accent);
display:flex;align-items:center;justify-content:center;font-weight:800;font-size:24px}
.karta h1{margin:0 0 4px}.karta .info{margin:0;line-height:1.6}
.adv-mreza{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
@media (max-width:820px){.adv-mreza{grid-template-columns:repeat(2,1fr)}}
.adv{background:var(--accent-soft);border-radius:8px;padding:12px}
.adv-v{font-size:24px;font-weight:800;font-variant-numeric:tabular-nums}
.adv-n{font-weight:700;margin-top:2px}
.adv-r{font-size:12.5px;color:var(--ink2);margin-top:2px}
.adv-o{font-size:12px;color:var(--muted);margin-top:6px;line-height:1.35}
.grafikon.uska svg{max-width:520px}
.sekcija{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin:14px 0}
.sekcija h2{margin:0 0 10px;font-size:17px}
.skrol{overflow-x:auto}
table.tab{width:100%;border-collapse:collapse;font-size:13.5px;font-variant-numeric:tabular-nums}
table.tab th,table.tab td{padding:6px 8px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}
table.tab th{color:var(--ink2);font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.03em}
table.tab th.l,table.tab td.l{text-align:left}
table.tab th[data-k]{cursor:pointer}table.tab th[data-k]:hover{color:var(--accent)}
table.tab tr:hover td{background:var(--accent-soft)}
.p{color:var(--good);font-weight:700}.i{color:var(--bad);font-weight:700}
.info{color:var(--ink2);margin:0 0 6px}
.u-profilu .k-glava,.u-profilu .tiles{display:none}
.u-profilu .kartica{border:0;padding:0;margin:0}
.filteri{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 10px}
.filteri input,.filteri select{font:inherit;padding:6px 8px;border:1px solid var(--line);border-radius:6px;
background:var(--card);color:var(--ink)}
.grafikon svg{width:100%;height:auto;display:block}
.grafikon .opis{font-size:12.5px;color:var(--muted);margin:4px 0 0}
.dva{display:grid;grid-template-columns:1fr 1fr;gap:14px}
@media (max-width:820px){.dva{grid-template-columns:1fr}}
.tiles.velike{grid-template-columns:repeat(7,1fr);max-width:640px}
@media (max-width:420px){.tiles.velike{grid-template-columns:repeat(4,1fr)}}
"""

JS_TABELA = """
<script>
document.querySelectorAll('table.sort').forEach(function(t){
  t.querySelectorAll('th[data-k]').forEach(function(th,i){
    th.addEventListener('click',function(){
      var tb=t.tBodies[0],r=[].slice.call(tb.rows),kol=th.cellIndex,
          num=th.dataset.k==='n',smer=th.dataset.s==='d'?1:-1;
      th.dataset.s=smer===1?'a':'d';
      r.sort(function(a,b){var x=a.cells[kol].dataset.v||a.cells[kol].textContent,
        y=b.cells[kol].dataset.v||b.cells[kol].textContent;
        return num?(parseFloat(x)-parseFloat(y))*smer:x.localeCompare(y)*smer;});
      r.forEach(function(x){tb.appendChild(x);});
    });
  });
});
var f=document.getElementById('filter');
if(f){var fi=function(){var q=document.getElementById('trazi').value.toLowerCase(),
  tm=document.getElementById('tim').value,pz=document.getElementById('poz').value;
  document.querySelectorAll('#igraci tbody tr').forEach(function(r){
    var ok=r.dataset.ime.indexOf(q)>-1&&(!tm||r.dataset.tim===tm)&&(!pz||r.dataset.poz===pz);
    r.style.display=ok?'':'none';});};
  f.addEventListener('input',fi);f.addEventListener('change',fi);}
</script>"""


# ----------------------------- ZAJEDNIČKO -----------------------------
def strana(naslov, telo, koren="", aktivno="", skripta=False, dodatak=""):
    """Okvir svake stranice: zaglavlje sa menijem, sadržaj, podnožje."""
    meni = [("index.html", "Početna"), ("utakmice.html", "Utakmice"), ("propovi.html", "Propovi"),
            ("forma.html", "Forma"), ("igraci.html", "Igrači"), ("timovi.html", "Timovi"), ("lideri.html", "Lideri")]
    linkovi = "".join(
        f'<a href="{koren}{h}"{" class=akt" if h == aktivno else ""}>{t}</a>' for h, t in meni)
    return f"""<!doctype html><html lang="sr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(naslov)} · {NAZIV_SAJTA}</title>
<link rel="icon" href="{koren}logo.svg" type="image/svg+xml">
<link rel="stylesheet" href="{koren}stil.css"></head><body>
<nav class="nav"><div class="in"><a class="logo" href="{koren}index.html">{LOGO_SVG}{ZNAK}</a>
<div class="meni">{linkovi}</div></div></nav>
<div class="wrap">{telo}
{A.FOOTER}
<p style="color:var(--muted);font-size:12px">Ažurirano {datetime.now().strftime('%d.%m.%Y. %H:%M')}</p>
</div>{JS_TABELA if skripta else ""}{dodatak}</body></html>"""


def snimi(putanja, sadrzaj):
    putanja.parent.mkdir(parents=True, exist_ok=True)
    putanja.write_text(sadrzaj, encoding="utf-8")


def oznaka_sezone(s):
    return f"{s}-{str(s + 1)[-2:]}"


def godine(datum_rodjenja):
    if not datum_rodjenja:
        return None
    d = datetime.strptime(datum_rodjenja[:10], "%Y-%m-%d").date()
    danas = date.today()
    return danas.year - d.year - ((danas.month, danas.day) < (d.month, d.day))


def svg_stubici(vrednosti, opisi, prosek, naziv, oznake=None, natpisi=False, sirina=640):
    """Stubičasti grafikon jedne vrednosti po utakmici + isprekidana linija proseka."""
    if not vrednosti:
        return "<p class='opis'>Nema podataka.</p>"
    visina, levo, dole = 170, 30, 20
    n = len(vrednosti)
    korak = (sirina - levo - 4) / n
    sb = max(min(korak * 0.7, 26), 3)
    vrh = max(max(vrednosti), prosek or 0, 1) * (1.12 if natpisi else 1)
    dno = min(min(vrednosti), 0)
    opseg = vrh - dno
    y = lambda v: 6 + (vrh - v) / opseg * (visina - dole - 6)
    d = [f'<svg viewBox="0 0 {sirina} {visina}" role="img" aria-label="{e(naziv)}">']
    for v in (vrh, 0) if dno == 0 else (vrh, 0, dno):
        d.append(f'<text x="{levo - 6}" y="{y(v) + 4:.1f}" font-size="11" text-anchor="end" '
                 f'fill="var(--muted)">{broj(v, 0)}</text>')
    d.append(f'<line x1="{levo}" x2="{sirina}" y1="{y(0):.1f}" y2="{y(0):.1f}" stroke="var(--line)"/>')
    for i, (v, opis) in enumerate(zip(vrednosti, opisi)):
        x = levo + i * korak + (korak - sb) / 2
        y1, y2 = sorted((y(v), y(0)))
        h = max(y2 - y1, 1.5)
        d.append(f'<rect x="{x:.1f}" y="{y1:.1f}" width="{sb:.1f}" height="{h:.1f}" rx="3" '
                 f'fill="var(--bar)"><title>{e(opis)}</title></rect>')
        # Široka nevidljiva površina da hover radi i na tankim stubićima
        d.append(f'<rect x="{levo + i * korak:.1f}" y="0" width="{korak:.1f}" height="{visina - dole}" '
                 f'fill="transparent"><title>{e(opis)}</title></rect>')
        if oznake or n <= 20 or i % 2 == 0:
            d.append(f'<text x="{x + sb / 2:.1f}" y="{visina - 5}" font-size="{11 if oznake else 10}" '
                     f'text-anchor="middle" fill="var(--muted)">{e(oznake[i]) if oznake else i + 1}</text>')
        if natpisi:
            d.append(f'<text x="{x + sb / 2:.1f}" y="{y1 - 5:.1f}" font-size="12" font-weight="700" '
                     f'text-anchor="middle" fill="var(--ink)">{broj(v)}</text>')
    if prosek is not None:
        d.append(f'<line x1="{levo}" x2="{sirina}" y1="{y(prosek):.1f}" y2="{y(prosek):.1f}" '
                 f'stroke="var(--bar-avg)" stroke-width="1.5" stroke-dasharray="4 4"/>')
    d.append("</svg>")
    return "".join(d)


def rezultat(r):
    """Iz ugla igračevog tima: ('P', '85:79') ili ('I', '70:81')."""
    if r["poeni_domacin"] is None:
        return "", ""
    nas, njih = ((r["poeni_domacin"], r["poeni_gost"]) if r["domacin"] == 1
                 else (r["poeni_gost"], r["poeni_domacin"]))
    return ("P" if nas > njih else "I"), f"{nas}:{njih}"


def tiles(z, klasa="tiles"):
    stavke = [("min", broj(z["min"])), ("poeni", broj(z["pts"])), ("skok", broj(z["reb"])),
              ("asist", broj(z["ast"])), ("PIR", broj(z["pir"])), ("TS%", procenat(z["ts"])),
              ("eFG%", procenat(z["efg"]))]
    return f'<div class="{klasa}">' + "".join(
        f'<div class="tile"><b>{v}</b><span>{k}</span></div>' for k, v in stavke) + "</div>"


# ----------------------------- STRANICE -----------------------------
def kartica_rezultata(k, u):
    naziv = lambda t: k["timovi"].get(t, t)
    dom_pob = u["poeni_domacin"] > u["poeni_gost"]
    dt = datetime.strptime(u["datum"], "%Y-%m-%d %H:%M")
    return (f'<a class="mec-k" href="utakmica/{u["sezona"]}-{u["sifra_utakmice"]}.html">'
            f'<div class="d">{dt.strftime("%d.%m.")} · box score</div>'
            f'<div class="r{" pob" if dom_pob else ""}"><span>{e(naziv(u["domacin"]))}</span><span>{u["poeni_domacin"]}</span></div>'
            f'<div class="r{"" if dom_pob else " pob"}"><span>{e(naziv(u["gost"]))}</span><span>{u["poeni_gost"]}</span></div></a>')


def stranica_utakmice(k, lista, utakmice):
    """Naredno kolo (samo mečevi, bez kartica igrača) i rezultati svih odigranih kola."""
    naziv = lambda t: k["timovi"].get(t, t)
    skor = k["skor"]
    po_id = {r["id"]: r for r in lista}

    def status_tima(tim):
        imena = [f'<a href="igrac/{i}.html">{e(po_id[i]["ime"])}</a>{A.bedz(i)}'
                 for i in A.POVREDE if i in po_id and po_id[i]["tim"] == tim]
        return f'<div class="st"><b>{e(naziv(tim))}:</b> {", ".join(imena)}</div>' if imena else ""

    kartice = []
    for m in k["mecevi"]:
        dt = datetime.strptime(m["datum"], "%Y-%m-%d %H:%M")
        dom, gost = m["domacin"], m["gost"]
        kartice.append(
            f'<div class="mec-red"><div class="d">{A.DANI[dt.weekday()]} {dt.strftime("%d.%m. u %H:%M")}</div>'
            f'<div class="t"><a href="tim/{dom}.html">{e(naziv(dom))}</a><small>{skor[dom][0]}-{skor[dom][1]}</small></div>'
            f'<div class="t"><a href="tim/{gost}.html">{e(naziv(gost))}</a><small>{skor[gost][0]}-{skor[gost][1]}</small></div>'
            f'{status_tima(dom)}{status_tima(gost)}'
            f'<a class="vise" href="igraci.html#mec-{m["sifra_utakmice"]}">Igrači ovog meča →</a></div>')

    po_kolu = {}
    for u in utakmice:
        if u["odigrana"]:
            po_kolu.setdefault(u["kolo"], []).append(u)
    rezultati = "".join(
        f'<div class="naslov-sekcije"><h2>{kolo}. kolo</h2></div><div class="traka">'
        + "".join(kartica_rezultata(k, u) for u in sorted(po_kolu[kolo], key=lambda u: u["datum"])) + "</div>"
        for kolo in sorted(po_kolu, reverse=True))

    telo = f"""<h1>Utakmice</h1>
<p class="sub">Evroliga {oznaka_sezone(k['sezona'])}</p>
<div class="naslov-sekcije"><h2>Naredno kolo ({k['kolo']}.)</h2></div>
<div class="mecevi">{''.join(kartice)}</div>
<p class="napomena">Pored tima je skor u sezoni (pobede-porazi). Ispod su igrači sa statusom iz tabele povreda.</p>
{rezultati}"""
    snimi(SAJT / "utakmice.html", strana("Utakmice", telo, "", "utakmice.html"))
    # Stara adresa najave vodi na novu stranicu (za sačuvane linkove)
    snimi(SAJT / "najava.html", '<!doctype html><meta charset="utf-8">'
          '<meta http-equiv="refresh" content="0;url=utakmice.html"><a href="utakmice.html">Utakmice</a>')


def stranica_forma(k, lista):
    """Forma: poslednjih 5 utakmica u odnosu na sezonski prosek."""
    naziv = lambda t: k["timovi"].get(t, t)
    redovi = []
    for r in lista:
        ut = k["po_sezona"][r["id"]]
        if len(ut) < 3:
            continue
        f = zbirno(ut[-5:])
        redovi.append({**r, "f": f, "razlika": f["pir"] - r["z"]["pir"]})
    kandidati = [r for r in redovi if r["z"]["gp"] >= 4 and r["z"]["min"] >= 15]

    def lista_forme(igraci, klasa, znak):
        return "<ol>" + "".join(
            f'<li><span class="ko"><a href="igrac/{r["id"]}.html">{e(r["ime"])}</a>{A.bedz(r["id"])} '
            f'<small>{e(naziv(r["tim"]))}</small></span>'
            f'<span>{broj(r["f"]["pir"])} <small class="napomena">(prosek {broj(r["z"]["pir"])})</small> '
            f'<b class="{klasa}">{znak} {broj(abs(r["razlika"]))}</b></span></li>' for r in igraci) + "</ol>"
    vruci = sorted(kandidati, key=lambda r: -r["razlika"])[:10]
    hladni = sorted(kandidati, key=lambda r: r["razlika"])[:10]

    tabela = "".join(
        f'<tr><td class="l"><a href="igrac/{r["id"]}.html">{e(r["ime"])}</a>{A.bedz(r["id"])}</td>'
        f'<td class="l"><a href="tim/{r["tim"]}.html">{e(naziv(r["tim"]))}</a></td>'
        f'<td class="l">{e(r["poz"])}</td>'
        f'<td data-v="{r["f"]["min"]:.2f}">{broj(r["f"]["min"])}</td>'
        f'<td data-v="{r["f"]["pts"]:.2f}">{broj(r["f"]["pts"])}</td>'
        f'<td data-v="{r["f"]["pir"]:.2f}"><b>{broj(r["f"]["pir"])}</b></td>'
        f'<td data-v="{r["z"]["pir"]:.2f}">{broj(r["z"]["pir"])}</td>'
        f'<td data-v="{r["razlika"]:.2f}" class="{"up" if r["razlika"] > 0 else "down"}">'
        f'{"+" if r["razlika"] > 0 else ""}{broj(r["razlika"])}</td></tr>'
        for r in sorted(redovi, key=lambda r: -r["razlika"]))

    telo = f"""<h1>Forma igrača</h1>
<p class="sub">Evroliga {oznaka_sezone(k['sezona'])} · poslednjih 5 utakmica u odnosu na sezonski prosek</p>
<div class="mreza">
<div class="mini"><h3>🔥 U najboljoj formi</h3>{lista_forme(vruci, 'up', '▲')}</div>
<div class="mini"><h3>❄️ Najveći pad forme</h3>{lista_forme(hladni, 'down', '▼')}</div></div>
<p class="napomena">PIR u poslednjih 5 utakmica. Na listama su igrači sa bar 4 utakmice i 15 minuta po meču.</p>
<div class="naslov-sekcije"><h2>Svi igrači</h2><span class="napomena">klik na naslov kolone sortira</span></div>
<div class="sekcija skrol" style="margin-top:0"><table class="tab sort"><thead><tr>
<th class="l" data-k="t">Igrač</th><th class="l" data-k="t">Tim</th><th class="l" data-k="t">Poz</th>
<th data-k="n">Min (5)</th><th data-k="n">Poeni (5)</th><th data-k="n">PIR (5)</th><th data-k="n">PIR sezona</th>
<th data-k="n">Razlika</th></tr></thead><tbody>{tabela}</tbody></table>
<p class="napomena">(5) = prosek poslednjih 5 utakmica. Prikazani su igrači sa bar 3 utakmice.</p></div>"""
    snimi(SAJT / "forma.html", strana("Forma", telo, "", "forma.html", skripta=True))


OCENE = {"jaka": "Jaka", "srednja": "Srednja", "slaba": "Slaba", "nema": "–"}

# Brojke izmerene 30.10.2026. na 30.000+ učinaka (sezone 2024-25, 2025-26 i početak 2026-27)
ZASTO_ISPOD = """<details class="svi-propovi"><summary>Zašto je većina predloga "ispod"?</summary>
<div class="sekcija" style="margin-top:8px">
<p style="margin:0 0 8px"><b>Igrači češće daju ispod svog proseka nego preko.</b> Prosek dižu retke velike
utakmice: igrač sa prosekom 12 poena često daje 9, 10, 11, a povremeno 22. Na liniji jednakoj proseku igrača
"preko" prolazi samo u 44-48% utakmica (kod trojki i asistencija 43-46%).</p>
<p style="margin:0 0 8px"><b>Model nije pristrasan.</b> Na liniji za koju model kaže 50/50, igrači su je u
prethodne dve i ovoj sezoni prešli u 49-51% slučajeva, u svim kategorijama.</p>
<p style="margin:0"><b>Kladionice često postavljaju linije visoko</b>, jer većina igrača voli da igra "preko".
Kad je linija iznad one koju model smatra fer, predlog je "ispod". Da li je to prava prednost ili kladionica
zna nešto više, pokazuje tabela "Kako je model prošao".</p></div></details>"""


def top_predlozi(rez, n=10, po_igracu=2):
    """Najbolji predlozi kola: bez sumnjivih, najviše 2 po igraču."""
    izabrani, broj_po_igracu = [], {}
    for r in rez:  # već sortirano po EV
        if r["ev"] <= 0 or r["sumnjivo"] or broj_po_igracu.get(r["igrac_id"], 0) >= po_igracu:
            continue
        izabrani.append(r)
        broj_po_igracu[r["igrac_id"]] = broj_po_igracu.get(r["igrac_id"], 0) + 1
        if len(izabrani) == n:
            break
    return izabrani


def tiket_dana(rez, najvise=3):
    """Do 3 predloga sa najvećom procenjenom šansom za prvi naredni dan sa utakmicama. Samo predlozi sa
    prednošću, bez ⚠ i bez upitnih igrača; jedan po igraču, prvo iz različitih utakmica."""
    sada = datetime.now()
    buduci = [r for r in rez if datetime.strptime(r["datum"], "%Y-%m-%d %H:%M") > sada]
    if not buduci:
        return None
    dan = min(r["datum"][:10] for r in buduci)
    kandidati = sorted((r for r in buduci if r["datum"][:10] == dan and r["ev"] > 0
                        and not r["sumnjivo"] and not r["upitan"]), key=lambda r: -r["p_model"])
    izabrani = []
    for razliciti_mecevi in (True, False):
        for r in kandidati:
            if len(izabrani) == najvise:
                break
            if r in izabrani or any(x["igrac_id"] == r["igrac_id"] for x in izabrani):
                continue
            if razliciti_mecevi and any(x["sifra_utakmice"] == r["sifra_utakmice"] for x in izabrani):
                continue
            izabrani.append(r)
    return {"dan": dan, "nogice": izabrani} if izabrani else None


def sacuvaj_tiket(tiket):
    """Tiket se menja dok nijedna njegova utakmica nije počela; posle je zaključan."""
    tiketi = json.loads(TIKETI.read_text(encoding="utf-8")) if TIKETI.exists() else {}
    if tiket:
        stari = tiketi.get(tiket["dan"])
        sada = datetime.now()
        zakljucan = stari and any(datetime.strptime(n["datum"], "%Y-%m-%d %H:%M") <= sada for n in stari["nogice"])
        if not zakljucan:
            nogice = [{"kljuc": kljuc_predloga(r), "igrac_id": r["igrac_id"], "tim": r["tim"], "sezona": r["sezona"],
                       "sifra_utakmice": r["sifra_utakmice"], "datum": r["datum"], "tip": r["tip"],
                       "linija": r["linija"], "strana": r["strana"], "kvota": r["kvota"],
                       "p_model": round(r["p_model"], 4)} for r in tiket["nogice"]]
            kvota, sansa = 1.0, 1.0
            for x in nogice:
                kvota *= x["kvota"]
                sansa *= x["p_model"]
            tiketi[tiket["dan"]] = {"nogice": nogice, "kvota": round(kvota, 2), "sansa": round(sansa, 4),
                                    "sacuvano": sada.strftime("%Y-%m-%d %H:%M")}
    TIKETI.parent.mkdir(parents=True, exist_ok=True)
    TIKETI.write_text(json.dumps(tiketi, ensure_ascii=False, indent=1), encoding="utf-8")
    return tiketi


def ishodi_tiketa(k, tiketi, utakmice):
    """Odigrani tiketi: prošao ako su prošle sve nogice; nogica igrača koji nije igrao se izbacuje."""
    odigrane = {(u["sezona"], u["sifra_utakmice"]) for u in utakmice if u["odigrana"]}
    redovi = {(r["sezona"], r["sifra_utakmice"], r["igrac_id"]): r for r in k["statistika"] if r["igrao"]}
    ishodi = []
    for dan, t in sorted(tiketi.items(), reverse=True):
        if not all((n["sezona"], n["sifra_utakmice"]) in odigrane for n in t["nogice"]):
            continue
        nogice, kvota = [], 1.0
        for n in t["nogice"]:
            r = redovi.get((n["sezona"], n["sifra_utakmice"], n["igrac_id"]))
            if not r:
                continue
            stvarno = M.vrednost(r, n["tip"])
            nogice.append({**n, "stvarno": stvarno, "prosao": (stvarno > n["linija"]) == (n["strana"] == "preko")})
            kvota *= n["kvota"]
        if nogice:
            prosao = all(n["prosao"] for n in nogice)
            ishodi.append({"dan": dan, "nogice": nogice, "kvota": kvota, "sansa": t["sansa"], "prosao": prosao,
                           "dobit": kvota - 1 if prosao else -1.0})
    return ishodi


def kljuc_predloga(r):
    return f'{r["sezona"]}-{r["sifra_utakmice"]}-{r["igrac_id"]}-{r["tip"]}'


def sacuvaj_predloge(rez, top):
    """Upisuje predloge za utakmice koje još nisu počele. Posle početka utakmice se više ne menjaju,
    pa se posle mogu pošteno proveriti (podaci/kvote/predlozi.json, čuva ga workflow)."""
    predlozi = json.loads(PREDLOZI.read_text(encoding="utf-8")) if PREDLOZI.exists() else {}
    sada = datetime.now()
    top_kljucevi = {kljuc_predloga(r) for r in top}
    for r in rez:
        if datetime.strptime(r["datum"], "%Y-%m-%d %H:%M") <= sada:
            continue
        predlozi[kljuc_predloga(r)] = {
            "igrac_id": r["igrac_id"], "tim": r["tim"], "protivnik": r["protivnik"], "sezona": r["sezona"],
            "sifra_utakmice": r["sifra_utakmice"], "datum": r["datum"], "tip": r["tip"], "linija": r["linija"],
            "strana": r["strana"], "kvota": r["kvota"], "p_model": round(r["p_model"], 4),
            "p_kladionica": round(r["p_kladionica"], 4), "ev": round(r["ev"], 4), "ocena": r["ocena"],
            "top": kljuc_predloga(r) in top_kljucevi, "sacuvano": sada.strftime("%Y-%m-%d %H:%M")}
    PREDLOZI.parent.mkdir(parents=True, exist_ok=True)
    PREDLOZI.write_text(json.dumps(predlozi, ensure_ascii=False, indent=0), encoding="utf-8")
    return predlozi


def ishodi_predloga(k, predlozi, utakmice):
    """Za predloge iz odigranih utakmica: prošao / nije prošao / igrač nije igrao (ne računa se)."""
    odigrane = {(u["sezona"], u["sifra_utakmice"]) for u in utakmice if u["odigrana"]}
    redovi = {(r["sezona"], r["sifra_utakmice"], r["igrac_id"]): r for r in k["statistika"] if r["igrao"]}
    ishodi = []
    for p in predlozi.values():
        if (p["sezona"], p["sifra_utakmice"]) not in odigrane or p["ocena"] == "nema":
            continue
        r = redovi.get((p["sezona"], p["sifra_utakmice"], p["igrac_id"]))
        if not r:
            continue  # nije igrao: kladionica vraća ulog
        stvarno = M.vrednost(r, p["tip"])
        prosao = (stvarno > p["linija"]) == (p["strana"] == "preko")
        ishodi.append({**p, "stvarno": stvarno, "prosao": prosao, "dobit": p["kvota"] - 1 if prosao else -1.0})
    return sorted(ishodi, key=lambda x: (x["datum"], -x["ev"]), reverse=True)


def sekcija_odsutnih(k, rez):
    """Po utakmici: ko ne igra (tabela povreda) i kome model zbog toga daje najviše (poeni, ili druga kategorija)."""
    naziv = lambda t: k["timovi"].get(t, t)
    ime = lambda i: A.lepo_ime((k["igraci"].get(i) or {}).get("ime"))
    mecevi = {}
    for r in rez:
        dom, gost = (r["tim"], r["protivnik"]) if r["kod_kuce"] else (r["protivnik"], r["tim"])
        mecevi.setdefault(r["sifra_utakmice"], (r["datum"], dom, gost))
    # Dobitak po igraču: prednost dajemo poenima, inače najveći dobitak u bilo kojoj kategoriji
    dobitak = {}
    for r in rez:
        if not r["saigraci"]:
            continue
        d = r["koraci"]["saigraci"]
        stari = dobitak.get(r["igrac_id"])
        if not stari or (r["tip"] == "poeni" and stari["tip"] != "poeni") or (
                stari["tip"] != "poeni" and d > stari["d"]):
            dobitak[r["igrac_id"]] = {"tip": r["tip"], "d": d, "tim": r["tim"],
                                      "dm": r["minuti"] - r["minuti_bez_saigraca"]}
    kartice = []
    for s, (datum, dom, gost) in sorted(mecevi.items(), key=lambda x: x[1][0]):
        odsutni = [(t, i, p) for t in (dom, gost) for i, p in A.POVREDE.items()
                   if k["poslednji_tim"].get(i) == t and p.get("klasa") in ("st-ne", "st-up")]
        if not odsutni:
            continue
        spisak = "".join(
            f'<div class="st"><b>{e(naziv(t))}:</b> ' + ", ".join(
                f'{e(ime(i))}{" (upitan)" if p["klasa"] == "st-up" else ""}' for tt, i, p in odsutni if tt == t)
            + "</div>" for t in (dom, gost) if any(tt == t for tt, _, _ in odsutni))
        korisnici = sorted(((v["d"], i, v) for i, v in dobitak.items() if v["tim"] in (dom, gost) and v["d"] >= 0.2),
                           reverse=True)[:4]
        dobijaju = (" · ".join(
            f'<a href="igrac/{i}.html">{e(ime(i))}</a> <b class="p">+{broj(d)}</b> '
            f'{"p" if v["tip"] == "poeni" else M.NAZIV_TIPA[v["tip"]].lower()}'
            + (f' <span class="napomena">(+{broj(v["dm"])} min)</span>' if v["dm"] >= 0.5 else "")
            for d, i, v in korisnici) or '<span class="napomena">bez većeg uticaja (ili su već duže van)</span>')
        kartice.append(f'<div class="mec-red"><div class="d">{datum[11:16]}</div>'
                       f'<div class="t">{e(naziv(dom))} – {e(naziv(gost))}</div>'
                       f'<div class="st" style="margin-top:6px;color:var(--muted)">Ne igraju:</div>{spisak}'
                       f'<div class="st" style="margin-top:6px"><b>Najviše dobijaju:</b> {dobijaju}</div></div>')
    if not kartice:
        return ""
    return f"""<div class="naslov-sekcije"><h2>Ko ne igra i ko dobija</h2></div>
<div class="mecevi">{''.join(kartice)}</div>
<p class="napomena">Odsutni iz tabele povreda. "Dobijaju" = koliko model dodaje igraču zbog odsustva saigrača
(izmereno na ranijim utakmicama: oslobođeni minuti i šutevi se razliju na više igrača, pa su brojke umerene).</p>"""


def sekcija_tiketa(k, tiketi, utakmice):
    """Tiket dana: poslednji tiket čije utakmice još nisu sve odigrane."""
    naziv = lambda t: k["timovi"].get(t, t)
    odigrane = {(u["sezona"], u["sifra_utakmice"]) for u in utakmice if u["odigrana"]}
    aktivni = [d for d, t in tiketi.items()
               if not all((n["sezona"], n["sifra_utakmice"]) in odigrane for n in t["nogice"])]
    if not aktivni:
        return ""
    dan = max(aktivni)
    t = tiketi[dan]
    redovi = "".join(
        f'<tr><td class="l"><a class="ime" href="igrac/{n["igrac_id"]}.html">'
        f'{e(A.lepo_ime((k["igraci"].get(n["igrac_id"]) or {}).get("ime")))}</a>'
        f'<br><span class="napomena">{e(naziv(n["tim"]))} · {n["datum"][11:16]}</span></td>'
        f'<td class="l">{M.NAZIV_TIPA[n["tip"]]}</td>'
        f'<td class="l"><span class="strana {n["strana"]}">{n["strana"]}</span> {broj(n["linija"])}</td>'
        f'<td>{broj(n["kvota"], 2)}</td><td><b>{procenat(n["p_model"])}</b></td></tr>' for n in t["nogice"])
    zakljucan = any(datetime.strptime(n["datum"], "%Y-%m-%d %H:%M") <= datetime.now() for n in t["nogice"])
    return f"""<div class="tiket"><div class="tiket-glava"><h2>Tiket dana · {datum_srb(dan)}</h2>
<span class="napomena">{'zaključan (utakmice su počele)' if zakljucan else 'menja se do početka prve utakmice'}</span></div>
<div class="skrol"><table class="tab"><thead><tr><th class="l">Igrač</th><th class="l">Kategorija</th>
<th class="l">Predlog</th><th>Kvota</th><th>Procena</th></tr></thead><tbody>{redovi}</tbody></table></div>
<div class="tiket-zbir"><span>Ukupna kvota <b>{broj(t['kvota'], 2)}</b></span>
<span>Procena da prođe ceo tiket <b>{procenat(t['sansa'])}</b></span></div>
<p class="napomena" style="margin:8px 0 0">Predlozi sa najvećom procenjenom šansom za ovaj dan (samo oni sa
prednošću po modelu, bez ⚠ i upitnih igrača, po jedan po igraču, iz različitih utakmica kad god je moguće).
Tiket prolazi samo ako prođu svi predlozi, pa je šansa manja od svakog pojedinačnog.</p></div>"""


def sekcija_rezultata(k, ishodi, ishodi_t=()):
    naziv = lambda t: k["timovi"].get(t, t)
    if not ishodi:
        return """<div class="sekcija"><h2>Kako je model prošao</h2><p style="margin:0">Praćenje je počelo
30.10.2026. Prvi rezultati se pojavljuju posle prvog odigranog kola sa sačuvanim predlozima.</p></div>"""
    grupe = [("Top 10 predloga", [x for x in ishodi if x["top"]]),
             ("Jaki", [x for x in ishodi if x["ocena"] == "jaka"]),
             ("Srednji", [x for x in ishodi if x["ocena"] == "srednja"]),
             ("Slabi", [x for x in ishodi if x["ocena"] == "slaba"]),
             ("Svi sa prednošću", ishodi)]
    red = []
    for ime, g in grupe:
        if not g:
            continue
        n, pogodjeno, dobit = len(g), sum(x["prosao"] for x in g), sum(x["dobit"] for x in g)
        ocek = sum(x["p_kladionica"] for x in g) / n
        red.append(f'<tr><td class="l"><b>{ime}</b></td><td>{n}</td><td>{pogodjeno}</td>'
                   f'<td><b>{procenat(pogodjeno / n)}</b></td><td>{procenat(ocek)}</td>'
                   f'<td class="{"p" if dobit > 0 else "i"}">{"+" if dobit > 0 else ""}{broj(dobit, 1)}</td>'
                   f'<td>{"+" if dobit > 0 else ""}{broj(dobit / n * 100, 0)}%</td></tr>')
    if ishodi_t:
        n, pogodjeno, dobit = len(ishodi_t), sum(x["prosao"] for x in ishodi_t), sum(x["dobit"] for x in ishodi_t)
        ocek = sum(x["sansa"] for x in ishodi_t) / n
        red.insert(0, f'<tr><td class="l"><b>Tiketi dana</b></td><td>{n}</td><td>{pogodjeno}</td>'
                      f'<td><b>{procenat(pogodjeno / n)}</b></td><td>{procenat(ocek)} (model)</td>'
                      f'<td class="{"p" if dobit > 0 else "i"}">{"+" if dobit > 0 else ""}{broj(dobit, 1)}</td>'
                      f'<td>{"+" if dobit > 0 else ""}{broj(dobit / n * 100, 0)}%</td></tr>')
    poslednji = [x for x in ishodi if x["top"]][:10]
    lista = "".join(
        f'<tr><td class="l">{datum_srb(x["datum"])}</td><td class="l"><a href="igrac/{x["igrac_id"]}.html">'
        f'{e(A.lepo_ime((k["igraci"].get(x["igrac_id"]) or {}).get("ime")))}</a> '
        f'<span class="napomena">{e(naziv(x["tim"]))}</span></td><td class="l">{M.NAZIV_TIPA[x["tip"]]}</td>'
        f'<td class="l"><span class="strana {x["strana"]}">{x["strana"]}</span> {broj(x["linija"])}</td>'
        f'<td>{broj(x["kvota"], 2)}</td><td><b>{broj(x["stvarno"], 0)}</b></td>'
        f'<td class="{"p" if x["prosao"] else "i"}">{"✔" if x["prosao"] else "✘"}</td></tr>' for x in poslednji)
    return f"""<div class="sekcija skrol"><h2>Kako je model prošao</h2>
<table class="tab"><thead><tr><th class="l"></th><th>Predloga</th><th>Prošlo</th><th>Uspešnost</th>
<th>Kladionica očekuje</th><th>Dobit (ulog 1)</th><th>Povraćaj</th></tr></thead><tbody>{''.join(red)}</tbody></table>
<p class="napomena">Predlozi se zaključavaju pred početak utakmice i posle se ne menjaju. <b>Kladionica očekuje</b> =
koliko bi prošlo da su kvote bez marže tačne. <b>Dobit</b> = zbir da je na svaki predlog uložena 1 jedinica po
ponuđenoj kvoti. Ako igrač nije igrao, predlog se ne računa. Malo predloga = rezultat je uglavnom sreća.</p>
{f'<h2 style="margin-top:16px">Poslednji top predlozi</h2><table class="tab"><thead><tr><th class="l">Datum</th><th class="l">Igrač</th><th class="l">Kategorija</th><th class="l">Predlog</th><th>Kvota</th><th>Stvarno</th><th></th></tr></thead><tbody>{lista}</tbody></table>' if lista else ''}
</div>"""


def stranica_propovi(k, utakmice):
    """Propovi kola: linije sa superbet.rs + procena modela (model.py), rang po očekivanom povraćaju."""
    naziv = lambda t: k["timovi"].get(t, t)
    kv = json.loads(KVOTE.read_text(encoding="utf-8")) if KVOTE.exists() else {}
    rez = M.proceni(kv.get("propovi", []), k["statistika"], k["igraci"], k["sezona"], utakmice, A.POVREDE)
    MN = {"Guard": "bekovima", "Forward": "krilima", "Center": "centrima"}

    def zasto(r):
        """'sezona 3,5 → očekivano 2,7: faktor −0,5 · faktor −0,2 ...' (faktori poređani po uticaju)."""
        znak = lambda x: f"{'+' if x >= 0 else '−'}{broj(abs(x))}"
        kor = r["koraci"]
        faktori = []  # (uticaj, tekst)
        faktori.append((kor["ucinak"], f"učinak po minutu u poslednjih 5 {znak(kor['ucinak'])}"))
        faktori.append((kor["minuti"], f"minuti u poslednjih 5: {broj(r['minuti_bez_saigraca'])} "
                                       f"(sezona {broj(r['min_sezona'])}) {znak(kor['minuti'])}"))
        if r["saigraci"]:
            imena = ", ".join(
                f"{A.lepo_ime((k['igraci'].get(y) or {}).get('ime'))} {'ne igra' if q >= 1 else 'upitan'}"
                + (" (već u formi)" if dm is None else "") for y, q, dm in r["saigraci"])
            faktori.append((max(abs(kor["saigraci"]), 0.051), f"{imena} {znak(kor['saigraci'])}"))
        raz = r["ocekivana_razlika"] or 0
        faktori.append((kor["razlika"], f"očekivana razlika {broj(abs(raz), 0)} poena "
                                        f"({'favorit' if raz > 0 else 'autsajder'}) {znak(kor['razlika'])}"))
        faktori.append((kor["protivnik"], f"{naziv(r['protivnik'])} dozvoljava {MN.get(r['pozicija'], 'igračima')} "
                                          f"{'više' if r['f_prot'] > 1 else 'manje'} od proseka {znak(kor['protivnik'])}"))
        faktori.append((kor["dom"], f"{'kod kuće' if r['kod_kuce'] else 'u gostima'} {znak(kor['dom'])}"))
        bitni = [t for u, t in sorted(faktori, key=lambda f: -abs(f[0])) if abs(u) >= 0.05]
        delovi = [f"sezona {broj(r['sezona_prosek'])} → očekivano {broj(r['ocekivano'])}"
                  + (": " + " · ".join(bitni) if bitni else "")]
        if r["sumnjivo"]:
            delovi.append("⚠ linija je daleko od proseka: kladionica možda zna nešto (uloga, povrede), proveri vesti")
        if r["malo_podataka"]:
            delovi.append("malo utakmica ove sezone")
        if r["upitan"]:
            delovi.append("UPITAN za meč")
        return " · ".join(delovi)

    top = top_predlozi(rez)
    predlozi = sacuvaj_predloge(rez, top)
    tiketi = sacuvaj_tiket(tiket_dana(rez))
    ishodi_t = ishodi_tiketa(k, tiketi, utakmice)
    rezultati = sekcija_rezultata(k, ishodi_predloga(k, predlozi, utakmice), ishodi_t)
    tiket_html = sekcija_tiketa(k, tiketi, utakmice)

    mecevi = {}

    def red_propa(r, sa_filterom=True):
        dom, gost = (r["tim"], r["protivnik"]) if r["kod_kuce"] else (r["protivnik"], r["tim"])
        mecevi[r["sifra_utakmice"]] = (r["datum"], f"{naziv(dom)} – {naziv(gost)}")
        ime = A.lepo_ime((k["igraci"].get(r["igrac_id"]) or {}).get("ime"))
        podaci = (f' data-mec="{r["sifra_utakmice"]}" data-tip="{r["tip"]}" data-ocena="{r["ocena"]}"'
                  if sa_filterom else "")
        return (
            f'<tr{podaci}>'
            f'<td class="l zasto"><a class="ime" href="igrac/{r["igrac_id"]}.html">{e(ime)}</a>'
            f'{A.bedz(r["igrac_id"])}<small>{e(zasto(r))}</small></td>'
            f'<td class="l">{e(naziv(r["tim"]))}<br><span class="napomena">{"vs" if r["kod_kuce"] else "@"} '
            f'{e(naziv(r["protivnik"]))}</span></td>'
            f'<td class="l">{M.NAZIV_TIPA[r["tip"]]}</td>'
            f'<td class="l"><span class="strana {r["strana"]}">{r["strana"]}</span> {broj(r["linija"])}</td>'
            f'<td data-v="{r["kvota"]}">{broj(r["kvota"], 2)}</td>'
            f'<td data-v="{r["p_model"]:.4f}"><b>{procenat(r["p_model"])}</b></td>'
            f'<td data-v="{r["p_kladionica"]:.4f}">{procenat(r["p_kladionica"])}</td>'
            f'<td data-v="{r["ev"]:.4f}"><span class="ocena o-{r["ocena"]}">{OCENE[r["ocena"]]}</span></td>'
            f'<td data-v="{r["presao"] / max(r["od"], 1):.3f}">{r["presao"]}/{r["od"]}</td></tr>')

    zaglavlje = """<thead><tr><th class="l">Igrač i zašto</th><th class="l">Tim</th><th class="l" data-k="t">Kategorija</th>
<th class="l">Predlog</th><th data-k="n">Kvota</th><th data-k="n">Procena</th><th data-k="n">Kladionica</th>
<th data-k="n">Ocena</th><th data-k="n">Posl. 10</th></tr></thead>"""
    redovi_top = "".join(red_propa(r, False) for r in top)
    redovi = [red_propa(r) for r in rez]

    upozorenje = ('<div class="upozorenje"><span class="g18">18+</span><div>Ovo je statistička analiza, '
                  '<b>ne savet za klađenje</b>. Klađenje nosi rizik gubitka novca. Igrajte odgovorno.</div></div>')
    if not redovi:
        telo = f"""<h1>Propovi kola</h1>{upozorenje}
<div class="sekcija"><p style="margin:0">Linije za naredno kolo još nisu dostupne. Kvote se preuzimaju na dan
utakmice i dan pre (ujutru i popodne).</p></div>
{rezultati}"""
    else:
        opcije_meca = "".join(f'<option value="{s}">{e(m)}</option>'
                              for s, (d, m) in sorted(mecevi.items(), key=lambda x: x[1][0]))
        tipovi = sorted({r["tip"] for r in rez}, key=list(M.KOLONE).index)
        opcije_tipa = "".join(f'<option value="{t}">{M.NAZIV_TIPA[t]}</option>' for t in tipovi)
        broj_ocena = {o: sum(r["ocena"] == o for r in rez) for o in OCENE}
        telo = f"""<h1>Propovi kola</h1>
<p class="sub">Linije i kvote kladionica · preuzeto {e(kv.get('preuzeto', ''))} ·
{len(redovi)} propova · jakih {broj_ocena['jaka']}, srednjih {broj_ocena['srednja']}</p>
{upozorenje}
{tiket_html}
<div class="naslov-sekcije"><h2>Top 10 predloga</h2></div>
<div class="sekcija skrol" style="margin-top:0">{'<table class="tab">' + zaglavlje + '<tbody>' + redovi_top + '</tbody></table>'
                                                 if redovi_top else '<p style="margin:0">Model ovog puta ne vidi nijedan predlog sa prednošću.</p>'}</div>
{sekcija_odsutnih(k, rez)}
{ZASTO_ISPOD}
{rezultati}
<details class="svi-propovi"><summary>Prikaži sve propove ({len(redovi)})</summary>
<div class="filteri" id="filter-p" style="margin-top:12px">
  <select id="p-mec"><option value="">Sve utakmice</option>{opcije_meca}</select>
  <select id="p-tip"><option value="">Sve kategorije</option>{opcije_tipa}</select>
  <select id="p-oc"><option value="">Sve ocene</option><option value="jaka">Jaka</option>
    <option value="srednja">Srednja i jača</option></select>
</div>
<div class="sekcija skrol"><table class="tab sort" id="propovi">{zaglavlje}<tbody>{''.join(redovi)}</tbody></table></div>
</details>
<p class="napomena"><b>Predlog</b> = strana (preko/ispod) koja po modelu više vredi.
<b>Procena</b> = verovatnoća da predlog prođe (30% model, 70% kladionica). <b>Kladionica</b> = verovatnoća iz
kvota, bez marže. <b>Ocena</b>: jaka / srednja / slaba prednost po modelu, "–" = bez prednosti.
<b>Posl. 10</b> = koliko puta u poslednjih 10 utakmica bi predlog prošao na ovoj liniji.
Top 10: najviše 2 predloga po igraču, bez linija označenih sa ⚠.</p>
<p class="napomena">Model: učinak po minutu i minuti iz poslednjih 5 utakmica (prošla sezona se ne koristi),
šta protivnik dozvoljava toj poziciji, kod kuće/u gostima, odsutni saigrači iz tabele
povreda i očekivana razlika u poenima (starteri sede kad je meč rešen). Sve je provereno na ranijim utakmicama.
⚠ stoji kod linija koje su daleko od proseka: tu kladionica verovatno zna nešto više. Model često bira "ispod":
igrače ne potcenjuje, pa razlog verovatno leži u tome što kladionice podižu linije jer se češće igra "preko".
Da li to zaista donosi prednost pokazuje tabela "Kako je model prošao".</p>"""
    filter_js = """<script>
(function(){var m=document.getElementById('p-mec');if(!m)return;var t=document.getElementById('p-tip'),
 v=document.getElementById('p-oc');function f(){document.querySelectorAll('#propovi tbody tr').forEach(function(r){
 var o=r.dataset.ocena,ok=(!m.value||r.dataset.mec===m.value)&&(!t.value||r.dataset.tip===t.value)&&
 (!v.value||(v.value==='jaka'?o==='jaka':(o==='jaka'||o==='srednja')));
 r.style.display=ok?'':'none';});}[m,t,v].forEach(function(x){x.addEventListener('change',f);});})();
</script>"""
    snimi(SAJT / "propovi.html", strana("Propovi kola", telo, "", "propovi.html", skripta=True, dodatak=filter_js))


def naredno_kolo_igraci(k):
    """Kartice igrača za svaki meč narednog kola (deo stranice Igrači)."""
    A.LINK_IGRACA = lambda i: f"igrac/{i}.html"
    naziv = lambda t: k["timovi"].get(t, t)
    skor, delovi = k["skor"], []
    for m in k["mecevi"]:
        dt = datetime.strptime(m["datum"], "%Y-%m-%d %H:%M")
        dom, gost, s = m["domacin"], m["gost"], m["sifra_utakmice"]
        delovi.append(f"""<details class="mec" id="mec-{s}"><summary>
<span class="mec-naslov">{e(naziv(dom))} – {e(naziv(gost))}</span>
<span class="mec-meta">{A.DANI[dt.weekday()]} {dt.strftime('%d.%m. u %H:%M')}</span></summary>
<div class="mec-telo">
{A.html_tim(dom, naziv(dom), skor, k['analize_po_mecu'][(s, dom)], naziv(gost), True)}
{A.html_tim(gost, naziv(gost), skor, k['analize_po_mecu'][(s, gost)], naziv(dom), False)}
</div></details>""")
    return (f'<div class="naslov-sekcije" id="naredno-kolo"><h2>Naredno kolo ({k["kolo"]}.): igrači po utakmicama</h2></div>'
            f'<p class="napomena">Klik na meč otvara kartice igrača: forma, kod kuće/u gostima, protiv protivnika.</p>'
            + "".join(delovi))


JS_OTVORI_MEC = """<script>
function otvoriMec(){var d=location.hash&&document.getElementById(location.hash.slice(1));
 if(d&&d.tagName==='DETAILS'){d.open=true;d.scrollIntoView();}}
otvoriMec();window.addEventListener('hashchange',otvoriMec);
</script>"""


def stranica_igraci(k, lista):
    naziv = lambda t: k["timovi"].get(t, t)
    timovi = sorted({r["tim"] for r in lista}, key=naziv)
    redovi = []
    for r in lista:
        z = r["z"]
        redovi.append(
            f'<tr data-ime="{e(r["ime"].lower())}" data-tim="{r["tim"]}" data-poz="{e(r["poz"])}">'
            f'<td class="l"><a href="igrac/{r["id"]}.html">{e(r["ime"])}</a>{A.bedz(r["id"])}</td>'
            f'<td class="l"><a href="tim/{r["tim"]}.html">{e(naziv(r["tim"]))}</a></td>'
            f'<td class="l">{e(r["poz"])}</td><td>{z["gp"]}</td>'
            f'<td data-v="{z["min"]:.2f}">{broj(z["min"])}</td>'
            f'<td data-v="{z["pts"]:.2f}">{broj(z["pts"])}</td>'
            f'<td data-v="{z["reb"]:.2f}">{broj(z["reb"])}</td>'
            f'<td data-v="{z["ast"]:.2f}">{broj(z["ast"])}</td>'
            f'<td data-v="{z["pir"]:.2f}">{broj(z["pir"])}</td>'
            f'<td data-v="{z["ts"] or 0:.3f}">{procenat(z["ts"])}</td></tr>')
    telo = f"""<h1>Igrači</h1>
<p class="sub">Evroliga {oznaka_sezone(k['sezona'])} · {len(lista)} igrača · klik na naslov kolone sortira</p>
<div class="filteri" id="filter">
  <input id="trazi" placeholder="Traži igrača..." autocomplete="off">
  <select id="tim"><option value="">Svi timovi</option>{''.join(
        f'<option value="{t}">{e(naziv(t))}</option>' for t in timovi)}</select>
  <select id="poz"><option value="">Sve pozicije</option>
    <option>Bek</option><option>Krilo</option><option>Centar</option></select>
</div>
<div class="sekcija skrol"><table class="tab sort" id="igraci"><thead><tr>
<th class="l" data-k="t">Igrač</th><th class="l" data-k="t">Tim</th><th class="l" data-k="t">Poz</th>
<th data-k="n">UT</th><th data-k="n">Min</th><th data-k="n">Poeni</th><th data-k="n">Skok</th>
<th data-k="n">Asist</th><th data-k="n">PIR</th><th data-k="n">TS%</th></tr></thead>
<tbody>{''.join(redovi)}</tbody></table></div>
{naredno_kolo_igraci(k)}"""
    snimi(SAJT / "igraci.html", strana("Igrači", telo, "", "igraci.html", skripta=True,
                                       dodatak=JS_OTVORI_MEC))


def tabela_lige(k, utakmice):
    t = {}
    for u in utakmice:
        if not u["odigrana"] or u["faza"] != "RS":
            continue
        for tim, dao, primio in ((u["domacin"], u["poeni_domacin"], u["poeni_gost"]),
                                 (u["gost"], u["poeni_gost"], u["poeni_domacin"])):
            x = t.setdefault(tim, {"ut": 0, "p": 0, "i": 0, "dao": 0, "primio": 0})
            x["ut"] += 1
            x["p" if dao > primio else "i"] += 1
            x["dao"] += dao
            x["primio"] += primio
    return sorted(t.items(), key=lambda kv: (-kv[1]["p"], -(kv[1]["dao"] - kv[1]["primio"])))


def stranica_timovi(k, tabela):
    naziv = lambda t: k["timovi"].get(t, t)
    redovi = "".join(
        f'<tr><td>{i}</td><td class="l"><a href="tim/{t}.html">{e(naziv(t))}</a></td>'
        f'<td>{x["ut"]}</td><td>{x["p"]}</td><td>{x["i"]}</td>'
        f'<td>{broj(x["dao"] / x["ut"])}</td><td>{broj(x["primio"] / x["ut"])}</td>'
        f'<td>{"+" if x["dao"] >= x["primio"] else ""}{x["dao"] - x["primio"]}</td></tr>'
        for i, (t, x) in enumerate(tabela, start=1))
    telo = f"""<h1>Timovi</h1>
<p class="sub">Tabela regularnog dela Evrolige {oznaka_sezone(k['sezona'])}</p>
<div class="sekcija skrol"><table class="tab"><thead><tr><th>#</th><th class="l">Tim</th><th>UT</th>
<th>P</th><th>I</th><th>Dao</th><th>Primio</th><th>+/-</th></tr></thead><tbody>{redovi}</tbody></table>
<p style="font-size:12.5px;color:var(--muted)">P = pobede, I = porazi, Dao/Primio = prosek poena po
utakmici. Redosled: pobede, pa koš-razlika (zvanična tabela može se razlikovati kod istog broja
pobeda zbog međusobnih duela).</p></div>"""
    snimi(SAJT / "timovi.html", strana("Timovi", telo, "", "timovi.html"))


def stranica_tim(k, tim, lista, utakmice, tabela):
    naziv = lambda t: k["timovi"].get(t, t)
    poz_tabela = next((i for i, (t, _) in enumerate(tabela, start=1) if t == tim), None)
    x = dict(tabela).get(tim, {"p": 0, "i": 0})

    igraci = sorted([r for r in lista if r["tim"] == tim], key=lambda r: -r["z"]["min"])
    red_ig = "".join(
        f'<tr><td class="l"><a href="../igrac/{r["id"]}.html">{e(r["ime"])}</a>{A.bedz(r["id"])}</td>'
        f'<td class="l">{e(r["poz"])}</td><td>{r["z"]["gp"]}</td><td>{broj(r["z"]["min"])}</td>'
        f'<td>{broj(r["z"]["pts"])}</td><td>{broj(r["z"]["reb"])}</td><td>{broj(r["z"]["ast"])}</td>'
        f'<td><b>{broj(r["z"]["pir"])}</b></td><td>{procenat(r["z"]["ts"])}</td></tr>' for r in igraci)

    red_ut = []
    for u in utakmice:
        if tim not in (u["domacin"], u["gost"]):
            continue
        kod_kuce = u["domacin"] == tim
        prot = u["gost"] if kod_kuce else u["domacin"]
        if u["odigrana"]:
            nas, njih = ((u["poeni_domacin"], u["poeni_gost"]) if kod_kuce
                         else (u["poeni_gost"], u["poeni_domacin"]))
            ishod = "P" if nas > njih else "I"
            rez = (f'<a href="../utakmica/{u["sezona"]}-{u["sifra_utakmice"]}.html">'
                   f'<span class="{ishod.lower()}">{ishod}</span> {nas}:{njih}</a>')
        else:
            rez = f'<span style="color:var(--muted)">{u["datum"][11:16]}</span>'
        red_ut.append(f'<tr><td>{u["kolo"]}</td><td class="l">{datum_srb(u["datum"])}</td>'
                      f'<td class="l">{"vs" if kod_kuce else "@"} '
                      f'<a href="{prot}.html">{e(naziv(prot))}</a></td><td class="l">{rez}</td></tr>')

    telo = f"""<h1>{e(naziv(tim))}</h1>
<p class="info">{x['p']}-{x['i']}{f' · {poz_tabela}. mesto' if poz_tabela else ''} · Evroliga {oznaka_sezone(k['sezona'])}</p>
<div class="sekcija skrol"><h2>Igrači</h2><table class="tab"><thead><tr><th class="l">Igrač</th>
<th class="l">Poz</th><th>UT</th><th>Min</th><th>Poeni</th><th>Skok</th><th>Asist</th><th>PIR</th>
<th>TS%</th></tr></thead><tbody>{red_ig}</tbody></table></div>
<div class="sekcija skrol"><h2>Rezultati i raspored</h2><table class="tab"><thead><tr><th>Kolo</th>
<th class="l">Datum</th><th class="l">Protivnik</th><th class="l">Rezultat / vreme</th></tr></thead>
<tbody>{''.join(red_ut)}</tbody></table></div>"""
    snimi(SAJT / "tim" / f"{tim}.html", strana(naziv(tim), telo, "../", ""))


# ----------------------------- PAKET 1: POČETNA, LIDERI, BOX SCORE -----------------------------
def prosireno(redovi):
    """Proseci po utakmici za sve kategorije (za lidere i početnu)."""
    z = zbirno(redovi)
    n = z["gp"]
    s = lambda kl: sum(r[kl] or 0 for r in redovi)
    z.update({
        "stl": s("ukradene") / n, "blk": s("blokade") / n, "tov": s("izgubljene") / n,
        "p2m": s("sut2_pogodjeno"), "p2a": s("sut2_pokusano"),
        "p3m": s("sut3_pogodjeno"), "p3a": s("sut3_pokusano"),
        "ftm": s("slobodna_pogodjeno"), "fta": s("slobodna_pokusano"),
    })
    z["p2"] = z["p2m"] / z["p2a"] if z["p2a"] else None
    z["p3"] = z["p3m"] / z["p3a"] if z["p3a"] else None
    z["ft"] = z["ftm"] / z["fta"] if z["fta"] else None
    return z


def inicijali(ime):
    delovi = [d for d in ime.replace("-", " ").split() if d]
    return (delovi[0][0] + delovi[-1][0]).upper() if len(delovi) >= 2 else ime[:2].upper()


def kvalifikovani(lista, tabela):
    """Za liste lidera: igrač mora da je odigrao bar 60% utakmica svog tima."""
    ut_tima = {t: x["ut"] for t, x in tabela}
    return [r for r in lista
            if r["zp"]["gp"] >= math.ceil(0.6 * ut_tima.get(r["tim"], r["zp"]["gp"]))]


KATEGORIJE = [
    # (ključ, naslov, format, uslov za procente)
    ("pir", "Indeks (PIR)", "broj", None),
    ("pts", "Poeni", "broj", None),
    ("reb", "Skokovi", "broj", None),
    ("ast", "Asistencije", "broj", None),
    ("stl", "Ukradene lopte", "broj", None),
    ("blk", "Blokade", "broj", None),
    ("min", "Minuti", "broj", None),
    ("ts", "TS% (efikasnost šuta)", "proc", ("fga_pg", 6)),
    ("p3", "Šut za 3", "proc", ("p3a_pg", 2)),
    ("p2", "Šut za 2", "proc", ("p2a_pg", 3)),
    ("ft", "Slobodna bacanja", "proc", ("fta_pg", 1.5)),
]
USLOVI_OPIS = {"fga_pg": "šuta iz igre", "p3a_pg": "šuta za 3", "p2a_pg": "šuta za 2",
               "fta_pg": "slobodnih bacanja"}


def lideri(lista, kljuc, uslov=None, n=5):
    kandidati = []
    for r in lista:
        z = r["zp"]
        if z.get(kljuc) is None:
            continue
        if uslov:
            pokusaji = {"fga_pg": (z["p2a"] + z["p3a"]) / z["gp"], "p3a_pg": z["p3a"] / z["gp"],
                        "p2a_pg": z["p2a"] / z["gp"], "fta_pg": z["fta"] / z["gp"]}[uslov[0]]
            if pokusaji < uslov[1]:
                continue
        kandidati.append(r)
    return sorted(kandidati, key=lambda r: -r["zp"][kljuc])[:n]


def vrednost(z, kljuc, fmt):
    return procenat(z[kljuc]) if fmt == "proc" else broj(z[kljuc])


def mini_tabela(naslov, igraci, kljuc, fmt, koren="", link=None, sufiks=""):
    naziv_tima = lambda r: r.get("tim_naziv", r["tim"])
    redovi = "".join(
        f'<li><span class="ko"><a href="{koren}igrac/{r["id"]}.html">{e(r["ime"])}</a>{A.bedz(r["id"])} '
        f'<small>{e(naziv_tima(r))}</small></span><b>{vrednost(r["zp"], kljuc, fmt)}{sufiks}</b></li>'
        for r in igraci)
    vise = f'<a href="{link}">sve →</a>' if link else ""
    return f'<div class="mini"><h3>{e(naslov)}{vise}</h3><ol>{redovi}</ol></div>'


def poslednje_kolo(utakmice):
    """Kolo sa najnovijom odigranom utakmicom i sve njegove odigrane utakmice."""
    odigrane = [u for u in utakmice if u["odigrana"]]
    if not odigrane:
        return None, []
    kolo = max(odigrane, key=lambda u: u["datum"])["kolo"]
    return kolo, [u for u in odigrane if u["kolo"] == kolo]


def stranica_pocetna(k, lista, tabela, utakmice):
    naziv = lambda t: k["timovi"].get(t, t)
    kval = kvalifikovani(lista, tabela)

    # Podaci za pretragu (igrači i timovi), ugrađeni u stranicu
    podaci = [{"i": r["ime"], "o": f'{naziv(r["tim"])} · {r["poz"]}', "u": f'igrac/{r["id"]}.html'}
              for r in sorted(lista, key=lambda r: -r["zp"]["min"])]
    podaci += [{"i": naziv(t), "o": "Tim", "u": f"tim/{t}.html"} for t, _ in tabela]
    pretraga_js = """<script>
(function(){var P=%s,inp=document.getElementById('pretraga'),box=document.getElementById('rezultati'),sel=-1;
function norm(s){return s.toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g,'').replace(/đ/g,'dj');}
P.forEach(function(p){p.n=norm(p.i);});
function prikazi(){var q=norm(inp.value.trim());sel=-1;
 if(q.length<2){box.hidden=true;box.innerHTML='';return;}
 var r=P.filter(function(p){return q.split(' ').every(function(d){return p.n.indexOf(d)>-1;});}).slice(0,8);
 box.innerHTML=r.length?r.map(function(p){return '<a href="'+p.u+'">'+p.i+'<span>'+p.o+'</span></a>';}).join('')
   :'<a>Nema rezultata<span></span></a>';
 box.hidden=false;}
inp.addEventListener('input',prikazi);
inp.addEventListener('keydown',function(ev){var a=box.querySelectorAll('a[href]');if(!a.length)return;
 if(ev.key==='ArrowDown'||ev.key==='ArrowUp'){ev.preventDefault();sel=(sel+(ev.key==='ArrowDown'?1:-1)+a.length)%%a.length;
  a.forEach(function(x,i){x.classList.toggle('izabran',i===sel);});}
 if(ev.key==='Enter'){location.href=a[Math.max(sel,0)].getAttribute('href');}});
document.addEventListener('click',function(ev){if(!ev.target.closest('.pretraga'))box.hidden=true;});
})();</script>""" % json.dumps(podaci, ensure_ascii=False)

    # MVP poslednjeg kola = najveći PIR u odigranim utakmicama tog kola
    kolo, mecevi_kola = poslednje_kolo(utakmice)
    sifre = {u["sifra_utakmice"] for u in mecevi_kola}
    nastupi = [r for r in k["statistika"]
               if r["sezona"] == k["sezona"] and r["sifra_utakmice"] in sifre and r["igrao"]]
    mvp_html = ""
    if nastupi:
        m = max(nastupi, key=lambda r: (r["pir"] or 0, r["poeni"] or 0))
        ime = A.lepo_ime((k["igraci"].get(m["igrac_id"]) or {}).get("ime"))
        ishod, skor = rezultat(m)
        mvp_html = f"""<div class="mvp"><div class="krug" aria-hidden="true">{e(inicijali(ime))}</div>
<div><div class="oznaka">MVP {kolo}. kola</div>
<div class="ime"><a href="igrac/{m['igrac_id']}.html">{e(ime)}</a></div>
<div class="brojke"><b>{m['pir']}</b> PIR · <b>{m['poeni']}</b> poena · <b>{m['skokovi_ukupno']}</b> skokova ·
<b>{m['asistencije']}</b> asistencija<br>{e(naziv(m['tim']))} · utakmica
{e(naziv(m['u_domacin']))} – {e(naziv(m['protivnik'] if m['domacin'] else m['tim']))} · <a href="utakmica/{m['sezona']}-{m['sifra_utakmice']}.html">{'pobeda' if ishod == 'P' else 'poraz'} {skor}</a></div></div></div>"""

    # Lideri (mini)
    mini_lideri = "".join(mini_tabela(nas, lideri(kval, klj), klj, fmt, link="lideri.html")
                          for klj, nas, fmt, _ in KATEGORIJE[:4])

    # Hot vs Cold: poslednje 3 utakmice u odnosu na sezonu
    kandidati = [r for r in lista if r["zp"]["gp"] >= 5 and r["zp"]["min"] >= 15]
    for r in kandidati:
        r["p3pir"] = zbirno(k["po_sezona"][r["id"]][-3:])["pir"]
        r["razlika"] = r["p3pir"] - r["zp"]["pir"]

    def lista_forme(igraci, klasa, znak):
        return "<ol>" + "".join(
            f'<li><span class="ko"><a href="igrac/{r["id"]}.html">{e(r["ime"])}</a>{A.bedz(r["id"])} '
            f'<small>{e(naziv(r["tim"]))}</small></span>'
            f'<span>{broj(r["p3pir"])} <small class="napomena">(prosek {broj(r["zp"]["pir"])})</small> '
            f'<b class="{klasa}">{znak} {broj(abs(r["razlika"]))}</b></span></li>' for r in igraci) + "</ol>"
    vruci = sorted(kandidati, key=lambda r: -r["razlika"])[:5]
    hladni = sorted(kandidati, key=lambda r: r["razlika"])[:5]

    # Trake: poslednje kolo (rezultati) i naredno kolo (raspored)
    def kartica_rasporeda(u):
        dt = datetime.strptime(u["datum"], "%Y-%m-%d %H:%M")
        return (f'<a class="mec-k" href="igraci.html#mec-{u["sifra_utakmice"]}"><div class="d">{A.DANI[dt.weekday()]} '
                f'{dt.strftime("%d.%m. %H:%M")}</div><div class="r"><span>{e(naziv(u["domacin"]))}</span></div>'
                f'<div class="r"><span>{e(naziv(u["gost"]))}</span></div></a>')

    telo = f"""<div class="hero"><h1 class="naslov">{LOGO_SVG}{ZNAK}</h1>
<p class="sub" style="margin:0">Evroliga {oznaka_sezone(k['sezona'])} · brojke, forma i povrede pred svaki meč</p>
<div class="pretraga"><input id="pretraga" type="search" placeholder="Unesi ime igrača ili tima..."
autocomplete="off" aria-label="Pretraga igrača i timova"><div class="rezultati" id="rezultati" hidden></div></div></div>
{mvp_html}
<div class="naslov-sekcije"><h2>Naredno kolo ({k['kolo']}.)</h2><a href="utakmice.html">sve utakmice →</a></div>
<div class="traka">{''.join(kartica_rasporeda(u) for u in k['mecevi'])}</div>
{tabela_statusa(k, lista)}
<div class="naslov-sekcije"><h2>Rezultati {kolo}. kola</h2><a href="timovi.html">tabela →</a></div>
<div class="traka">{''.join(kartica_rezultata(k, u) for u in sorted(mecevi_kola, key=lambda u: u['datum']))}</div>
<div class="naslov-sekcije"><h2>Lideri sezone</h2><a href="lideri.html">svi lideri →</a></div>
<div class="mreza">{mini_lideri}</div>
<p class="napomena">Proseci po utakmici. Uslov: odigrano bar 60% utakmica svog tima.</p>
<div class="naslov-sekcije"><h2>Forma: poslednje 3 utakmice</h2><a href="forma.html">forma svih igrača →</a></div>
<div class="mreza">
<div class="mini"><h3>🔥 U usponu</h3>{lista_forme(vruci, 'up', '▲')}</div>
<div class="mini"><h3>❄️ U padu</h3>{lista_forme(hladni, 'down', '▼')}</div></div>
<p class="napomena">PIR u poslednje 3 utakmice u odnosu na sezonski prosek (bar 5 utakmica i 15 minuta po meču).</p>"""
    snimi(SAJT / "index.html", strana("Početna", telo, "", "index.html", dodatak=pretraga_js))


def tabela_statusa(k, lista):
    """Početna: svi igrači iz tabele povreda, prvo oni čiji tim igra u narednom kolu."""
    if not A.POVREDE:
        return ""
    naziv = lambda t: k["timovi"].get(t, t)
    po_id = {r["id"]: r for r in lista}
    igraju = {t for m in k["mecevi"] for t in (m["domacin"], m["gost"])}
    red = {"st-ne": 0, "st-up": 1, "st-vr": 2}
    stavke = sorted([(po_id[i], p) for i, p in A.POVREDE.items() if i in po_id],
                    key=lambda x: (x[0]["tim"] not in igraju, red.get(x[1]["klasa"], 3), naziv(x[0]["tim"])))
    redovi = "".join(
        f'<tr><td class="l"><a href="igrac/{r["id"]}.html">{e(r["ime"])}</a>{A.bedz(r["id"])}</td>'
        f'<td class="l"><a href="tim/{r["tim"]}.html">{e(naziv(r["tim"]))}</a></td>'
        f'<td class="l">{e(p.get("razlog") or "")}</td><td class="l">{e(p.get("povratak") or "")}</td>'
        f'<td class="l napomena">{e(p.get("azurirano") or "")}</td></tr>' for r, p in stavke)
    return f"""<div class="naslov-sekcije"><h2>Povrede i statusi</h2></div>
<div class="sekcija skrol" style="margin-top:0"><table class="tab"><thead><tr><th class="l">Igrač</th>
<th class="l">Tim</th><th class="l">Razlog</th><th class="l">Povratak</th><th class="l">Ažurirano</th></tr></thead>
<tbody>{redovi}</tbody></table></div>"""


def stranica_lideri(k, lista, tabela):
    kval = kvalifikovani(lista, tabela)
    blokovi = []
    for klj, nas, fmt, uslov in KATEGORIJE:
        nap = ""
        if uslov:
            nap = f'<p class="napomena" style="margin:6px 0 0">bar {broj(uslov[1])} {USLOVI_OPIS[uslov[0]]} po meču</p>'
        blokovi.append(mini_tabela(nas, lideri(kval, klj, uslov, n=10), klj, fmt)
                       .replace("</ol></div>", f"</ol>{nap}</div>"))
    telo = f"""<h1>Lideri sezone</h1>
<p class="sub">Evroliga {oznaka_sezone(k['sezona'])} · proseci po utakmici · top 10 u svakoj kategoriji</p>
<div class="mreza">{''.join(blokovi)}</div>
<p class="napomena">Uslov za sve liste: odigrano bar 60% utakmica svog tima. Za procente šuta važi i
minimalan broj pokušaja po meču (napisan ispod liste).</p>"""
    snimi(SAJT / "lideri.html", strana("Lideri", telo, "", "lideri.html"))


def stranica_utakmica(k, u):
    naziv = lambda t: k["timovi"].get(t, t)
    redovi = [r for r in k["statistika"]
              if r["sezona"] == u["sezona"] and r["sifra_utakmice"] == u["sifra_utakmice"]]
    dt = datetime.strptime(u["datum"], "%Y-%m-%d %H:%M")
    dom_pob = u["poeni_domacin"] > u["poeni_gost"]

    def tabela_tima(tim):
        igr = sorted([r for r in redovi if r["tim"] == tim],
                     key=lambda r: (-r["starter"], -(r["minuti"] or 0)))
        tr = []
        for r in igr:
            ime = A.lepo_ime((k["igraci"].get(r["igrac_id"]) or {}).get("ime"))
            link = (f'<a href="../igrac/{r["igrac_id"]}.html">{e(ime)}</a>'
                    if k["po_sezona"].get(r["igrac_id"]) else e(ime))
            if not r["igrao"]:
                tr.append(f'<tr><td class="l">{link}</td><td colspan="13" class="l napomena">nije igrao</td></tr>')
                continue
            pm = r["plus_minus"]
            tr.append(
                f'<tr><td class="l">{link}{" *" if r["starter"] else ""}</td><td>{broj(r["minuti"])}</td>'
                f'<td><b>{r["poeni"]}</b></td><td>{r["sut2_pogodjeno"]}/{r["sut2_pokusano"]}</td>'
                f'<td>{r["sut3_pogodjeno"]}/{r["sut3_pokusano"]}</td>'
                f'<td>{r["slobodna_pogodjeno"]}/{r["slobodna_pokusano"]}</td>'
                f'<td>{r["skokovi_napad"]}</td><td>{r["skokovi_odbrana"]}</td><td>{r["skokovi_ukupno"]}</td>'
                f'<td>{r["asistencije"]}</td><td>{r["ukradene"]}</td><td>{r["izgubljene"]}</td>'
                f'<td>{r["blokade"]}</td><td>{r["licne_greske"]}</td>'
                f'<td>{"" if pm is None else ("+" if pm > 0 else "") + str(pm)}</td><td><b>{r["pir"]}</b></td></tr>')
        igrali = [r for r in igr if r["igrao"]]
        s = lambda kl: sum(r[kl] or 0 for r in igrali)
        tr.append(f'<tr class="ukupno"><td class="l">Ukupno</td><td></td><td>{s("poeni")}</td>'
                  f'<td>{s("sut2_pogodjeno")}/{s("sut2_pokusano")}</td><td>{s("sut3_pogodjeno")}/{s("sut3_pokusano")}</td>'
                  f'<td>{s("slobodna_pogodjeno")}/{s("slobodna_pokusano")}</td><td>{s("skokovi_napad")}</td>'
                  f'<td>{s("skokovi_odbrana")}</td><td>{s("skokovi_ukupno")}</td><td>{s("asistencije")}</td>'
                  f'<td>{s("ukradene")}</td><td>{s("izgubljene")}</td><td>{s("blokade")}</td>'
                  f'<td>{s("licne_greske")}</td><td></td><td>{s("pir")}</td></tr>')
        return f"""<div class="sekcija skrol"><h2><a href="../tim/{tim}.html">{e(naziv(tim))}</a></h2>
<table class="tab"><thead><tr><th class="l">Igrač</th><th>Min</th><th>Poeni</th><th>2P</th><th>3P</th><th>SB</th>
<th>SkN</th><th>SkO</th><th>Sk</th><th>As</th><th>Uk</th><th>Izg</th><th>Bl</th><th>F</th><th>+/-</th><th>PIR</th>
</tr></thead><tbody>{''.join(tr)}</tbody></table></div>"""

    telo = f"""<p class="sub" style="text-align:center;margin:8px 0">{u['kolo']}. kolo · {A.DANI[dt.weekday()]}
{dt.strftime('%d.%m.%Y. u %H:%M')}</p>
<div class="hero box-glava">
<span class="tim-n {'pob' if dom_pob else 'por'}"><a href="../tim/{u['domacin']}.html">{e(naziv(u['domacin']))}</a></span>
<span class="skor"><span class="{'pob' if dom_pob else 'por'}">{u['poeni_domacin']}</span> :
<span class="{'por' if dom_pob else 'pob'}">{u['poeni_gost']}</span></span>
<span class="tim-n {'por' if dom_pob else 'pob'}"><a href="../tim/{u['gost']}.html">{e(naziv(u['gost']))}</a></span></div>
{tabela_tima(u['domacin'])}
{tabela_tima(u['gost'])}
<p class="napomena">* = starter · SB = slobodna bacanja · SkN/SkO = skokovi u napadu/odbrani · F = lične greške</p>"""
    snimi(SAJT / "utakmica" / f"{u['sezona']}-{u['sifra_utakmice']}.html",
          strana(f"{naziv(u['domacin'])} - {naziv(u['gost'])}", telo, "../", ""))


DRZAVE = {
    "USA": "SAD", "FRA": "Francuska", "SRB": "Srbija", "ESP": "Španija", "ITA": "Italija",
    "GER": "Nemačka", "LTU": "Litvanija", "GRE": "Grčka", "TUR": "Turska", "ISR": "Izrael",
    "CAN": "Kanada", "SEN": "Senegal", "SLO": "Slovenija", "NGR": "Nigerija", "LAT": "Letonija",
    "CRO": "Hrvatska", "BRA": "Brazil", "RUS": "Rusija", "MLI": "Mali", "MKD": "Severna Makedonija",
    "FIN": "Finska", "DOM": "Dominikanska Republika", "DEN": "Danska", "CZE": "Češka",
    "AUS": "Australija", "UKR": "Ukrajina", "UK": "Velika Britanija", "GBR": "Velika Britanija",
    "SWE": "Švedska", "POL": "Poljska", "HUN": "Mađarska", "GHA": "Gana", "GEO": "Gruzija",
    "EST": "Estonija", "CMR": "Kamerun", "BIH": "Bosna i Hercegovina", "ANG": "Angola",
    "ZAI": "DR Kongo", "COD": "DR Kongo", "SVK": "Slovačka", "SUI": "Švajcarska",
    "SSD": "Južni Sudan", "NZL": "Novi Zeland", "MNE": "Crna Gora", "LUX": "Luksemburg",
    "JAM": "Jamajka", "IVO": "Obala Slonovače", "CIV": "Obala Slonovače", "ISL": "Island",
    "IRL": "Irska", "GUI": "Gvineja", "GAB": "Gabon", "CPV": "Zelenortska Ostrva",
    "COL": "Kolumbija", "CHI": "Čile", "CHA": "Čad", "BUR": "Burkina Faso", "BUL": "Bugarska",
    "BEL": "Belgija", "BAH": "Bahami", "NED": "Holandija", "POR": "Portugalija", "AUT": "Austrija",
    "ARG": "Argentina", "PUR": "Portoriko", "ROU": "Rumunija", "MNG": "Mongolija",
}


def drzava(kod):
    kod = (kod or "").strip()
    return DRZAVE.get(kod, kod)


def napredna_statistika(k, lista, tabela):
    """USG% i +/- na 40 min za sve igrače sezone + rang na poziciji (među kvalifikovanim)."""
    # Zbir tima po utakmici (za USG%)
    tim_mec = {}
    for r in k["statistika"]:
        if r["sezona"] != k["sezona"] or not r["igrao"]:
            continue
        x = tim_mec.setdefault((r["sifra_utakmice"], r["tim"]), [0.0, 0.0, 0.0, 0.0])
        x[0] += (r["sut2_pokusano"] or 0) + (r["sut3_pokusano"] or 0)
        x[1] += r["slobodna_pokusano"] or 0
        x[2] += r["izgubljene"] or 0
        x[3] += r["minuti"] or 0
    for r in lista:
        ut = k["po_sezona"][r["id"]]
        min_ig = sum(u["minuti"] or 0 for u in ut)
        pos_ig = sum((u["sut2_pokusano"] or 0) + (u["sut3_pokusano"] or 0)
                     + 0.44 * (u["slobodna_pokusano"] or 0) + (u["izgubljene"] or 0) for u in ut)
        tm_min = tm_pos = 0.0
        for u in ut:
            t = tim_mec.get((u["sifra_utakmice"], u["tim"]))
            if t:
                tm_pos += t[0] + 0.44 * t[1] + t[2]
                tm_min += t[3]
        usg = 100 * pos_ig * (tm_min / 5) / (min_ig * tm_pos) if min_ig and tm_pos else None
        pm = [u for u in ut if u["plus_minus"] is not None]
        pm_min = sum(u["minuti"] or 0 for u in pm)
        pm40 = sum(u["plus_minus"] for u in pm) / pm_min * 40 if pm_min >= 20 else None
        r["adv"] = {"usg": usg, "pm40": pm40, "ts": r["zp"]["ts"], "efg": r["zp"]["efg"]}

    # Rang na poziciji: bar 60% utakmica tima i bar 10 minuta po meču
    kval = [r for r in kvalifikovani(lista, tabela) if r["zp"]["min"] >= 10]
    for kljuc in ("usg", "pm40", "ts", "efg"):
        for poz in {r["poz"] for r in kval}:
            grupa = sorted([r for r in kval if r["poz"] == poz and r["adv"][kljuc] is not None],
                           key=lambda r: -r["adv"][kljuc])
            for i, r in enumerate(grupa, start=1):
                r.setdefault("rang", {})[kljuc] = (i, len(grupa))


def split_red(naslov, ut):
    if not ut:
        return f'<tr><td class="l">{naslov}</td><td>0</td><td colspan="6" class="l napomena">nema utakmica</td></tr>'
    z = prosireno(ut)
    return (f'<tr><td class="l">{naslov}</td><td>{z["gp"]}</td><td>{broj(z["min"])}</td>'
            f'<td>{broj(z["pts"])}</td><td>{broj(z["reb"])}</td><td>{broj(z["ast"])}</td>'
            f'<td><b>{broj(z["pir"])}</b></td><td>{procenat(z["ts"])}</td></tr>')


def stranica_igrac(k, r, najava, tabela):
    naziv = lambda t: k["timovi"].get(t, t)
    info = k["igraci"].get(r["id"]) or {}
    utakmice = k["po_sezona"][r["id"]]
    z = r["zp"]
    MN = {"Bek": "bekovima", "Krilo": "krilima", "Centar": "centrima"}

    # 1. Lična karta
    red1 = [f'#{e(info["broj"])}' if info.get("broj") else "", e(r["poz"]),
            f'<a href="../tim/{r["tim"]}.html">{e(naziv(r["tim"]))}</a>']
    red2 = []
    if info.get("visina"):
        red2.append(f'{info["visina"]} cm')
    if info.get("datum_rodjenja"):
        dr = datetime.strptime(info["datum_rodjenja"][:10], "%Y-%m-%d")
        red2.append(f'{godine(info["datum_rodjenja"])} god. (rođen {dr.day}.{dr.month}.{dr.year}.)')
    if info.get("drzava"):
        red2.append(e(drzava(info["drzava"])))
    karta = f"""<div class="karta"><div class="krug" aria-hidden="true">{e(inicijali(r['ime']))}</div>
<div><h1>{e(r['ime'])}{A.bedz(r['id'])}</h1>
<p class="info">{' · '.join(x for x in red1 if x)}<br>{' · '.join(red2)}</p></div></div>"""

    # 2. Status povrede
    status = ""
    p = A.POVREDE.get(r["id"])
    if p:
        delovi_st = [f"<b>{e(p['razlog'])}</b>" if p.get("razlog") else ""]
        if p.get("povratak"):
            delovi_st.append(f"očekivani povratak: {e(p['povratak'])}")
        if p.get("azurirano"):
            delovi_st.append(f"ažurirano: {e(p['azurirano'])}")
        if p.get("izvor", "").startswith("http"):
            delovi_st.append(f'<a href="{e(p["izvor"])}" rel="nofollow noopener" target="_blank">izvor</a>')
        status = (f'<div class="sekcija"><h2>Status {A.bedz(r["id"])}</h2>'
                  f'<p style="margin:0">{" · ".join(x for x in delovi_st if x) or "bez detalja"}</p></div>')

    # 3. Sledeći meč (kartica iz najave)
    sledeci = ""
    if najava:
        a, mec, protivnik = najava
        A.LINK_IGRACA = lambda i: f"{i}.html"
        dt = datetime.strptime(mec["datum"], "%Y-%m-%d %H:%M")
        mesto = "kod kuće" if a["kod_kuce"] else "u gostima"
        sledeci = (f'<div class="sekcija u-profilu"><h2>Sledeći meč: {e(naziv(protivnik))} ({mesto}), '
                   f'{A.DANI[dt.weekday()]} {dt.strftime("%d.%m. u %H:%M")}</h2>'
                   f'{A.html_kartica(a, naziv(protivnik))}</div>')

    # 4. Pregled sezone (proseci po utakmici)
    gp = z["gp"]
    s = lambda kl: sum(u[kl] or 0 for u in utakmice) / gp
    def sut(proc, m, a):
        return f'{procenat(proc)} <span class="napomena">({broj(m / gp)}/{broj(a / gp)})</span>'
    pregled = f"""<div class="sekcija skrol"><h2>Sezona {oznaka_sezone(k['sezona'])} · proseci po utakmici</h2>
<table class="tab"><thead><tr><th>UT</th><th>Min</th><th>Poeni</th><th>Skok</th><th>SkN</th><th>SkO</th>
<th>Asist</th><th>Ukr</th><th>Bl</th><th>Izg</th><th>2P%</th><th>3P%</th><th>SB%</th><th>PIR</th></tr></thead>
<tbody><tr><td>{gp}</td><td>{broj(z['min'])}</td><td><b>{broj(z['pts'])}</b></td><td>{broj(z['reb'])}</td>
<td>{broj(s('skokovi_napad'))}</td><td>{broj(s('skokovi_odbrana'))}</td><td>{broj(z['ast'])}</td>
<td>{broj(z['stl'])}</td><td>{broj(z['blk'])}</td><td>{broj(z['tov'])}</td>
<td>{sut(z['p2'], z['p2m'], z['p2a'])}</td><td>{sut(z['p3'], z['p3m'], z['p3a'])}</td>
<td>{sut(z['ft'], z['ftm'], z['fta'])}</td><td><b>{broj(z['pir'])}</b></td></tr></tbody></table>
<p class="napomena">U zagradi: pogođeno/pokušano po utakmici. SkN/SkO = skokovi u napadu/odbrani.</p></div>"""

    # 5. Napredna statistika
    adv, rang = r["adv"], r.get("rang", {})
    def kocka(kljuc, vrednost, naslov, opis):
        rg = rang.get(kljuc)
        rang_t = (f"{rg[0]}. od {rg[1]} među {MN.get(r['poz'], 'igračima')}" if rg
                  else "nema ranga (malo minuta ili utakmica)")
        return (f'<div class="adv"><div class="adv-v">{vrednost}</div><div class="adv-n">{naslov}</div>'
                f'<div class="adv-r">{rang_t}</div><div class="adv-o">{opis}</div></div>')
    pm = adv["pm40"]
    pm_t = "–" if pm is None else ("+" if pm > 0 else "") + broj(pm)
    napredno = f"""<div class="sekcija"><h2>Napredna statistika</h2><div class="adv-mreza">
{kocka("ts", procenat(adv["ts"]), "TS%", "Prava efikasnost šuta: računa i trojke i slobodna bacanja.")}
{kocka("efg", procenat(adv["efg"]), "eFG%", "Procenat šuta iz igre u kom trojka vredi više od dvojke.")}
{kocka("usg", "–" if adv["usg"] is None else broj(adv["usg"]) + "%", "USG%",
       "Koliki deo napada tima završi on dok je na terenu (šut, bacanja, izgubljena lopta). Prosek ≈ 20%.")}
{kocka("pm40", pm_t, "+/- na 40 min", "Razlika u poenima za tim dok je on na terenu, preračunata na 40 minuta.")}
</div></div>"""

    # 6. Splitovi
    top8 = {t for t, _ in tabela[:8]}
    pobede = [u for u in utakmice if rezultat(u)[0] == "P"]
    splitovi = f"""<div class="sekcija skrol"><h2>Splitovi</h2><table class="tab"><thead><tr>
<th class="l"></th><th>UT</th><th>Min</th><th>Poeni</th><th>Skok</th><th>Asist</th><th>PIR</th><th>TS%</th>
</tr></thead><tbody>
{split_red("Kod kuće", [u for u in utakmice if u["domacin"] == 1])}
{split_red("U gostima", [u for u in utakmice if u["domacin"] == 0])}
{split_red("Protiv top 8", [u for u in utakmice if u["protivnik"] in top8])}
{split_red("Protiv ostalih", [u for u in utakmice if u["protivnik"] not in top8])}
{split_red("U pobedama", pobede)}
{split_red("U porazima", [u for u in utakmice if u not in pobede])}
</tbody></table><p class="napomena">Top 8 = prvih 8 timova trenutne tabele.</p></div>"""

    # 7. Grafikoni
    poslednjih = utakmice[-10:]
    opisi = [f"{u['kolo']}. kolo · {'vs' if u['domacin'] else '@'} {naziv(u['protivnik'])} · "
             for u in poslednjih]
    oznake = [u["protivnik"] for u in poslednjih]
    pir = [u["pir"] or 0 for u in poslednjih]
    minuti = [round(u["minuti"] or 0, 1) for u in poslednjih]
    po_sezonama = {}
    for u in k["po_sve"][r["id"]]:
        po_sezonama.setdefault(u["sezona"], []).append(u)
    sez = sorted(po_sezonama)
    pir_sez = [round(zbirno(po_sezonama[x])["pir"], 1) for x in sez]
    graf = f"""<div class="dva">
<div class="sekcija grafikon"><h2>PIR · poslednjih {len(poslednjih)} <small style="font-weight:400;color:var(--muted)">· prosek sezone {broj(z["pir"])}</small></h2>
{svg_stubici(pir, [o + f"{v} PIR" for o, v in zip(opisi, pir)], z["pir"], "PIR u poslednjim utakmicama", oznake, sirina=420)}
<p class="opis">Ispod stubića je protivnik. Pređi mišem preko stubića za detalje.</p></div>
<div class="sekcija grafikon"><h2>Minuti · poslednjih {len(poslednjih)} <small style="font-weight:400;color:var(--muted)">· prosek sezone {broj(z["min"])}</small></h2>
{svg_stubici(minuti, [o + f"{broj(v)} min" for o, v in zip(opisi, minuti)], z["min"], "Minuti u poslednjim utakmicama", oznake, sirina=420)}
<p class="opis">Isprekidana linija je sezonski prosek.</p></div></div>
<div class="sekcija grafikon uska"><h2>PIR kroz sezone</h2>
{svg_stubici(pir_sez, [f"{oznaka_sezone(x)}: {broj(v)} PIR ({utakmica_rec(len(po_sezonama[x]))})" for x, v in zip(sez, pir_sez)],
             None, "Prosečan PIR po sezoni", [oznaka_sezone(x) for x in sez], natpisi=True, sirina=420)}
<p class="opis">Prosečan PIR po utakmici u svakoj sezoni (poslednje 4 sezone).</p></div>"""

    # 8. Dnevnik utakmica (najnovije prve)
    red_ut = []
    for u in reversed(utakmice):
        ishod, skor = rezultat(u)
        red_ut.append(
            f'<tr><td>{u["kolo"]}</td><td class="l">{datum_srb(u["datum"])}</td>'
            f'<td class="l">{"vs" if u["domacin"] else "@"} '
            f'<a href="../tim/{u["protivnik"]}.html">{e(naziv(u["protivnik"]))}</a></td>'
            f'<td class="l"><a href="../utakmica/{u["sezona"]}-{u["sifra_utakmice"]}.html">'
            f'<span class="{ishod.lower()}">{ishod}</span> {skor}</a></td>'
            f'<td>{broj(u["minuti"])}</td><td><b>{u["poeni"]}</b></td>'
            f'<td>{u["sut2_pogodjeno"]}/{u["sut2_pokusano"]}</td>'
            f'<td>{u["sut3_pogodjeno"]}/{u["sut3_pokusano"]}</td>'
            f'<td>{u["slobodna_pogodjeno"]}/{u["slobodna_pokusano"]}</td>'
            f'<td>{u["skokovi_ukupno"]}</td><td>{u["asistencije"]}</td><td>{u["ukradene"]}</td>'
            f'<td>{u["izgubljene"]}</td><td>{u["blokade"]}</td><td><b>{u["pir"]}</b></td></tr>')

    # 9. Po sezonama
    red_sez = []
    for x in sorted(po_sezonama, reverse=True):
        zz = prosireno(po_sezonama[x])
        timovi = ", ".join(dict.fromkeys(naziv(u["tim"]) for u in po_sezonama[x]))
        red_sez.append(f'<tr><td class="l">{oznaka_sezone(x)}</td><td class="l">{e(timovi)}</td>'
                       f'<td>{zz["gp"]}</td><td>{broj(zz["min"])}</td><td>{broj(zz["pts"])}</td>'
                       f'<td>{broj(zz["reb"])}</td><td>{broj(zz["ast"])}</td><td>{broj(zz["stl"])}</td>'
                       f'<td>{broj(zz["blk"])}</td><td><b>{broj(zz["pir"])}</b></td>'
                       f'<td>{procenat(zz["p3"])}</td><td>{procenat(zz["ts"])}</td></tr>')

    telo = f"""{karta}
{status}
{sledeci}
{pregled}
{napredno}
{splitovi}
{graf}
<div class="sekcija skrol"><h2>Dnevnik utakmica · {oznaka_sezone(k['sezona'])}</h2><table class="tab"><thead><tr>
<th>Kolo</th><th class="l">Datum</th><th class="l">Protivnik</th><th class="l">Rezultat</th>
<th>Min</th><th>Poeni</th><th>2P</th><th>3P</th><th>SB</th><th>Skok</th><th>As</th><th>Uk</th>
<th>Izg</th><th>Bl</th><th>PIR</th></tr></thead><tbody>{''.join(red_ut)}</tbody></table>
<p class="napomena">vs = kod kuće, @ = u gostima · P = pobeda, I = poraz · klik na rezultat otvara box score</p></div>
<div class="sekcija skrol"><h2>Po sezonama</h2><table class="tab"><thead><tr>
<th class="l">Sezona</th><th class="l">Tim</th><th>UT</th><th>Min</th><th>Poeni</th><th>Skok</th>
<th>Asist</th><th>Ukr</th><th>Bl</th><th>PIR</th><th>3P%</th><th>TS%</th></tr></thead><tbody>{''.join(red_sez)}</tbody></table></div>"""
    snimi(SAJT / "igrac" / f"{r['id']}.html", strana(r["ime"], telo, "../", ""))


# ----------------------------- GLAVNI DEO -----------------------------
def main():
    if not BAZA.exists():
        print(f"Nema baze: {BAZA}. Prvo pokreni azuriraj_bazu.py.")
        return
    baza = sqlite3.connect(BAZA)
    k = A.analiziraj_kolo(baza)
    if not k:
        print("Nema zakazanih utakmica u tekućoj sezoni.")
        return
    utakmice = [dict(u) for u in baza.execute(
        "SELECT * FROM utakmice WHERE sezona=? ORDER BY datum", (k["sezona"],))]
    baza.close()

    # Svi igrači koji su igrali u tekućoj sezoni, sa trenutnim timom
    lista = []
    for igrac_id, utak in k["po_sezona"].items():
        if not utak:
            continue
        info = k["igraci"].get(igrac_id) or {}
        lista.append({"id": igrac_id, "ime": A.lepo_ime(info.get("ime")),
                      "poz": A.POZICIJA.get(info.get("pozicija"), "?"),
                      "tim": k["poslednji_tim"][igrac_id], "z": zbirno(utak), "zp": prosireno(utak)})
    lista.sort(key=lambda r: -r["z"]["pir"])
    for r in lista:
        r["tim_naziv"] = k["timovi"].get(r["tim"], r["tim"])

    # Povrede iz Dejanove Google tabele
    A.POVREDE = POV.ucitaj([(r["id"], r["ime"], r["tim"]) for r in lista])
    for a in k["sve_analize"]:
        p = A.POVREDE.get(a["id"])
        if p:
            detalji = ", ".join(x for x in (p.get("razlog"), p.get("povratak") and
                                             f"očekivani povratak: {p['povratak']}") if x)
            a["rezime"].insert(0, f"{p['bedz'].capitalize()}{': ' + detalji if detalji else ''}.")

    # Ko igra u narednom kolu (za karticu "Sledeći meč" na profilu)
    najava = {}
    for m in k["mecevi"]:
        for tim, prot in ((m["domacin"], m["gost"]), (m["gost"], m["domacin"])):
            for a in k["analize_po_mecu"][(m["sifra_utakmice"], tim)]:
                najava[a["id"]] = (a, m, prot)

    # Brišemo stari sajt da ne ostanu stranice igrača koji su otišli,
    # ali NE diramo skriveni folder .git (veza sa GitHub-om)
    SAJT.mkdir(exist_ok=True)
    for stavka in SAJT.iterdir():
        if stavka.name == ".git":
            continue
        if stavka.is_dir():
            shutil.rmtree(stavka)
        else:
            stavka.unlink()
    (SAJT / "stil.css").write_text(A.CSS + DODATNI_CSS, encoding="utf-8")
    (SAJT / "logo.svg").write_text(LOGO_SVG, encoding="utf-8")
    (SAJT / ".nojekyll").write_text("", encoding="utf-8")  # GitHub Pages: objavi fajlove kakvi jesu

    tabela = tabela_lige(k, utakmice)
    napredna_statistika(k, lista, tabela)
    stranica_pocetna(k, lista, tabela, utakmice)
    stranica_utakmice(k, lista, utakmice)
    stranica_propovi(k, utakmice)
    stranica_forma(k, lista)
    stranica_lideri(k, lista, tabela)
    stranica_igraci(k, lista)
    stranica_timovi(k, tabela)
    for tim, _ in tabela:
        stranica_tim(k, tim, lista, utakmice, tabela)
    for r in lista:
        stranica_igrac(k, r, najava.get(r["id"]), tabela)
    for u in utakmice:
        if u["odigrana"]:
            stranica_utakmica(k, u)

    print(f"Gotovo! Sajt ima {len(lista)} igrača i {len(tabela)} timova. Statusa povreda: {len(A.POVREDE)}.")
    print(f"Otvori: {SAJT / 'index.html'}")


if __name__ == "__main__":
    main()
