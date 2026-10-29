# Prelazak na Vercel + GitHub Actions

Posle ovoga sajt se ažurira sam na GitHub serverima (8h, 15h, 19h), a Vercel ga
objavljuje. Tvoj računar više ne mora da bude upaljen.

## 1. Pripremi folder Projekat

1. Raspakuj ovaj ZIP direktno u folder `Projekat`, tako da `.github`,
   `requirements.txt`, `.gitignore` i ovo uputstvo budu pored `sajt.py`.
2. Obriši skriveni folder `sajt\.git` (u Exploreru: View → Show → Hidden items).
   To je stara veza sa GitHub Pages repozitorijumom. Od sada ceo projekat
   ide u jedan repozitorijum, a dva ugnježdena repozitorijuma ne rade zajedno.
3. U Task Scheduler-u isključi (Disable) zadatke koji pokreću
   `pokreni_azuriranje.bat`. Tu ulogu sada preuzima GitHub.

## 2. Napravi novi PRIVATNI repozitorijum na GitHub-u

1. github.com → New repository → ime npr. `eurocourt` → izaberi **Private** →
   ne dodaj README → Create.
2. U Command Prompt-u, iz foldera `Projekat` (umesto KORISNIK upiši svoj nalog):

```
git init
git add .
git commit -m "Prvi unos projekta"
git branch -M main
git remote add origin https://github.com/KORISNIK/eurocourt.git
git push -u origin main
```

## 3. Probno pokretanje

1. U repozitorijumu otvori karticu **Actions** → levo izaberi
   **Ažuriranje sajta** → **Run workflow**.
2. Posle 1-3 minuta treba da se pojavi zelena kvačica.
3. Ako je crveni X, klikni na korak koji je pao i pogledaj poruku:
   - **"Ažuriraj bazu"** prijavljuje 403 ili greške u sezoni: Evroliga API ne
     prihvata zahteve sa GitHub servera. Javi mi, postoji zaobilazno rešenje.
   - **"Sačuvaj bazu i sajt"** prijavljuje 403 kod `git push`: Settings → Actions →
     General → Workflow permissions → izaberi **Read and write permissions** → Save.
   - **"Provera grešaka"**: sajt je objavljen, ali je nešto usput preskočeno
     (npr. Google tabela nije bila dostupna). Detalji su u istom koraku.

GitHub ti šalje mejl svaki put kad ažuriranje ne uspe.

## 4. Poveži Vercel

1. vercel.com → Sign up → **Continue with GitHub**.
2. **Add New → Project** → kod `eurocourt` klikni **Import** (ako ga ne vidiš:
   "Adjust GitHub App Permissions" i dozvoli pristup tom repozitorijumu).
3. Podešavanja pre objave:
   - **Framework Preset:** Other
   - **Root Directory:** `sajt`  ← najvažnije
   - Build Command i Output Directory ostavi prazne
4. **Deploy**. Za minut dobijaš adresu tipa `eurocourt-xxxx.vercel.app`.
5. Lepše ime: Project → Settings → Domains → izmeni na npr. `eurocourt.vercel.app`
   (ako je slobodno) ili kasnije dodaj svoj domen.

Od sada svako ažuriranje sa GitHub-a automatski ide na Vercel.

## 5. Ugasi stari sajt

U starom repozitorijumu (onom za GitHub Pages): Settings → Pages → isključi
objavu, ili arhiviraj/obriši ceo repozitorijum. Tako neće postojati dva sajta
i niko neće videti stari link sa tvojim nalogom.

## Nova svakodnevna rutina

- Povrede upisuješ u Google tabelu kao i do sada.
- Sajt se osveži sam u 8h, 15h i 19h (leti sat kasnije).
- Kad ti treba odmah: GitHub (i u mobilnoj aplikaciji) → repozitorijum →
  Actions → Ažuriranje sajta → Run workflow. To zamenjuje `pokreni_azuriranje.bat`.

## Kad menjaš kod na računaru

GitHub sada sam dodaje izmene (novu bazu i sajt), pa uvek PRVO povuci najnovije:

```
git pull
```

pa tek onda menjaj fajlove, i na kraju:

```
git add .
git commit -m "Opis izmene"
git push
```

`objavi.py` i `pokreni_azuriranje.bat` više nisu potrebni za objavu. Mogu da
ostanu u folderu, ali ih ne pokreći, jer bi slali sajt na stari repozitorijum.
