# Projekat: clutchtime (sajt "ClutchTime", ranije "EuroCourt") – statistika i propovi Evrolige

Vlasnik: Dejan (GitHub: deja111, repozitorijum `deja111/clutchtime`, privatan).
Komuniciraj na srpskom (latinica). Sav tekst na sajtu je na srpskom, latinica.

## Šta projekat radi

Python generator statičkog sajta. Podaci idu u SQLite bazu, iz baze se pravi HTML,
a Vercel ga objavljuje.

| Fajl | Uloga |
|---|---|
| `azuriraj_bazu.py` | Puni `podaci/evroliga.db` iz nezvaničnog Evroliga API-ja (`api-live.euroleague.net/v2`, box score sa `live.euroleague.net/api/Boxscore`). Tekuća + 3 prethodne sezone, inkrementalno. Greške beleži u `podaci/log.txt` i nastavlja. |
| `povrede.py` | Čita Dejanovu Google tabelu sa povredama (objavljen CSV, URL u fajlu) i povezuje imena sa `igrac_id`. Rezerva: `podaci/povrede_poslednje.csv`. |
| `analiza.py` | Najava narednog kola: forma (5 utakmica), trend minutaže, kod kuće/u gostima, protiv protivnika, šta protivnik dozvoljava po poziciji, automatski rezime. |
| `sajt.py` | Pravi ceo sajt u `sajt/` (index, najava, lideri, igraci, igrac/<id>, timovi, tim/<sifra>, utakmica/<id>). Koristi funkcije iz `analiza.py`. |
| `preuzmi_kolo.py` | Stari pomoćni alat (CSV jednog kola). |
| `objavi.py`, `pokreni_azuriranje.bat` | ZASTARELO (stari GitHub Pages + Task Scheduler). Ne pokretati. |
| `istrazi_oddspapi.py` | Jednokratno istraživanje OddsPapi odgovora (vidi dole). `--pregled` ponovo ispiše nalaze bez zahteva. |
| `kvote.py` | Kvote za propove igrača (superbet.rs) → `podaci/kvote/kvote_poslednje.json` + `arhiva/`. Zove API samo dan utakmice/dan pre, najviše 2x dnevno (`pozivi.json`). `--sada`, `--fajl X` (obrada bez poziva). Bez ključa samo preskoči. |

Tabele u bazi: `timovi`, `utakmice` (sezona 2026 = 2026-27, `odigrana` 0/1), `igraci`, `statistika` (jedan red = igrač na utakmici).

## Automatizacija i objava

- `.github/workflows/azuriranje.yml`: cron `0 7`, `0 14`, `0 18` UTC (8h/15h/19h zimi u Srbiji) + ručno "Run workflow".
  Redom: `azuriraj_bazu.py` → `analiza.py` → `sajt.py` → commit `podaci/evroliga.db`, `podaci/povrede_poslednje.csv`, `sajt/` → push.
  Poslednji korak pada (crveni X + mejl) ako u logu ima grešaka, ali tek posle objave.
- Python 3.12, `TZ=Europe/Belgrade`, zavisnosti u `requirements.txt` (samo `requests`).
- Vercel: projekat `clutchtime`, Root Directory = `sajt`, preset Other, bez build komande. Svaki push na `main` = nova objava.

## Pravila za rad

- Na početku uvek `git pull`, jer GitHub Actions sam commituje bazu i sajt.
- `sajt/` je generisan: nikad ga ne menjaj ručno, menjaj `sajt.py` / `analiza.py`.
- `sajt.py` briše SVE u `sajt/` pri svakom pokretanju, pa tamo ne stavljaj konfiguracione fajlove (npr. `vercel.json`).
- Pre commita pokreni `python analiza.py` i `python sajt.py` lokalno da proveriš da rade.
- Tajne (OddsPapi ključ) nikad u kod, chat ili commit. Lokalno: `set ODDSPAPI_KEY=...` u CMD-u. Na GitHub-u: Secret `ODDSPAPI_KEY`.
- Dejan radi na Windowsu (CMD), nije programer: objašnjavaj kratko, korak po korak.

## Sledeća velika funkcija: propovi kola (OddsPapi)

Cilj: stranica "Propovi kola". Linije i kvote iz OddsPapi-ja, model računa verovatnoću prelaska,
rang po prednosti (edge), a ne samo po verovatnoći.

OddsPapi pravila (besplatan plan, 250 zahteva mesečno):
- 1 poziv plaćenog endpointa = 1 zahtev, bez obzira na veličinu odgovora. I greške (4xx/5xx) se naplaćuju.
- Besplatno: `/v4/account` (stanje: `request_count`, `request_limit`) i `/v4/historical-odds`.
- `/v4/odds-by-tournaments?tournamentIds=...&bookmakers=...` (do 3 kladionice) vraća celo kolo u jednom pozivu. Pauza bar 1 s između poziva.
- Uslovi: zabranjena preprodaja/redistribucija podataka kao samostalnog proizvoda. Prikaz uz sopstvenu analizu verovatno OK; Dejan treba mejlom da potvrdi kod OddsPapi-ja.

