"""
azuriraj_bazu.py
-----------------
Puni i osvežava SQLite bazu sa podacima Evrolige: podaci/evroliga.db

Pokretanje (Command Prompt, iz foldera Projekat):
    python azuriraj_bazu.py

Prvo pokretanje preuzima tekuću i 3 prethodne sezone (20-30 minuta).
Svako sledeće pokretanje dodaje samo ono što je novo (obično par sekundi).
Skripta se može prekinuti (Ctrl+C) u bilo kom trenutku: sledeći put
nastavlja tamo gde je stala.

Tabele:
    timovi     - šifra i naziv tima (RED = Crvena Zvezda)
    utakmice   - sve utakmice sezone, odigrane (odigrana=1) i zakazane (0)
    igraci     - igrači: ime, pozicija, visina, datum rođenja, država
    statistika - jedan red = jedan igrač na jednoj utakmici

Izvor: javni (nezvanični) API sajta Evrolige. Podaci su vlasništvo
Euroleague Basketball-a.
"""

import logging
import sqlite3
import time
from datetime import date
from pathlib import Path

import requests

# ----------------------------- PODEŠAVANJA -----------------------------
TAKMICENJE = "E"           # "E" = Evroliga
PRETHODNIH_SEZONA = 3      # koliko sezona unazad preuzimamo
PAUZA_SEKUNDE = 1.0        # pauza između zahteva, da ne opterećujemo server

FOLDER = Path(__file__).parent / "podaci"
BAZA = FOLDER / "evroliga.db"
LOG_FAJL = FOLDER / "log.txt"

API = "https://api-live.euroleague.net/v2/competitions/" + TAKMICENJE
URL_BOXSCORE = "https://live.euroleague.net/api/Boxscore"
ZAGLAVLJE = {
    "Accept": "application/json",
    "User-Agent": "evroliga-statistika-hobi-projekat/1.0",
}

# Kolone statistike: (naziv u bazi, naziv u API-ju)
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

STRUKTURA_BAZE = f"""
CREATE TABLE IF NOT EXISTS utakmice (
    sezona          INTEGER NOT NULL,   -- 2026 = sezona 2026-27
    sifra_utakmice  INTEGER NOT NULL,
    kolo            INTEGER,
    faza            TEXT,               -- RS, PI, PO, FF
    datum           TEXT,               -- 2026-09-25 20:45 (lokalno vreme)
    domacin         TEXT,
    gost            TEXT,
    poeni_domacin   INTEGER,            -- prazno dok se ne odigra
    poeni_gost      INTEGER,
    odigrana        INTEGER NOT NULL,   -- 1 = odigrana, 0 = zakazana
    PRIMARY KEY (sezona, sifra_utakmice)
);

CREATE TABLE IF NOT EXISTS igraci (
    igrac_id         TEXT PRIMARY KEY,  -- npr. P010568
    ime              TEXT,
    pozicija         TEXT,              -- Guard / Forward / Center
    visina           INTEGER,           -- cm
    datum_rodjenja   TEXT,
    drzava           TEXT,
    poslednja_sezona INTEGER,           -- iz koje sezone su podaci
    broj             TEXT               -- broj na dresu (poslednji poznat)
);

CREATE TABLE IF NOT EXISTS statistika (
    sezona          INTEGER NOT NULL,
    sifra_utakmice  INTEGER NOT NULL,
    igrac_id        TEXT NOT NULL,
    tim             TEXT,
    protivnik       TEXT,
    domacin         INTEGER,            -- 1 = igrao kod kuće
    starter         INTEGER,
    igrao           INTEGER,            -- 0 = DNP
    minuti          REAL,
    {", ".join(f"{naziv} INTEGER" for naziv, _ in KOLONE_STATISTIKE)},
    PRIMARY KEY (sezona, sifra_utakmice, igrac_id)
);

CREATE TABLE IF NOT EXISTS timovi (
    sifra       TEXT PRIMARY KEY,       -- npr. RED
    naziv       TEXT,                   -- Crvena Zvezda
    puni_naziv  TEXT                    -- Crvena Zvezda Meridianbet Belgrade
);

CREATE INDEX IF NOT EXISTS idx_stat_igrac ON statistika (igrac_id);
CREATE INDEX IF NOT EXISTS idx_utakmice_datum ON utakmice (datum);
"""


