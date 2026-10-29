"""
preuzmi_kolo.py
----------------
Preuzima statistiku svih igrača za jedno odigrano kolo Evrolige
i čuva je u CSV fajl (otvara se i u Excelu).

Primeri pokretanja (u Command Prompt-u, iz foldera gde je skripta):
    python preuzmi_kolo.py                  -> pita te za sezonu i kolo
    python preuzmi_kolo.py 2026 1           -> sezona 2026-27, kolo 1
    python preuzmi_kolo.py 2025 34          -> sezona 2025-26, kolo 34

Izvor podataka: javni (nezvanični, nedokumentovani) API koji koristi
sajt Evrolige. Podaci su vlasništvo Euroleague Basketball-a.
Koristi ih umereno (skripta pravi pauzu između zahteva).
"""

import csv
import sys
import time
from pathlib import Path

import requests

TAKMICENJE = "E"           # "E" = Evroliga, "U" = Evrokup
PAUZA_SEKUNDE = 1.0        # pauza između zahteva, da ne opterećujemo server
FOLDER_ZA_CSV = Path(__file__).parent / "podaci"

URL_UTAKMICE_KOLA = "https://api-live.euroleague.net/v2/competitions/{tak}/seasons/{tak}{sezona}/games"
URL_BOXSCORE = "https://live.euroleague.net/api/Boxscore"

ZAGLAVLJE = {
    "Accept": "application/json",
    "User-Agent": "evroliga-statistika-hobi-projekat/1.0",
}

# Redosled i nazivi kolona u CSV fajlu: (naš naziv, naziv u API-ju)
KOLONE_STATISTIKE = [
    ("poeni", "Points"),
    ("sut2_pogodjeno", "FieldGoalsMade2"),
    ("sut2_pokusano", "FieldGoalsAttempted2"),
    ("sut3_pogodjeno", "FieldGoalsMade3"),
    ("sut3_pokusano", "FieldGoalsAttempted3"),
    ("slobodna_pogodjeno", "FreeThrowsMade"),
    ("slobodna_pokusano", "FreeThrowsAttempted"),
    ("skokovi_napad", "OffensiveRebounds"),
    ("skokovi_odbrana", "DefensiveRebounds"),
    ("skokovi_ukupno", "TotalRebounds"),
    ("asistencije", "Assistances"),
    ("ukradene", "Steals"),
    ("izgubljene", "Turnovers"),
    ("blokade", "BlocksFavour"),
    ("primljene_blokade", "BlocksAgainst"),
    ("licne_greske", "FoulsCommited"),
    ("iznudjene_greske", "FoulsReceived"),
    ("plus_minus", "Plusminus"),
    ("pir", "Valuation"),
]


def preuzmi_json(url, parametri):
    """Pošalje zahtev serveru i vrati odgovor kao Python rečnik."""
    odgovor = requests.get(url, params=parametri, headers=ZAGLAVLJE, timeout=60)
    odgovor.raise_for_status()  # prijavi grešku ako server ne vrati 200 OK
    return odgovor.json()


def minuti_u_broj(tekst):
    """'26:52' -> 26.87 ; 'DNP' ili prazno -> 0.0"""
    if not tekst or ":" not in str(tekst):
        return 0.0
    minuti, sekunde = str(tekst).split(":")
    return round(int(minuti) + int(sekunde) / 60, 2)


def utakmice_kola(sezona, kolo):
    """Vrati listu odigranih utakmica u kolu (šifra utakmice, timovi, datum)."""
    url = URL_UTAKMICE_KOLA.format(tak=TAKMICENJE, sezona=sezona)
    podaci = preuzmi_json(url, {"roundNumber": kolo})

    utakmice = []
    for u in podaci.get("data", []):
        if not u.get("played"):
            continue  # preskoči utakmice koje još nisu odigrane
        utakmice.append({
            "sifra": u["gameCode"],
            "datum": (u.get("date") or "")[:10],
            "faza": (u.get("phaseType") or {}).get("code", ""),
            "domacin": u["local"]["club"]["code"],
            "gost": u["road"]["club"]["code"],
            "rezultat": f'{u["local"]["score"]}:{u["road"]["score"]}',
        })
    return sorted(utakmice, key=lambda x: x["sifra"])


