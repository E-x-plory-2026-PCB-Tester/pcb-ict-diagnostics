<div align="center">

# ICT-SCAN PRO

**Aplikacja Diagnostyczna i Optyczny Inspektor Błędów dla Testera PCB (E(x)plory 2026)**

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)
![GUI](https://img.shields.io/badge/GUI-CustomTkinter-0EA5E9?style=flat-square)
![MCU](https://img.shields.io/badge/MCU-ESP32-E7352C?style=flat-square&logo=espressif&logoColor=white)
![Protocol](https://img.shields.io/badge/USB-JSON%20115200-10B981?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-94A3B8?style=flat-square)

[🇬🇧 English](README.md) | **🇵🇱 Polski**

Część projektu **[E(x)plory 2026 PCB Tester](https://github.com/E-x-plory-2026-PCB-Tester)**  •  Pozostałe moduły: [`ict-firmware`](https://github.com/E-x-plory-2026-PCB-Tester/ict-firmware) · [`ict-jig-gen`](https://github.com/E-x-plory-2026-PCB-Tester/ict-jig-gen)

</div>

---

**ICT-SCAN PRO** to aplikacja komputerowa do niskokosztowej stacji diagnostycznej In-Circuit Test (ICT). Dzięki metodzie porównawczej **Golden Sample** wykrywa błędy montażowe na zlutowanych płytkach bezpiecznym mikroprądem (`< 1 mA`), **zanim zostanie podłączone główne zasilanie**.

![Podgląd aplikacji ICT-SCAN PRO](podglad.png)

---

## Zasada działania

Zamiast mierzyć pojedyncze elementy w izolacji (co na zlutowanej płytce nie działa przez rozpływ prądu po równoległych ścieżkach), program analizuje dwukierunkowe skany (`a→b` oraz `b→a`) na `16` wspólnych igłach (`3,3 V`, `R_ref = 3,3 kΩ`, prąd zwarcia `< 1 mA`):

1. **Kalibracja (`⚙ Kalibruj`):** Mierzy opór własny kabli i multiplekserów (`R_cal`) na zwartej parze igieł i odejmuje go jak tarowanie wagi.
2. **Zapis wzorca (`★ Zapisz wzorzec`):** Zapisuje sygnaturę jednej sprawnej płytki do `wzorzec.json` (wczytuje się automatycznie po starcie).
3. **Test płytek (`▶ Testuj płytkę`):** Porównuje kolejne płytki ze wzorcem w tolerancji `±10%` i nanosi wyniki bezpośrednio na zdjęcie PCB.

### Klasyfikacja wyników

| Status | Warunek | Znaczenie |
| :--- | :--- | :--- |
| `OK` | W granicach tolerancji `±10%` (lub zgodna polaryzacja diody) | Element / ścieżka zgodna ze wzorcem |
| `ZWARCIE` / `ZWARCIE LINII` | Spadek oporu `< 15 Ω` (lub `< 10%` wartości wzorca) | Zwarcie lub mostek cyny (np. na szynie `VCC–GND`) |
| `PRZERWA` | Obwód otwarty (`≥ 3050 mV` na ADC), gdy wzorzec przewodził | Brak styku, przerwana ścieżka lub zimny lut |
| `ZŁA WARTOŚĆ` | Odchyłka rezystancji przekracza `±10%` | Wlutowany rezystor o błędnej wartości |
| `ODWRÓCONA` | Odczyty `a→b / b→a` zamieniły się miejscami względem wzorca | Odwrotnie wlutowana dioda lub LED |
| `PRZEBICIE` | Wzorzec był otwarty, badana płytka przewodzi (`≥ 15 Ω`) | Niepożądane przejście między węzłami |
| `BLISKO GRANICY` | Odchyłka między `±5%` a `±10%` | Wartość na granicy tolerancji |

---

## Główne funkcje

* **Wbudowany Serial Monitor USB:** Nieblokujący odbiornik JSON (`115200` baud, timeout `4,5 s`) z podglądem surowych linii `RX/TX`, ręcznym wysyłaniem komend (`SCAN`, `PING`) i odświeżaniem portów COM (`↻`).
* **Konfigurator pinów (`⚙ Piny`):** Klikasz bezpośrednio na zdjęcie płytki PCB, wybierasz piny `0–15` oraz typ (`element` / `linia`) i zapisujesz prosto do `lista_elementow.json`.
* **Interaktywny podgląd i skalowanie:** Zoom kółkiem myszy (`55%–200%`), przesuwanie płytki, przeciągany podział ekranu, skalowanie tabeli (`85%–130%`), tryb pełnoekranowy tabeli (`⛶ Pełny`).
* **Historia skanów i eksport CSV:** Podgląd ostatnich 10 skanów i automatyczny zapis do `pomiary_raport.csv` (ze średnikiem pod polski Excel).
* **Tryb DEMO:** Wbudowany symulator usterek (`dobra płytka`, `zwarcie`, `zly_rezystor`, `odwrocona_dioda`, `przerwa`) do pracy bez sprzętu.

---

## Instalacja i uruchomienie

### Windows / macOS
```bash
pip install -r requirements.txt
python testuj_plytke.py
```
*(Na Windowsie można też kliknąć dwa razy `URUCHOM_WINDOWS.bat`).*

### Linux (Fedora / Ubuntu / Debian)
Przed uruchomieniem wymagane są pakiety systemowe dla `Tkinter` i `ImageTk`:
* **Fedora:** `sudo dnf install python3-tkinter python3-pillow-tk`
* **Ubuntu / Debian:** `sudo apt install python3-tk python3-pil.imagetk`

```bash
pip3 install -r requirements.txt
python3 testuj_plytke.py
```

---

## Protokół USB i format konfiguracji

Po wysłaniu komendy `SCAN\n` przez USB (`115200` baud) mikrokontroler zwraca jedną linię JSON:
```json
{
  "board_id": "test_01",
  "scan_ms": 850,
  "readings": [
    {"a": 0, "b": 1, "mv": 472},
    {"a": 1, "b": 0, "mv": 474}
  ]
}
```

Format pliku `lista_elementow.json` (generowany też automatycznie przez `ict-jig-gen`):
```json
{
  "elementy": [
    {"nazwa": "R1", "piny": [0, 1], "x": 168, "y": 240, "typ": "element"},
    {"nazwa": "VCC-GND", "piny": [0, 15], "x": 256, "y": 452, "typ": "linia"}
  ]
}
```

## Zawartość repozytorium

| Plik | Opis |
| :--- | :--- |
| `testuj_plytke.py` | Główna aplikacja GUI (`ICT-SCAN PRO`) |
| `lista_elementow.json` | Przykładowa mapa elementów, pinów i współrzędnych (x, y) |
| `zdjecie_plytki.png` | Zdjęcie płytki z góry pod mapę błędów |
| `requirements.txt` | Zależności Pythona (`customtkinter`, `pillow`, `pyserial`) |
| `URUCHOM_WINDOWS.bat` / `URUCHOM.sh` | Skrypty startowe |
| `PRZECZYTAJ.txt` | Krótka instrukcja obsługi dla paczek ZIP |