# ----------------------------- POMOĆNE FUNKCIJE -----------------------------
def preuzmi_json(url, parametri=None):
    """Pošalje zahtev serveru (do 3 pokušaja) i vrati odgovor kao rečnik."""
    for pokusaj in range(1, 4):
        try:
            odgovor = requests.get(url, params=parametri, headers=ZAGLAVLJE, timeout=60)
            if odgovor.status_code == 429 and pokusaj < 3:
                # "Previše zahteva": server traži da usporimo - sačekaj pa probaj ponovo
                cekaj = odgovor.headers.get("Retry-After", "")
                cekaj = int(cekaj) if cekaj.isdigit() else 60 * pokusaj
                logging.warning(f"   Server javlja 'previše zahteva', čekam {cekaj} s...")
                time.sleep(min(cekaj, 300))
                continue
            odgovor.raise_for_status()
            return odgovor.json()
        except requests.RequestException:
            if pokusaj == 3:
                raise
            time.sleep(5 * pokusaj)
        finally:
            time.sleep(PAUZA_SEKUNDE)


def minuti_u_broj(tekst):
    """'26:52' -> 26.87 ; 'DNP' ili prazno -> 0.0"""
    if not tekst or ":" not in str(tekst):
        return 0.0
    minuti, sekunde = str(tekst).split(":")
    return round(int(minuti) + int(sekunde) / 60, 2)


def tekuca_sezona():
    """Sezona počinje u jesen: od avgusta važi nova sezona."""
    danas = date.today()
    return danas.year if danas.month >= 8 else danas.year - 1


def oznaka(sezona):
    return f"{sezona}-{str(sezona + 1)[-2:]}"


# ----------------------------- KORACI -----------------------------
def osvezi_utakmice(baza, sezona):
    """Preuzme ceo raspored sezone i upiše/osveži tabelu utakmice."""
    podaci = preuzmi_json(f"{API}/seasons/{TAKMICENJE}{sezona}/games")
    for u in podaci.get("data", []):
        odigrana = 1 if u.get("played") else 0
        baza.execute(
            """INSERT INTO utakmice VALUES (?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT (sezona, sifra_utakmice) DO UPDATE SET
                 kolo=excluded.kolo, faza=excluded.faza, datum=excluded.datum,
                 domacin=excluded.domacin, gost=excluded.gost,
                 poeni_domacin=excluded.poeni_domacin, poeni_gost=excluded.poeni_gost,
                 odigrana=excluded.odigrana""",
            (
                sezona,
                u["gameCode"],
                u.get("round"),
                (u.get("phaseType") or {}).get("code"),
                (u.get("date") or "")[:16].replace("T", " "),
                u["local"]["club"]["code"],
                u["road"]["club"]["code"],
                u["local"].get("score") if odigrana else None,
                u["road"].get("score") if odigrana else None,
                odigrana,
            ),
        )
        for strana in ("local", "road"):
            klub = u[strana]["club"]
            baza.execute(
                "INSERT OR REPLACE INTO timovi VALUES (?,?,?)",
                (klub["code"], klub.get("abbreviatedName") or klub.get("name"), klub.get("name")),
            )
    baza.commit()