def igraci_utakmice(sezona, kolo, utakmica):
    """Vrati listu redova (jedan red = jedan igrač) za jednu utakmicu."""
    boxscore = preuzmi_json(URL_BOXSCORE, {
        "gamecode": utakmica["sifra"],
        "seasoncode": f"{TAKMICENJE}{sezona}",
    })

    redovi = []
    for tim in boxscore.get("Stats", []):
        for p in tim.get("PlayersStats", []):
            tim_kod = p.get("Team", "").strip()
            je_domacin = tim_kod == utakmica["domacin"]
            red = {
                "sezona": f"{sezona}-{str(sezona + 1)[-2:]}",
                "kolo": kolo,
                "faza": utakmica["faza"],
                "sifra_utakmice": utakmica["sifra"],
                "datum": utakmica["datum"],
                "tim": tim_kod,
                "protivnik": utakmica["gost"] if je_domacin else utakmica["domacin"],
                "domacin": 1 if je_domacin else 0,
                "rezultat": utakmica["rezultat"],
                "igrac_id": (p.get("Player_ID") or "").strip(),
                "igrac": " ".join((p.get("Player") or "").split()),
                "broj": p.get("Dorsal", ""),
                "starter": p.get("IsStarter", 0),
                "igrao": 0 if p.get("Minutes") == "DNP" else 1,
                "minuti": minuti_u_broj(p.get("Minutes")),
            }
            for nas_naziv, api_naziv in KOLONE_STATISTIKE:
                vrednost = p.get(api_naziv)
                red[nas_naziv] = "" if vrednost is None else vrednost
            redovi.append(red)
    return redovi


def sacuvaj_csv(redovi, putanja):
    putanja.parent.mkdir(parents=True, exist_ok=True)
    # "utf-8-sig" da bi Excel ispravno prikazao naša slova (č, ć, š...)
    with open(putanja, "w", newline="", encoding="utf-8-sig") as f:
        pisac = csv.DictWriter(f, fieldnames=list(redovi[0].keys()))
        pisac.writeheader()
        pisac.writerows(redovi)


def procitaj_argumente():
    """Sezonu i kolo uzmi iz komandne linije, a ako ih nema - pitaj korisnika."""
    if len(sys.argv) >= 3:
        return int(sys.argv[1]), int(sys.argv[2])
    print("Sezona se upisuje kao godina početka (npr. 2026 za sezonu 2026-27).")
    sezona = int(input("Sezona: ").strip())
    kolo = int(input("Kolo: ").strip())
    return sezona, kolo


def main():
    sezona, kolo = procitaj_argumente()
    print(f"\nTražim utakmice: sezona {sezona}-{str(sezona + 1)[-2:]}, kolo {kolo}...")

    utakmice = utakmice_kola(sezona, kolo)
    if not utakmice:
        print("Nema odigranih utakmica za to kolo. Proveri sezonu i broj kola.")
        return

    svi_redovi = []
    for i, u in enumerate(utakmice, start=1):
        print(f"  [{i}/{len(utakmice)}] {u['domacin']} - {u['gost']} {u['rezultat']}")
        try:
            svi_redovi.extend(igraci_utakmice(sezona, kolo, u))
        except Exception as greska:
            print(f"     ! Nisam uspeo da preuzmem ovu utakmicu: {greska}")
        time.sleep(PAUZA_SEKUNDE)

    if not svi_redovi:
        print("Nije preuzet nijedan red podataka.")
        return

    putanja = FOLDER_ZA_CSV / f"statistika_{TAKMICENJE}{sezona}_kolo{kolo:02d}.csv"
    sacuvaj_csv(svi_redovi, putanja)
    print(f"\nGotovo! Sačuvano {len(svi_redovi)} redova u fajl:\n  {putanja}")


if __name__ == "__main__":
    main()
