"""
istorija_kvota.py
------------------
Preuzima ISTORIJSKE kvote za već odigrane utakmice Evrolige ove sezone, za Superbet i
dve kladionice za poređenje (Betano, bwin). Služi za proveru "tržišnog modela" na prošlim
kolima pre nego što ga uključimo na sajt.

Pokretanje (Command Prompt, iz foldera Projekat):
    set ODDSPAPI_KEY=tvoj_kljuc
    python istorija_kvota.py            - sve odigrane utakmice od početka sezone
    python istorija_kvota.py --proba    - samo jedna utakmica (da proverimo format i da je besplatno)

Zahtevi:
    /v4/account        - besplatno (provera stanja pre i posle)
    /v4/fixtures       - 1 zahtev (spisak utakmica sa ID-jevima), samo prvi put
    /v4/historical-odds - besplatno po OddsPapi uslovima. Skripta to PROVERAVA: posle prvog
                          poziva pogleda stanje naloga i ako je potrošnja porasla, odmah staje.

Odgovori se snimaju u podaci/oddspapi/istorija/ (ključ se nikad ne snima).
Već preuzete utakmice se preskaču, pa skripta može da se pokrene ponovo.
"""

import json
import os
import sys
import time
from pathlib import Path

import requests

from istrazi_oddspapi import bez_kljuca

FOLDER = Path(__file__).parent
IZLAZ = FOLDER / "podaci" / "oddspapi" / "istorija"
OSNOVA = "https://api.oddspapi.io"
TURNIR = 138
KLADIONICE = "superbet.rs,betano,bwin"   # najviše 3 po pozivu
POCETAK_SEZONE = "2026-09-20"
PAUZA = 5.5   # istorijske kvote: najmanje 5 s između poziva


def pozovi(putanja, parametri, kljuc):
    try:
        odgovor = requests.get(OSNOVA + putanja, params={**parametri, "apiKey": kljuc}, timeout=90)
    except requests.RequestException as g:
        print(f"  !! Nema veze: {type(g).__name__}")
        return None, None
    try:
        telo = odgovor.json()
    except ValueError:
        telo = {"_tekst": odgovor.text[:1000]}
    return odgovor.status_code, bez_kljuca(telo, kljuc)


def potroseno(kljuc):
    status, telo = pozovi("/v4/account", {}, kljuc)
    if status != 200:
        return None
    for p in telo.get("subscriptions") or [telo]:
        if p.get("is_active", True) and "request_count" in p:
            return p["request_count"]
    return telo.get("request_count")


def main():
    kljuc = os.environ.get("ODDSPAPI_KEY", "").strip()
    if not kljuc:
        print("Nema ključa. U Command Prompt-u prvo upiši:  set ODDSPAPI_KEY=tvoj_kljuc")
        return
    proba = "--proba" in sys.argv
    IZLAZ.mkdir(parents=True, exist_ok=True)

    pre = potroseno(kljuc)
    print(f"Stanje naloga: potrošeno {pre}")
    if pre is None or pre >= 200:
        print("Ne mogu da proverim stanje ili je potrošeno 200+. Prekidam.")
        return

    # 1) Spisak odigranih utakmica (1 zahtev, samo prvi put)
    fajl_utakmica = IZLAZ / "utakmice.json"
    if fajl_utakmica.exists():
        utakmice = json.loads(fajl_utakmica.read_text(encoding="utf-8"))
        print(f"Spisak utakmica iz fajla ({len(utakmice)}).")
    else:
        status, utakmice = pozovi("/v4/fixtures", {"tournamentId": TURNIR, "from": POCETAK_SEZONE,
                                                   "statusId": 2}, kljuc)
        time.sleep(2.5)
        if status != 200 or not isinstance(utakmice, list):
            print(f"Spisak utakmica nije preuzet (status {status}): {str(utakmice)[:300]}")
            return
        fajl_utakmica.write_text(json.dumps(utakmice, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"Preuzet spisak: {len(utakmice)} odigranih utakmica.")

    utakmice = sorted(utakmice, key=lambda u: u.get("startTime", ""))
    if proba:
        utakmice = utakmice[-1:]

    # 2) Istorijske kvote po utakmici (besplatno - proveravamo posle prvog poziva)
    provereno = False
    pre_istorije = potroseno(kljuc)
    for n, u in enumerate(utakmice, start=1):
        fid = u["fixtureId"]
        fajl = IZLAZ / f"{fid}.json"
        if fajl.exists():
            continue
        naziv = f'{u.get("participant1Name", "?")} - {u.get("participant2Name", "?")} ({u.get("startTime", "")[:10]})'
        status, telo = pozovi("/v4/historical-odds", {"fixtureId": fid, "bookmakers": KLADIONICE}, kljuc)
        print(f"  [{n}/{len(utakmice)}] {naziv}: status {status}")
        if status == 200:
            fajl.write_text(json.dumps({"utakmica": u, "odgovor": telo}, ensure_ascii=False), encoding="utf-8")
        else:
            print(f"     odgovor: {str(telo)[:300]}")
        if not provereno:
            time.sleep(1)
            posle = potroseno(kljuc)
            print(f"  Provera naplate: pre prvog istorijskog poziva {pre_istorije}, posle {posle}")
            if posle is None or pre_istorije is None or posle > pre_istorije:
                print("  !! Istorijske kvote se naplaćuju (ili ne mogu da proverim). Prekidam.")
                return
            provereno = True
        time.sleep(PAUZA)

    print(f"\nGotovo. Stanje naloga: potrošeno {potroseno(kljuc)}. Fajlovi: podaci/oddspapi/istorija/")


if __name__ == "__main__":
    main()
