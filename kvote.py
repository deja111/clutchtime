"""
kvote.py
---------
Preuzima kvote za propove igrača (preko/ispod) iz OddsPapi-ja za naredno kolo
Evrolige i snima ih u podaci/kvote/kvote_poslednje.json (sajt i model rade iz fajla).

Pokretanje (Command Prompt, iz foldera Projekat):
    set ODDSPAPI_KEY=tvoj_kljuc
    python kvote.py              - zove API samo ako treba (pravila štednje ispod)
    python kvote.py --sada       - zove odmah, bez obzira na raspored (i dalje pazi na limit)
    python kvote.py --fajl X     - bez poziva: samo obradi sačuvan sirov odgovor X (za proveru)

Pravila štednje (besplatan plan: 250 zahteva mesečno):
    - zove samo na dan utakmice ili dan pre (raspored iz baze, besplatno)
    - najviše 2 poziva dnevno (brojač u podaci/kvote/pozivi.json)
    - pre poziva proveri stanje naloga (besplatno); ne zove ako je potrošeno 200+
    - 1 poziv = celo kolo za jednu kladionicu; neuspeli poziv se NE ponavlja

Ako ključ nije postavljen (npr. Secret još nije dodat na GitHub), samo to napiše i
završi bez greške, da ne zaustavi ažuriranje sajta.
"""

import json
import os
import sqlite3
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

from povrede import normalizuj

FOLDER = Path(__file__).parent
BAZA = FOLDER / "podaci" / "evroliga.db"
LOG_FAJL = FOLDER / "podaci" / "log.txt"
IZLAZ = FOLDER / "podaci" / "kvote"
KATALOG = IZLAZ / "marketi_igraci.json"     # mali izvod iz kataloga marketa (samo propovi igrača)
POZIVI = IZLAZ / "pozivi.json"              # koliko puta je API pozvan kog dana
POSLEDNJE = IZLAZ / "kvote_poslednje.json"

OSNOVA = "https://api.oddspapi.io"
TURNIR = 138                 # Evroliga kod OddsPapi-ja
KOSARKA = 11                 # sportId za košarku
KLADIONICA = "superbet.rs"   # jedina srpska kladionica sa propovima za Evroligu (provereno 30.10.2026)
GRANICA = 200                # ne zovemo ako je mesečno potrošeno ovoliko ili više
NAJVISE_DNEVNO = 2

# marketType iz kataloga -> naš naziv (ostali tipovi se ne čuvaju)
TIPOVI = {
    "playertotals-points": "poeni",
    "playertotals-rebounds": "skokovi",
    "playertotals-assists": "asistencije",
    "playertotals-ptsassreb": "PSA",
    "playertotals-ptsreb": "PS",
    "playertotals-ptsass": "PA",
    "playertotals-assreb": "SA",
    "playertotals-3pointers": "trojke",
    "playertotals-steals": "ukradene",
    "playertotals-blocks": "blokade",
}


