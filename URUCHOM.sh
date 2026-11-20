#!/usr/bin/env bash
# URUCHOM.sh — macOS / Linux
# Działa po dwukliku na Linuksie i przez: bash URUCHOM.sh

cd "$(dirname "$0")" || exit 1

echo "======================================"
echo "  TESTER PLYTEK - uruchamianie"
echo "======================================"
echo

# 1. znajdz Pythona
if command -v python3 >/dev/null 2>&1; then
    PY=python3
elif command -v python >/dev/null 2>&1; then
    PY=python
else
    echo "BLAD: nie znaleziono Pythona."
    echo
    echo "Zainstaluj go:"
    echo "  macOS:  https://www.python.org/downloads/"
    echo "  Ubuntu: sudo apt install python3 python3-pip python3-tk"
    echo "  Fedora: sudo dnf install python3 python3-pip python3-tkinter"
    echo
    read -r -p "Nacisnij Enter, zeby zamknac..."
    exit 1
fi

echo "Python: $($PY --version 2>&1)"
echo

# 2. sprawdz biblioteki, w razie braku zainstaluj
if ! $PY -c "import customtkinter, PIL" >/dev/null 2>&1; then
    echo "Brakuje bibliotek - instaluje (tylko raz, moze potrwac minute)..."
    echo
    $PY -m pip install --user customtkinter pillow pyserial || {
        echo
        echo "Nie udalo sie zainstalowac. Sprobuj recznie:"
        echo "  $PY -m pip install customtkinter pillow pyserial"
        echo
        read -r -p "Nacisnij Enter, zeby zamknac..."
        exit 1
    }
    echo
fi

# 3. sprawdz tkinter (na Linuksie czesto brakuje)
if ! $PY -c "import tkinter" >/dev/null 2>&1; then
    echo "BLAD: brak tkinter (czesc Pythona, ale w Linuksie osobny pakiet)."
    echo
    echo "  Ubuntu/Debian: sudo apt install python3-tk"
    echo "  Fedora:        sudo dnf install python3-tkinter"
    echo "  Arch:          sudo pacman -S tk"
    echo
    read -r -p "Nacisnij Enter, zeby zamknac..."
    exit 1
fi

# 4. sprawdz pliki
for plik in testuj_plytke.py zdjecie_plytki.png lista_elementow.json; do
    if [ ! -f "$plik" ]; then
        echo "BLAD: brak pliku $plik w tym folderze."
        echo "Wszystkie trzy pliki musza lezec razem."
        echo
        read -r -p "Nacisnij Enter, zeby zamknac..."
        exit 1
    fi
done

# 5. odpal
echo "Uruchamiam program..."
echo
$PY testuj_plytke.py

# 6. nie zamykaj okna jesli byl blad
if [ $? -ne 0 ]; then
    echo
    echo "Program zakonczyl sie bledem - skopiuj tekst powyzej."
    read -r -p "Nacisnij Enter, zeby zamknac..."
fi
