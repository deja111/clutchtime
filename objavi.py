"""
objavi.py
----------
Šalje folder "sajt" na GitHub (GitHub Pages), samo ako ima izmena.

Pokretanje (Command Prompt, iz foldera Projekat):
    python objavi.py

Pre prvog pokretanja folder "sajt" mora jednom da se poveže sa
GitHub repozitorijumom (git init + git remote add - vidi uputstvo).
Rezultat se upisuje i u podaci/log.txt.
"""

import shutil
import subprocess
from datetime import datetime
from pathlib import Path

FOLDER = Path(__file__).parent
SAJT = FOLDER / "sajt"
LOG_FAJL = FOLDER / "podaci" / "log.txt"


def zapisi(poruka):
    linija = f"{datetime.now().strftime('%Y-%m-%d %H:%M')}  {poruka}"
    print(linija)
    with open(LOG_FAJL, "a", encoding="utf-8") as f:
        f.write(linija + "\n")


def nadji_git():
    """Git sa PATH-a, a ako ga tamo nema - sa uobičajenih mesta instalacije."""
    putanja = shutil.which("git")
    if putanja:
        return putanja
    for kandidat in (r"C:\Program Files\Git\cmd\git.exe",
                     r"C:\Program Files (x86)\Git\cmd\git.exe",
                     str(Path.home() / r"AppData\Local\Programs\Git\cmd\git.exe")):
        if Path(kandidat).exists():
            return kandidat
    return "git"


GIT = nadji_git()


def git(*argumenti):
    """Pokrene git komandu u folderu sajt i vrati (uspeh, ispis)."""
    r = subprocess.run([GIT, *argumenti], cwd=SAJT, capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    return r.returncode == 0, (r.stdout + r.stderr).strip()


def main():
    if not (SAJT / ".git").exists():
        zapisi("Objava: folder sajt još nije povezan sa GitHub-om (nema .git). Preskačem.")
        return

    git("add", "--all")
    ima_izmena = not git("diff", "--cached", "--quiet")[0]
    if not ima_izmena:
        zapisi("Objava: nema izmena na sajtu, ništa ne šaljem.")
        return

    poruka = f"Ažuriranje {datetime.now().strftime('%d.%m.%Y. %H:%M')}"
    ok, ispis = git("commit", "-m", poruka)
    if not ok:
        zapisi(f"Objava: GREŠKA pri commit-u: {ispis[-300:]}")
        return

    ok, ispis = git("push", "origin", "main")
    if ok:
        zapisi("Objava: sajt poslat na GitHub.")
    else:
        zapisi(f"Objava: GREŠKA pri slanju na GitHub: {ispis[-300:]}")


if __name__ == "__main__":
    main()