def zapisi(poruka, greska=False):
    """Ispis + red u podaci/log.txt. Greške sadrže 'NIJE preuzeta' da bi workflow dao crveni X."""
    print(poruka)
    with open(LOG_FAJL, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M')}  {'Kvote NIJE preuzeta: ' if greska else ''}{poruka}\n")


# ----------------------------- POZIVI -----------------------------
def pozovi(putanja, parametri, kljuc):
    """Jedan poziv bez ponavljanja. Vraća (status, json) ili (None, None) kad nema veze."""
    try:
        odgovor = requests.get(OSNOVA + putanja, params={**parametri, "apiKey": kljuc}, timeout=60)
    except requests.RequestException as g:
        return None, {"greska": type(g).__name__}
    try:
        telo = odgovor.json()
    except ValueError:
        telo = {"_tekst": odgovor.text[:500]}
    time.sleep(1.5)
    return odgovor.status_code, telo


def potroseno(kljuc):
    """Broj potrošenih zahteva ovog meseca (besplatan poziv). None ako ne uspe."""
    status, telo = pozovi("/v4/account", {}, kljuc)
    if status != 200:
        return None
    for pretplata in telo.get("subscriptions") or [telo]:
        if pretplata.get("is_active", True) and "request_count" in pretplata:
            return pretplata["request_count"]
    return telo.get("request_count")


def ucitaj_katalog(kljuc):
    """{marketId: {"tip", "linija", "ishodi": {outcomeId: "over"/"under"}}}. Jednom se preuzme (1 zahtev)."""
    if KATALOG.exists():
        return json.loads(KATALOG.read_text(encoding="utf-8"))
    # Ako postoji pun katalog od istrazi_oddspapi.py, koristimo njega (bez zahteva)
    pun = sorted((FOLDER / "podaci" / "oddspapi").glob("marketi_*.json"), reverse=True)
    if pun:
        marketi = json.loads(pun[0].read_text(encoding="utf-8"))["odgovor"]
    elif kljuc:
        status, marketi = pozovi("/v4/markets", {"sportId": KOSARKA}, kljuc)
        if status != 200:
            zapisi(f"katalog marketa, status {status}", greska=True)
            return None
    else:
        return None
    katalog = {}
    for m in marketi:
        if m.get("marketType") in TIPOVI:
            katalog[str(m["marketId"])] = {
                "tip": TIPOVI[m["marketType"]], "linija": m.get("handicap"),
                "ishodi": {str(o["outcomeId"]): str(o.get("outcomeName", "")).lower() for o in m.get("outcomes", [])}}
    IZLAZ.mkdir(parents=True, exist_ok=True)
    KATALOG.write_text(json.dumps(katalog, ensure_ascii=False, indent=0), encoding="utf-8")
    return katalog


# ----------------------------- BAZA -----------------------------
def ucitaj_bazu():
    """Raspored narednih utakmica, imena igrača i njihov poslednji tim."""
    baza = sqlite3.connect(BAZA)
    baza.row_factory = sqlite3.Row
    utakmice = [dict(r) for r in baza.execute(
        "SELECT sezona, sifra_utakmice, datum, domacin, gost FROM utakmice WHERE odigrana=0 ORDER BY datum")]
    imena = {r["igrac_id"]: r["ime"] or "" for r in baza.execute("SELECT igrac_id, ime FROM igraci")}
    tim = {}
    for r in baza.execute("SELECT s.igrac_id, s.tim FROM statistika s JOIN utakmice u "
                          "ON u.sezona=s.sezona AND u.sifra_utakmice=s.sifra_utakmice ORDER BY u.datum"):
        tim[r["igrac_id"]] = r["tim"]  # poslednja utakmica pobeđuje
    baza.close()
    return utakmice, imena, tim


def kljucevi_imena(ime_baze):
    """'WRIGHT IV, MCKINLEY' -> {'mckinley wright iv', 'wright iv mckinley'}"""
    prezime, _, ime = ime_baze.partition(",")
    return {normalizuj(f"{ime} {prezime}"), normalizuj(f"{prezime} {ime}")}


def upari(ime_feed, kandidati, imena):
    """igrac_id za ime iz kvota. Prvo tačno poklapanje, pa najviše zajedničkih delova imena
    među igračima dva tima tog meča (npr. 'Oturu, Daniel' -> 'OTURU, DAN')."""
    trazi = normalizuj(ime_feed.replace(",", " "))
    tacni = [i for i in kandidati if trazi in kljucevi_imena(imena[i])]
    if len(tacni) == 1:
        return tacni[0]
    delovi = set(trazi.split())
    ocene = sorted(((len(delovi & set(normalizuj(imena[i].replace(",", " ")).split())), i) for i in kandidati),
                   reverse=True)
    if ocene and ocene[0][0] >= 1 and (len(ocene) == 1 or ocene[1][0] < ocene[0][0]):
        return ocene[0][1]
    return None


# ----------------------------- OBRADA -----------------------------
def obradi(mecevi, katalog, utakmice, imena, tim):
    """Sirov odgovor -> lista propova (jedan red = igrač, tip, linija, kvota preko/ispod)."""
    po_timu = {}
    for i, t in tim.items():
        po_timu.setdefault(t, []).append(i)

    propovi, neupareni = [], set()
    for mec in mecevi:
        bo = (mec.get("bookmakerOdds") or {}).get(KLADIONICA)
        if not bo or not bo.get("bookmakerIsActive", True):
            continue
        pocetak = datetime.strptime(mec["startTime"][:16], "%Y-%m-%dT%H:%M")  # UTC

        # Skupi kvote: (ime, marketId) -> {"over": kvota, "under": kvota}
        sirovo = {}
        for mid, market in (bo.get("markets") or {}).items():
            k = katalog.get(str(mid))
            if not k:
                continue
            for oid, ishod in (market.get("outcomes") or {}).items():
                strana = k["ishodi"].get(str(oid))
                for p in (ishod.get("players") or {}).values():
                    if p.get("active") and p.get("playerName") and strana in ("over", "under"):
                        x = sirovo.setdefault((p["playerName"], str(mid)), {"promenjeno": p.get("changedAt")})
                        x[strana] = p.get("price")
        if not sirovo:
            continue

        # Koja je to naša utakmica: tim većine uparenih igrača + vreme početka (±6 h zbog vremenske zone)
        glasovi = {}
        for ime, _ in sirovo:
            for i in [i for i in imena if normalizuj(ime.replace(",", " ")) in kljucevi_imena(imena[i])]:
                if i in tim:
                    glasovi[tim[i]] = glasovi.get(tim[i], 0) + 1
        utakmica = max(
            (u for u in utakmice
             if abs(datetime.strptime(u["datum"], "%Y-%m-%d %H:%M") - pocetak) <= timedelta(hours=6)),
            key=lambda u: glasovi.get(u["domacin"], 0) + glasovi.get(u["gost"], 0), default=None)
        if not utakmica or glasovi.get(utakmica["domacin"], 0) + glasovi.get(utakmica["gost"], 0) == 0:
            neupareni.add(f"meč {mec.get('fixtureId')} ({mec['startTime']})")
            continue
        kandidati = po_timu.get(utakmica["domacin"], []) + po_timu.get(utakmica["gost"], [])

        for (ime, mid), x in sirovo.items():
            if "over" not in x or "under" not in x:
                continue
            igrac_id = upari(ime, kandidati, imena)
            if not igrac_id:
                neupareni.add(ime)
                continue
            k = katalog[mid]
            propovi.append({
                "igrac_id": igrac_id, "ime": ime, "tim": tim[igrac_id],
                "sezona": utakmica["sezona"], "sifra_utakmice": utakmica["sifra_utakmice"],
                "datum": utakmica["datum"], "tip": k["tip"], "linija": k["linija"],
                "preko": x["over"], "ispod": x["under"], "promenjeno": x["promenjeno"]})
    propovi.sort(key=lambda p: (p["datum"], p["sifra_utakmice"], p["tim"], p["ime"], p["tip"], p["linija"]))
    return propovi, sorted(neupareni)


# ----------------------------- GLAVNI DEO -----------------------------
def treba_zvati(utakmice, pozivi):
    danas = date.today()
    dani = {danas.isoformat(), (danas + timedelta(days=1)).isoformat()}
    if not any(u["datum"][:10] in dani for u in utakmice):
        return "nema utakmica danas ni sutra"
    if pozivi.get(danas.isoformat(), 0) >= NAJVISE_DNEVNO:
        return f"već {NAJVISE_DNEVNO} poziva danas"
    return None


def main():
    arg = sys.argv[1:]
    if not BAZA.exists():
        print("Nema baze. Prvo pokreni azuriraj_bazu.py.")
        return
    utakmice, imena, tim = ucitaj_bazu()
    kljuc = os.environ.get("ODDSPAPI_KEY", "").strip()

    if "--fajl" in arg:  # samo obrada sačuvanog odgovora, bez poziva
        sirovo = json.loads(Path(arg[arg.index("--fajl") + 1]).read_text(encoding="utf-8"))
        mecevi = sirovo.get("odgovor", sirovo)
        mecevi = mecevi if isinstance(mecevi, list) else [mecevi]
    else:
        if not kljuc:
            print("Kvote: nema ključa (ODDSPAPI_KEY), preskačem.")
            return
        pozivi = json.loads(POZIVI.read_text(encoding="utf-8")) if POZIVI.exists() else {}
        razlog = None if "--sada" in arg else treba_zvati(utakmice, pozivi)
        if razlog:
            print(f"Kvote: ne zovem API ({razlog}).")
            return
        stanje = potroseno(kljuc)
        if stanje is None or stanje >= GRANICA:
            zapisi(f"Kvote: ne zovem API (potrošeno: {stanje}, granica {GRANICA}).")
            return

        danas = date.today().isoformat()
        pozivi[danas] = pozivi.get(danas, 0) + 1  # računa se i neuspeo poziv (i on se naplaćuje)
        IZLAZ.mkdir(parents=True, exist_ok=True)
        POZIVI.write_text(json.dumps(dict(sorted(pozivi.items())[-60:]), indent=0), encoding="utf-8")
        status, telo = pozovi("/v4/odds-by-tournaments",
                              {"tournamentIds": TURNIR, "bookmaker": KLADIONICA, "oddsFormat": "decimal"}, kljuc)
        if status != 200:
            poruka = (telo or {}).get("error", telo) if isinstance(telo, dict) else telo
            zapisi(f"status {status}, odgovor: {str(poruka)[:300]}", greska=True)
            return
        mecevi = telo if isinstance(telo, list) else [telo]

    katalog = ucitaj_katalog(kljuc)
    if not katalog:
        zapisi("nema kataloga marketa", greska=True)
        return
    propovi, neupareni = obradi(mecevi, katalog, utakmice, imena, tim)

    rezultat = {"preuzeto": datetime.now().strftime("%Y-%m-%d %H:%M"), "kladionica": KLADIONICA,
                "broj": len(propovi), "neupareni": neupareni, "propovi": propovi}
    if "--fajl" in arg:
        print(json.dumps(rezultat, ensure_ascii=False, indent=1)[:3000])
    else:
        IZLAZ.mkdir(parents=True, exist_ok=True)
        POSLEDNJE.write_text(json.dumps(rezultat, ensure_ascii=False, indent=1), encoding="utf-8")
        # Arhiva po pozivu (za kasniju proveru modela: kakve su bile linije pre meča)
        arhiva = IZLAZ / "arhiva" / f"{datetime.now().strftime('%Y-%m-%d_%H%M')}.json"
        arhiva.parent.mkdir(exist_ok=True)
        arhiva.write_text(json.dumps(rezultat, ensure_ascii=False), encoding="utf-8")
    igraca = len({p["igrac_id"] for p in propovi})
    zapisi(f"Kvote ({KLADIONICA}): {len(propovi)} linija za {igraca} igrača"
           + (f"; neupareno: {', '.join(neupareni)}" if neupareni else ""))


if __name__ == "__main__":
    main()
