# Projekat: clutchtime (sajt "ClutchTime", ranije "EuroCourt") – statistika i granice igrača Evrolige

Vlasnik: Dejan (GitHub: deja111, repozitorijum `deja111/clutchtime`, privatan).
Komuniciraj na srpskom (latinica). Sav tekst na sajtu je na srpskom, latinica.

## Šta projekat radi

Python generator statičkog sajta. Podaci idu u SQLite bazu, iz baze se pravi HTML,
a Vercel ga objavljuje.

| Fajl | Uloga |
|---|---|
| `azuriraj_bazu.py` | Puni `podaci/evroliga.db` iz nezvaničnog Evroliga API-ja (`api-live.euroleague.net/v2`, box score sa `live.euroleague.net/api/Boxscore`). Tekuća + 3 prethodne sezone, inkrementalno. Greške beleži u `podaci/log.txt` i nastavlja. |
| `povrede.py` | Čita Dejanovu Google tabelu sa povredama (objavljen CSV, URL u fajlu) i povezuje imena sa `igrac_id`. Razume i engleske statuse (Out, Game Time Decision...), prevodi razloge i datume. Rezerva: `podaci/povrede_poslednje.csv`. |
| `analiza.py` | Najava narednog kola: forma, trend minutaže, kod kuće/u gostima, protiv protivnika, automatski rezime. CSS sajta (`CSS`). |
| `model.py` | TRENUTNO SE NE KORISTI na sajtu (31.10.2026 Dejan ne želi predikciju modela). Procena za sledeći meč (`procene_kola`) i sve provere ostaju ovde ako se vraća. Detalji ispod. |
| `sajt.py` | Pravi ceo sajt u `sajt/`: index, utakmice, granice, odbrana (kako brani svaki tim, `odbrana_timova`; i sekcija na tim/<sifra>), forma, igraci (+ kartice narednog kola), igrac/<id>, timovi, tim/<sifra>, lideri, utakmica/<id>. `najava.html` i `propovi.html` samo preusmeravaju. |
| `preuzmi_kolo.py` | Stari pomoćni alat (CSV jednog kola). |
| `objavi.py`, `pokreni_azuriranje.bat` | ZASTARELO (stari GitHub Pages + Task Scheduler). Ne pokretati. |

Tabele u bazi: `timovi`, `utakmice` (sezona 2026 = 2026-27, `odigrana` 0/1), `igraci`, `statistika` (jedan red = igrač na utakmici).

## Automatizacija i objava

- `.github/workflows/azuriranje.yml`: cron `23 7`, `23 14`, `23 18` UTC (8:23/15:23/19:23 zimi u Srbiji; ne na pun sat jer GitHub tada preskače) + ručno "Run workflow".
  Redom: `azuriraj_bazu.py` → `analiza.py` → `sajt.py` → commit `podaci/evroliga.db`, `podaci/povrede_poslednje.csv`, `sajt/` → push.
  Poslednji korak pada (crveni X + mejl) ako u logu ima grešaka, ali tek posle objave.
- Python 3.12, `TZ=Europe/Belgrade`, zavisnosti u `requirements.txt` (samo `requests`).
- Vercel: projekat `clutchtime-sajt`, adresa **https://clutchtime-sajt.vercel.app** (adrese pojedinačnih deploymenta prikazuju staru verziju), Root Directory = `sajt`, preset Other, bez build komande. Svaki push na `main` = nova objava.

## Pravila za rad

- Na početku uvek `git pull`, jer GitHub Actions sam commituje bazu i sajt.
- `sajt/` je generisan: nikad ga ne menjaj ručno, menjaj `sajt.py` / `analiza.py`.
- `sajt.py` briše SVE u `sajt/` pri svakom pokretanju, pa tamo ne stavljaj konfiguracione fajlove (npr. `vercel.json`).
- Pre commita pokreni `python analiza.py` i `python sajt.py` lokalno da proveriš da rade.
- Svaku izmenu modela prvo proveri na prethodnim sezonama (procena samo iz ranijih utakmica → poređenje sa stvarnim), pa tek onda uključi.
- Dejan radi na Windowsu (CMD), nije programer: objašnjavaj kratko, korak po korak.

