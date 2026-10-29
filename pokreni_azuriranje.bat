@echo off
REM Azurira bazu Evrolige, pravi najavu kola i sajt, pa ga salje na GitHub (koristi ga Task Scheduler)
cd /d "%~dp0"
python azuriraj_bazu.py
python analiza.py
python sajt.py
python objavi.py
