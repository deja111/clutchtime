"""
istrazi_oddspapi.py
--------------------
Jednokratno istraživanje OddsPapi odgovora (pre pisanja kvote.py).
Snima sirove odgovore u podaci/oddspapi/*.json i ispiše kratak pregled:
ID Evrolige, koji marketi postoje za igrače, kako izgleda linija i
koliko imena igrača uspe da se upari sa bazom.

Pokretanje (Command Prompt, iz foldera Projekat), NA DAN UTAKMICA:
    set ODDSPAPI_KEY=tvoj_kljuc
    python istrazi_oddspapi.py

Troši najviše 3 zahteva (besplatan plan: 250 mesečno):
    1. /v4/tournaments  - samo prvi put (posle se čita iz fajla)
    2. /v4/markets      - samo prvi put (posle se čita iz fajla)
    3. /v4/odds-by-tournaments - kvote celog kola
Provera stanja (/v4/account) je besplatna i radi se pre i posle.

Opcije:
    --suvo         samo ispiše šta bi pozvao, ne zove ništa
    --turnir ID    ručno zadat ID Evrolige (ako ga skripta ne nađe sama)
    --pregled      bez poziva: samo ponovo ispiše pregled iz sačuvanih fajlova

Pravila: ključ se nikad ne ispisuje i ne snima. Neuspeli poziv se NE ponavlja
(i greške se naplaćuju), samo se snimi odgovor da vidimo šta je pošlo naopako.
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
IZLAZ = Path(os.environ.get("ODDSPAPI_FOLDER", FOLDER / "podaci" / "oddspapi"))  # drugačiji samo za testiranje
BAZA = FOLDER / "podaci" / "evroliga.db"
OSNOVA = os.environ.get("ODDSPAPI_BASE", "https://api.oddspapi.io")  # drugačija samo za testiranje
KOSARKA = 11  # sportId za košarku
GRANICA = 200  # ne trošimo zahteve ako je mesečno potrošeno ovoliko ili više
PAUZA = 1.5  # sekundi između poziva


# ----------------------------- POZIVI -----------------------------
def pozovi(putanja, parametri, naziv, kljuc, suvo=False):
    """Jedan poziv, bez ponavljanja. Odgovor (i greška) se snima u fajl."""
    javni = "&".join(f"{k}={v}" for k, v in parametri.items())
    print(f"  -> GET {putanja}{'?' + javni if javni else ''}")
    if suvo:
        return None
    try:
        odgovor = requests.get(OSNOVA + putanja, params={**parametri, "apiKey": kljuc}, timeout=60)
    except requests.RequestException as greska:
        print(f"  !! Nema veze sa serverom: {type(greska).__name__}")
        return None
    try:
        telo = odgovor.json()
    except ValueError:
        telo = {"_tekst": odgovor.text[:2000]}
    vreme = datetime.now().strftime("%Y%m%d_%H%M%S")
    IZLAZ.mkdir(parents=True, exist_ok=True)
    fajl = IZLAZ / f"{naziv}_{vreme}.json"
    fajl.write_text(json.dumps({"_putanja": putanja, "_parametri": parametri, "_status": odgovor.status_code,
                                "_vreme": vreme, "odgovor": telo}, ensure_ascii=False, indent=1),
                    encoding="utf-8")
    print(f"  <- {odgovor.status_code}, snimljeno: {fajl.name}")
    time.sleep(PAUZA)
    return telo if odgovor.ok else None


def poslednji_fajl(naziv):
    """Najnoviji uspešan sačuvan odgovor (status 200) ili None."""
    for fajl in sorted(IZLAZ.glob(f"{naziv}_*.json"), reverse=True):
        podaci = json.loads(fajl.read_text(encoding="utf-8"))
        if podaci.get("_status") == 200:
            return podaci["odgovor"]
    return None


def nadji_kljuceve(obj, *imena):
    """Rekurzivno traži prvu vrednost za svako od imena (format odgovora nije siguran)."""
    nadjeno = {}
    def idi(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in imena and k not in nadjeno:
                    nadjeno[k] = v
                idi(v)
        elif isinstance(o, list):
            for x in o:
                idi(x)
    idi(obj)
    return nadjeno


def stanje_naloga(kljuc, naziv, suvo):
    telo = pozovi("/v4/account", {}, naziv, kljuc, suvo)
    if telo is None:
        return None
    s = nadji_kljuceve(telo, "request_count", "request_limit", "requestCount", "requestLimit")
    potroseno = s.get("request_count", s.get("requestCount"))
    limit = s.get("request_limit", s.get("requestLimit"))
    print(f"  Stanje: potrošeno {potroseno} od {limit}")
    return potroseno


def kao_lista(telo):
    """Odgovor može biti lista ili rečnik {id: {...}} ili {"data": [...]}."""
    if isinstance(telo, list):
        return telo
    if isinstance(telo, dict):
        for k in ("data", "tournaments", "markets", "items"):
            if isinstance(telo.get(k), list):
                return telo[k]
        if all(isinstance(v, dict) for v in telo.values()):
            return [{"_kljuc": k, **v} for k, v in telo.items()]
    return []


# ----------------------------- RASPORED -----------------------------
def utakmice_danas_sutra():
    if not BAZA.exists():
        return []
    danas = date.today()
    baza = sqlite3.connect(BAZA)
    redovi = baza.execute(
        "SELECT datum, domacin, gost FROM utakmice WHERE odigrana=0 AND substr(datum,1,10) IN (?,?) ORDER BY datum",
        (danas.isoformat(), (danas + timedelta(days=1)).isoformat())).fetchall()
    baza.close()
    return redovi


# ----------------------------- PREGLED -----------------------------
def nadji_evroligu(turniri):
    kandidati = []
    for t in kao_lista(turniri):
        tekst = " ".join(str(v) for v in t.values() if isinstance(v, (str, int))).lower()
        if "euroleague" in tekst.replace(" ", "") and not any(x in tekst for x in ("women", "eurocup", "u18", "junior")):
            kandidati.append(t)
    return kandidati


def pregled(turnir_id):
    print("\n================ PREGLED ================")
    marketi = {}
    for m in kao_lista(poslednji_fajl("marketi") or []):
        mid = m.get("marketId", m.get("_kljuc"))
        if mid is not None:
            marketi[str(mid)] = m
    print(f"Marketa za košarku u katalogu: {len(marketi)}")
    igracki = {k: m for k, m in marketi.items()
               if m.get("playerProp") or "player" in str(m.get("marketName", "")).lower()}
    print(f"Od toga za igrače (playerProp): {len(igracki)}")
    for k, m in list(igracki.items())[:40]:
        print(f"  {k}: {m.get('marketName')} | tip={m.get('marketType')} | handicap={m.get('handicap')}"
              f" | period={m.get('period')}")

    kvote = poslednji_fajl("kvote")
    if kvote is None:
        print("\nNema sačuvanih kvota (fajl kvote_*.json sa statusom 200).")
        return
    mecevi = kao_lista(kvote)
    print(f"\nMečeva u odgovoru: {len(mecevi)} (turnir {turnir_id})")

    # Imena iz baze za probno uparivanje (baza: "PREZIME, IME")
    imena_baze = set()
    if BAZA.exists():
        baza = sqlite3.connect(BAZA)
        for (ime,) in baza.execute("SELECT ime FROM igraci"):
            prez, _, ime_ = (ime or "").partition(",")
            imena_baze.add(normalizuj(f"{ime_} {prez}"))
            imena_baze.add(normalizuj(f"{prez} {ime_}"))
        baza.close()

    po_marketu, kladionice, imena = {}, set(), set()
    for mec in mecevi:
        for kladionica, bo in (mec.get("bookmakerOdds") or {}).items():
            kladionice.add(kladionica)
            for mid, market in (bo.get("markets") or {}).items():
                x = po_marketu.setdefault(str(mid), {"primeri": [], "igraci": set(), "ishodi": 0})
                for oid, ishod in (market.get("outcomes") or {}).items():
                    for igrac in (ishod.get("players") or {}).values():
                        x["ishodi"] += 1
                        ime = igrac.get("playerName")
                        if ime:
                            x["igraci"].add(ime)
                            imena.add(ime)
                        if len(x["primeri"]) < 3:
                            x["primeri"].append(f"{kladionica} | outcome {oid} | {ime} | "
                                                f"{igrac.get('bookmakerOutcomeId')} | kvota {igrac.get('price')}")
    print(f"Kladionice: {', '.join(sorted(kladionice)) or '-'}")
    print(f"Različitih marketa sa kvotama: {len(po_marketu)}\n")
    for mid, x in sorted(po_marketu.items(), key=lambda kv: -len(kv[1]["igraci"])):
        m = marketi.get(mid, {})
        print(f"Market {mid}: {m.get('marketName', '?')} | igrača: {len(x['igraci'])} | ishoda: {x['ishodi']}")
        for p in x["primeri"]:
            print(f"    {p}")

    if imena and imena_baze:
        upareno = [i for i in imena if normalizuj(i.replace(",", " ")) in imena_baze]
        print(f"\nUparivanje imena sa bazom (prosto, bez dodatnih pravila): {len(upareno)} od {len(imena)}")
        for i in sorted(set(imena) - set(upareno))[:25]:
            print(f"  nije upareno: {i}")


# ----------------------------- GLAVNI DEO -----------------------------
def main():
    arg = sys.argv[1:]
    suvo = "--suvo" in arg
    turnir_id = arg[arg.index("--turnir") + 1] if "--turnir" in arg else None
    if "--pregled" in arg:
        pregled(turnir_id)
        return

    kljuc = os.environ.get("ODDSPAPI_KEY", "").strip()
    if not kljuc and not suvo:
        print("Nema ključa. U Command Prompt-u prvo upiši:  set ODDSPAPI_KEY=tvoj_kljuc")
        return

    mecevi = utakmice_danas_sutra()
    if mecevi:
        print(f"Utakmice danas/sutra: {len(mecevi)} (prva {mecevi[0][0]}: {mecevi[0][1]} - {mecevi[0][2]})")
    else:
        print("U bazi nema utakmica danas ni sutra: kvote verovatno još nisu objavljene.")
        if not suvo and input("Ipak nastaviti i potrošiti zahteve? (da/ne): ").strip().lower() != "da":
            return

    print("\n1) Stanje naloga (besplatno)")
    potroseno = stanje_naloga(kljuc, "nalog_pre", suvo)
    if isinstance(potroseno, int) and potroseno >= GRANICA:
        print(f"Potrošeno je {potroseno} zahteva (granica {GRANICA}). Prekidam.")
        return

    print("\n2) Turniri (ID Evrolige)")
    if not turnir_id:
        turniri = poslednji_fajl("turniri")
        if turniri is None:
            turniri = pozovi("/v4/tournaments", {"sportId": KOSARKA}, "turniri", kljuc, suvo)
        else:
            print("  Iz sačuvanog fajla (bez zahteva).")
        kandidati = nadji_evroligu(turniri or [])
        for t in kandidati:
            print(f"  kandidat: {json.dumps(t, ensure_ascii=False)[:200]}")
        if len(kandidati) == 1:
            turnir_id = kandidati[0].get("tournamentId", kandidati[0].get("_kljuc"))
        elif not suvo:
            print("Ne mogu sigurno da odredim ID Evrolige. Pogledaj kandidate iznad (ili fajl turniri_*.json)\n"
                  "i pokreni ponovo sa:  python istrazi_oddspapi.py --turnir ID")
            return
    print(f"  Evroliga: tournamentId = {turnir_id}")

    print("\n3) Katalog marketa")
    if poslednji_fajl("marketi") is None:
        pozovi("/v4/markets", {"sportId": KOSARKA}, "marketi", kljuc, suvo)
    else:
        print("  Iz sačuvanog fajla (bez zahteva).")

    print("\n4) Kvote celog kola (sve kladionice, da vidimo koje imaju propove)")
    pozovi("/v4/odds-by-tournaments", {"tournamentIds": turnir_id, "oddsFormat": "decimal"},
           "kvote", kljuc, suvo)

    print("\n5) Stanje posle (besplatno)")
    stanje_naloga(kljuc, "nalog_posle", suvo)

    if not suvo:
        pregled(turnir_id)


if __name__ == "__main__":
    main()
