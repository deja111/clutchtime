"""
povrede.py
-----------
Čita Dejanovu Google tabelu sa povredama (objavljenu kao CSV) i povezuje
imena iz tabele sa igračima u bazi. Koristi ga sajt.py.

Kolone u tabeli: Igrač | Status | Razlog | Očekivani povratak | Ažurirano | Izvor
Status: "Ne igra", "Upitan" ili "Vraća se".

Ako tabela trenutno ne može da se preuzme (nema interneta i sl.), koristi se
poslednja uspešno preuzeta verzija (podaci/povrede_poslednje.csv), da povrede
ne bi nestale sa sajta zbog kratkog prekida.
"""

import csv
import io
import logging
import unicodedata
from pathlib import Path

import requests

URL_TABELE = ("https://docs.google.com/spreadsheets/d/e/2PACX-1vTDwA3Sc6YILJjO4OWgjj3zk_MT9o7JYKk"
              "PN6s6bNIcTMsJZt4Z-X_sYyYJ8Guz-YlcUPRt8KjmdfQR/pub?gid=0&single=true&output=csv")
FOLDER = Path(__file__).parent
REZERVA = FOLDER / "podaci" / "povrede_poslednje.csv"
LOG_FAJL = FOLDER / "podaci" / "log.txt"

# Kako se status prikazuje na sajtu: (tekst na bedžu, CSS klasa)
STATUSI = {
    "ne igra": ("NE IGRA", "st-ne"),
    "upitan": ("UPITAN", "st-up"),
    "vraca se": ("VRAĆA SE", "st-vr"),
}


def normalizuj(tekst):
    """'Đorđe Šćepanović' -> 'djordje scepanovic' (za poređenje imena)."""
    t = (tekst or "").lower().replace("đ", "dj").replace("-", " ").replace(".", " ")
    t = unicodedata.normalize("NFD", t)
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return " ".join(t.split())


def zapisi_upozorenje(poruka):
    logging.warning(poruka)
    from datetime import datetime
    try:
        with open(LOG_FAJL, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M')}  {poruka}\n")
    except OSError:
        pass


def preuzmi_tekst():
    """Preuzme CSV tabele; ako ne uspe, vrati poslednju sačuvanu verziju."""
    try:
        odgovor = requests.get(URL_TABELE, timeout=30)
        odgovor.raise_for_status()
        odgovor.encoding = "utf-8"
        tekst = odgovor.text
        REZERVA.parent.mkdir(parents=True, exist_ok=True)
        REZERVA.write_text(tekst, encoding="utf-8")
        return tekst
    except requests.RequestException as greska:
        if REZERVA.exists():
            zapisi_upozorenje(f"Povrede: tabela nije preuzeta ({greska}), koristim poslednju verziju.")
            return REZERVA.read_text(encoding="utf-8")
        zapisi_upozorenje(f"Povrede: tabela nije preuzeta ({greska}).")
        return ""


def procitaj_redove(tekst):
    """Vrati listu rečnika sa ključevima: igrac, status, razlog, povratak, azurirano, izvor."""
    citac = csv.reader(io.StringIO(tekst.lstrip("﻿")))
    redovi = list(citac)
    if not redovi:
        return []
    zaglavlje = [normalizuj(h) for h in redovi[0]]
    kolone = {"igrac": "igrac", "status": "status", "razlog": "razlog",
              "ocekivani povratak": "povratak", "azurirano": "azurirano", "izvor": "izvor"}
    indeksi = {kolone[h]: i for i, h in enumerate(zaglavlje) if h in kolone}
    rezultat = []
    for red in redovi[1:]:
        vrednost = lambda k: red[indeksi[k]].strip() if k in indeksi and indeksi[k] < len(red) else ""
        if not vrednost("igrac"):
            continue
        rezultat.append({k: vrednost(k) for k in ("igrac", "status", "razlog", "povratak",
                                                    "azurirano", "izvor")})
    return rezultat


def povezi(redovi, igraci):
    """
    redovi: iz tabele; igraci: lista (igrac_id, ime_za_prikaz, tim).
    Vraća {igrac_id: povreda}. Neprepoznata imena upisuje u log.
    """
    puno_ime, prezime = {}, {}
    for igrac_id, ime, tim in igraci:
        n = normalizuj(ime)
        puno_ime.setdefault(n, igrac_id)
        delovi = n.split()
        if len(delovi) >= 2:
            puno_ime.setdefault(" ".join(delovi[1:] + delovi[:1]), igrac_id)  # "nwora jordan"
            prezime.setdefault(delovi[-1], []).append(igrac_id)

    povrede = {}
    for r in redovi:
        n = normalizuj(r["igrac"])
        igrac_id = puno_ime.get(n)
        if not igrac_id and len(prezime.get(n.split()[-1] if n else "", [])) == 1:
            igrac_id = prezime[n.split()[-1]][0]   # samo prezime, ako je jedinstveno
        if not igrac_id:
            zapisi_upozorenje(f"Povrede: ne prepoznajem igrača '{r['igrac']}' - proveri ime u tabeli.")
            continue
        tekst, klasa = STATUSI.get(normalizuj(r["status"]), (r["status"].upper() or "STATUS?", "st-up"))
        povrede[igrac_id] = dict(r, bedz=tekst, klasa=klasa)
    return povrede


def ucitaj(igraci):
    tekst = preuzmi_tekst()
    return povezi(procitaj_redove(tekst), igraci) if tekst else {}