Plan štednje za `kvote.py` (još nije napisan):
- Zovi samo na dan utakmice ili dan pre (raspored iz baze, besplatno), najviše 2 puta dnevno.
- Pre poziva proveri `/v4/account`; ne zovi ako je potrošeno 200+.
- Bez ponavljanja neuspelih poziva. Odgovor sačuvaj u repo, a sajt i model rade iz fajla.
- ID Evrolige i spisak marketa preuzeti jednom i čuvati.
- Očekivano oko 25 zahteva mesečno.

Model (plan): ponderisan prosek (skorije utakmice više vrede) + trend minutaže + šta protivnik dozvoljava po poziciji
(postoji u `analiza.py`) + kod kuće/u gostima → raspodela → P(preko linije). Poređenje sa implicitnom verovatnoćom
kvote (1/kvota, bez marže kladionice) → edge. Označiti igrače iz tabele povreda. Kalibracija na besplatnim istorijskim kvotama.
Na stranici: oznaka 18+ i napomena da je to analiza, a ne savet za klađenje.

Nalazi iz `istrazi_oddspapi.py` (30.10.2026, pravi odgovori u `podaci/oddspapi/`):
- Evroliga `tournamentId = 138`, košarka `sportId = 11`. Katalog marketa sačuvan (`marketi_*.json`, 8883 marketa, 440 za igrače).
- `/v4/odds-by-tournaments` traži TAČNO JEDNU kladionicu: parametar `bookmaker` (jednina). Inače 400 (i naplati se).
- `/v4/odds?fixtureId=...` vraća sve kladionice (~250) za jedan meč, 1 zahtev. Dobro za proveru pokrivenosti.
- `/v4/account` vraća i `api_key`: pre snimanja obavezno ukloniti (`bez_kljuca()` u skripti). `nalog_*.json` su u `.gitignore`.
- Pinnacle NEMA propove igrača za Evroligu (samo ishod, hendikep, ukupno). Srpske: samo `superbet.rs` ima propove
  (mozzartbet, maxbet.rs, admiralbet.rs, balkanbet.rs nemaju; soccerbet.rs i meridianbet nisu na meču).
  Najviše propova: `betano` (sve varijante). `bet365` ima samo "lestvice" (10+, 15+, 20+...), ne preko/ispod.
- Format preko/ispod: `marketType` u katalogu, npr. `playertotals-points`, `-rebounds`, `-assists`, `-ptsassreb`, `-ptsreb`,
  `-ptsass`, `-3pointers`. Svaka linija je poseban market ID; linija je `handicap` u katalogu (npr. 14.5), a ishodi
  Over/Under su `outcomeId` iz kataloga (`outcomeName`). `bookmakerOutcomeId` je interni ID kladionice, NIJE linija.
- U `players` ključ je ID igrača kod OddsPapi-ja, a `playerName` je "Prezime, Ime" (kao u našoj bazi). Gledati `active`
  (neaktivne kvote preskočiti). Prosto uparivanje preko `normalizuj()` je uspelo za 14 od 16 imena; ne uspeva za imena
  bez zareza ("McKinley Wright") i za igrače kojih nema u bazi.

## Otvoreni zadaci

- [x] Pokrenuti `istrazi_oddspapi.py` (30.10.2026).
- [x] `kvote.py` + korak u workflow (30.10.2026). Kladionica: samo `superbet.rs` (Dejanova odluka).
- [ ] Dodati Secret `ODDSPAPI_KEY` na GitHub (dok ga nema, korak kvota samo preskoči).
- [ ] Model (P(preko linije), edge) i stranica "Propovi kola". Superbet ima više linija po igraču/tipu:
      glavna linija = ona sa kvotama najbližim jedna drugoj.
- [ ] Izmene iz `izmene.txt` (naziv sajta, CSS, meni, ukloniti "napravljeno…" ispod najave, forma igrača i utakmice u meni).
- [ ] Podnožje svake stranice: nije zvanično povezano sa Evroligom, podaci su vlasništvo Euroleague Basketball-a, 18+.
- [ ] Ukloniti iz git-a ono što je ostalo pre `.gitignore`: `git rm -r --cached "Claude outputs" __pycache__`.
- [ ] Isključiti stari GitHub Pages repozitorijum i Task Scheduler zadatke (proveriti sa Dejanom).
- [ ] Kasnije: poređenje dva igrača, percentili po poziciji, Vercel Web Analytics, engleska verzija.