def preuzmi_statistiku_utakmice(baza, sezona, sifra, domacin, gost):
    """Preuzme box score jedne utakmice i upiše igrače u tabelu statistika."""
    boxscore = preuzmi_json(URL_BOXSCORE, {
        "gamecode": sifra,
        "seasoncode": f"{TAKMICENJE}{sezona}",
    })
    if boxscore.get("Live"):
        return 0  # utakmica je još u toku, uzećemo je sledeći put
    broj = 0
    for tim in boxscore.get("Stats") or []:
        for p in tim.get("PlayersStats") or []:
            igrac_id = (p.get("Player_ID") or "").strip()
            if not igrac_id:
                continue
            tim_kod = (p.get("Team") or "").strip()
            je_domacin = tim_kod == domacin
            vrednosti = [
                sezona, sifra, igrac_id, tim_kod,
                gost if je_domacin else domacin,
                1 if je_domacin else 0,
                p.get("IsStarter", 0),
                0 if p.get("Minutes") == "DNP" else 1,
                minuti_u_broj(p.get("Minutes")),
            ] + [p.get(api_naziv) for _, api_naziv in KOLONE_STATISTIKE]
            baza.execute(
                f"INSERT OR REPLACE INTO statistika VALUES ({','.join('?' * len(vrednosti))})",
                vrednosti,
            )
            # Ako igrač još nije u tabeli igraci, upiši bar ime
            baza.execute(
                "INSERT OR IGNORE INTO igraci (igrac_id, ime) VALUES (?, ?)",
                (igrac_id, " ".join((p.get("Player") or "").split())),
            )
            broj += 1
    baza.commit()
    return broj


def osvezi_igrace(baza, sezona):
    """Preuzme spiskove igrača svih timova u sezoni (pozicija, visina...)."""
    timovi = [r[0] for r in baza.execute(
        "SELECT domacin FROM utakmice WHERE sezona=? UNION SELECT gost FROM utakmice WHERE sezona=?",
        (sezona, sezona))]
    for tim in timovi:
        try:
            podaci = preuzmi_json(f"{API}/seasons/{TAKMICENJE}{sezona}/clubs/{tim}/people")
        except Exception as greska:
            logging.warning(f"   Spisak igrača za {tim} nije preuzet: {greska}")
            continue
        clanovi = podaci if isinstance(podaci, list) else podaci.get("data", [])
        for c in clanovi:
            if c.get("typeName") != "Player":
                continue
            osoba = c.get("person") or {}
            if not osoba.get("code"):
                continue
            baza.execute(
                """INSERT INTO igraci (igrac_id, ime, pozicija, visina, datum_rodjenja, drzava,
                                      poslednja_sezona, broj) VALUES (?,?,?,?,?,?,?,?)
                   ON CONFLICT (igrac_id) DO UPDATE SET
                     ime=excluded.ime, pozicija=excluded.pozicija, visina=excluded.visina,
                     datum_rodjenja=excluded.datum_rodjenja, drzava=excluded.drzava,
                     poslednja_sezona=excluded.poslednja_sezona, broj=excluded.broj
                   WHERE igraci.poslednja_sezona IS NULL
                      OR excluded.poslednja_sezona >= igraci.poslednja_sezona""",
                (
                    "P" + osoba["code"].strip(),
                    osoba.get("name"),
                    c.get("positionName"),
                    osoba.get("height") or None,
                    (osoba.get("birthDate") or "")[:10] or None,
                    (osoba.get("country") or {}).get("code"),
                    sezona,
                    (str(c.get("dorsal")).strip() or None) if c.get("dorsal") is not None else None,
                ),
            )
        baza.commit()