## Stranica Granice (od 31.10.2026) i model (sačuvan, ne prikazuje se)

Koncept: posetilac bira igrača, kategoriju (poeni, skokovi, asistencije, PSA, PS, PA, SA, trojke, ukradene, blokade)
i granicu → vidi prelaske (posl. 5 / 10 / sezona / kod kuće / u gostima / protiv sledećeg protivnika, sve sezone),
poslednjih 10 utakmica i "Prednosti i mane protiv <protivnik>" (`prednosti_i_mane` u sajt.py: činjenice, bez
predviđanja – igračeve jake strane po percentilu (šut za tri, SB, skok u napadu, asistencije, blokade, izgubljene)
naspram onoga što protivnik dozvoljava/brani ove sezone, šta dozvoljava njegovoj poziciji (rang), i ranije protiv tog
tima). Filter "Bez saigrača": prelasci samo u utakmicama kad izabrani saigrač (10+ min) nije igrao (`bez_saigraca`,
maska po utakmici; link dobija 4. deo `#igrac/kat/granica/saigrac`). Procenu modela Dejan NE želi na sajtu (31.10.2026: ne slaže se sa njom, npr. Koloko). Link `granice.html#<igrac_id>/<kategorija>/<granica>`;
sa profila igrača "Proveri granicu →". Podaci su ugrađeni u stranicu, sve računa JS.

Model (`model.py`), sve provereno na 2024-25/2025-26:
- Učinak po minutu i minuti iz POSLEDNJIH 5 utakmica (`UZORAK`, bez prošle sezone – Dejanova odluka; ponderisana
  cela sezona + prošla imala je manju grešku, poeni 5,49 prema 5,78).
- Saigrači (`Saigraci`, `POVRATAK=True`): korekcija = (verovatnoća odsustva sada: ne igra 1, upitan 0,5) −
  (udeo odsustva u poslednjih 5) → i izostanci i povratci. Skale izmerene (`SKALA_MINUTA` 0,35, `SKALA_UCINKA`).
  Poeni 5,822 → 5,765. Usage-raspodela i tempo izmereni, bez koristi, isključeni.
- Očekivana razlika / blowout: rejting timova + 3 za domaćina; starteri gube, klupa dobija minute.
- Protivnik po poziciji SAMO za asistencije i trojke (za poene/skokove/PSA šum). Kod kuće/gosti blago (±6%).
- Negativna binomna (rasipanje ublaženo ka `RASIPANJE_LIGA`) + Platt `KALIBRACIJA` po kategoriji.
- Odmor/back-to-back izmeren: bez efekta (nema domaćeg prvenstva u bazi).

## Istorija: propovi iz kladionice (30.-31.10.2026, UGAŠENO)

Stranica "Propovi kola" sa linijama superbet.rs (OddsPapi), tiket dana i praćenje rezultata. Ugašeno 31.10.2026
na Dejanov zahtev (jedno kolo: Top 10 prošao 2/10, svi predlozi 56% uz +7%). Kod (`kvote.py`, `istrazi_oddspapi.py`,
`istorija_kvota.py`, stranica u `sajt.py`) i podaci (`podaci/kvote/`) obrisani, ostaju u git istoriji
(commit pre "Granice"). Korisno ako se vraća: Evroliga `tournamentId=138`; `/v4/odds-by-tournaments` traži
tačno jednu kladionicu (`bookmaker`); `/v4/account` vraća api_key (ne snimati); Pinnacle nema propove za
Evroligu, od srpskih samo superbet.rs; Betano i bwin najbolje pokrivaju iste propove. GitHub Secret
`ODDSPAPI_KEY` više nije potreban (Dejan može da ga obriše).

## Otvoreni zadaci

- [ ] Podnožje svake stranice: nije zvanično povezano sa Evroligom, podaci su vlasništvo Euroleague Basketball-a.
- [ ] Ukloniti iz git-a ono što je ostalo pre `.gitignore`: `git rm -r --cached "Claude outputs" __pycache__`.
- [ ] Isključiti stari GitHub Pages repozitorijum i Task Scheduler zadatke (proveriti sa Dejanom).
- [ ] Kasnije: poređenje dva igrača, percentili po poziciji, Vercel Web Analytics, engleska verzija.