def obradi_sezonu(baza, sezona, tekuca):
    logging.info(f"Sezona {oznaka(sezona)}")

    # 1) Raspored: tekuću sezonu osvežavamo uvek, stare samo prvi put
    vec_ima = baza.execute("SELECT COUNT(*) FROM utakmice WHERE sezona=?", (sezona,)).fetchone()[0]
    if sezona == tekuca or vec_ima == 0:
        osvezi_utakmice(baza, sezona)

    # 2) Statistika za odigrane utakmice koje još nemamo
    nove = baza.execute(
        """SELECT u.sifra_utakmice, u.domacin, u.gost, u.kolo FROM utakmice u
           WHERE u.sezona=? AND u.odigrana=1
             AND NOT EXISTS (SELECT 1 FROM statistika s
                             WHERE s.sezona=u.sezona AND s.sifra_utakmice=u.sifra_utakmice)
           ORDER BY u.sifra_utakmice""", (sezona,)).fetchall()
    if nove:
        logging.info(f"   Novih utakmica za preuzimanje: {len(nove)}")
    for i, (sifra, domacin, gost, kolo) in enumerate(nove, start=1):
        try:
            broj = preuzmi_statistiku_utakmice(baza, sezona, sifra, domacin, gost)
            logging.info(f"   [{i}/{len(nove)}] kolo {kolo}: {domacin} - {gost} ({broj} igrača)")
        except Exception as greska:
            logging.warning(f"   [{i}/{len(nove)}] {domacin} - {gost} NIJE preuzeta: {greska}")

    # 3) Podaci o igračima: samo ako u ovoj sezoni ima novih igrača
    #    za koje još nismo proverili spiskove timova
    uslov = """igrac_id IN (SELECT igrac_id FROM statistika WHERE sezona=:s)
               AND pozicija IS NULL
               AND (poslednja_sezona IS NULL OR poslednja_sezona < :s)"""
    fali = baza.execute(f"SELECT COUNT(*) FROM igraci WHERE {uslov}", {"s": sezona}).fetchone()[0]
    if fali:
        logging.info(f"   Osvežavam podatke o igračima ({fali} novih)")
        osvezi_igrace(baza, sezona)
        # Igrače kojih nema na spiskovima označi kao proverene,
        # da ih ne bismo tražili pri svakom pokretanju
        baza.execute(f"UPDATE igraci SET poslednja_sezona=:s WHERE {uslov}", {"s": sezona})
        baza.commit()


def kratak_izvestaj(baza):
    logging.info("Stanje baze:")
    for sezona, ukupno, odigrano, redova in baza.execute(
        """SELECT u.sezona, COUNT(*), SUM(u.odigrana),
                  (SELECT COUNT(*) FROM statistika s WHERE s.sezona=u.sezona)
           FROM utakmice u GROUP BY u.sezona ORDER BY u.sezona"""):
        logging.info(f"   {oznaka(sezona)}: {odigrano}/{ukupno} utakmica odigrano, {redova} redova statistike")
    igraca = baza.execute("SELECT COUNT(*), COUNT(pozicija) FROM igraci").fetchone()
    logging.info(f"   Igrača: {igraca[0]} (sa pozicijom: {igraca[1]})")


def main():
    FOLDER.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M",
        handlers=[logging.FileHandler(LOG_FAJL, encoding="utf-8"), logging.StreamHandler()],
    )
    logging.info("=== Početak ažuriranja ===")

    baza = sqlite3.connect(BAZA)
    baza.executescript(STRUKTURA_BAZE)

    # Dopuna starije baze: kolona "broj" (broj na dresu) - jednom, pa osveži spiskove tekuće sezone
    kolone = [r[1] for r in baza.execute("PRAGMA table_info(igraci)")]
    if "broj" not in kolone:
        logging.info("Dopuna baze: dodajem broj na dresu")
        baza.execute("ALTER TABLE igraci ADD COLUMN broj TEXT")
        baza.commit()
        dopuni_brojeve = True
    else:
        dopuni_brojeve = False

    tekuca = tekuca_sezona()
    for sezona in range(tekuca - PRETHODNIH_SEZONA, tekuca + 1):
        try:
            obradi_sezonu(baza, sezona, tekuca)
        except Exception as greska:
            logging.error(f"Greška u sezoni {oznaka(sezona)}: {greska}")

    if dopuni_brojeve:
        osvezi_igrace(baza, tekuca)

    kratak_izvestaj(baza)
    baza.close()
    logging.info("=== Kraj ===\n")


if __name__ == "__main__":
    main()
