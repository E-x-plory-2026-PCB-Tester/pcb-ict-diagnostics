@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Tester Plytek

echo ======================================
echo   TESTER PLYTEK - uruchamianie
echo ======================================
echo.

REM 1. znajdz Pythona
where python >nul 2>nul
if %errorlevel%==0 (
    set PY=python
) else (
    where py >nul 2>nul
    if %errorlevel%==0 (
        set PY=py
    ) else (
        echo BLAD: nie znaleziono Pythona.
        echo.
        echo Zainstaluj go z https://www.python.org/downloads/
        echo Przy instalacji zaznacz "Add Python to PATH".
        echo.
        pause
        exit /b 1
    )
)

for /f "delims=" %%v in ('%PY% --version 2^>^&1') do echo Python: %%v
echo.

REM 2. sprawdz biblioteki
%PY% -c "import customtkinter, PIL" >nul 2>nul
if not %errorlevel%==0 (
    echo Brakuje bibliotek - instaluje ^(tylko raz, moze potrwac minute^)...
    echo.
    %PY% -m pip install customtkinter pillow pyserial
    if not %errorlevel%==0 (
        echo.
        echo Nie udalo sie zainstalowac. Sprobuj recznie:
        echo   %PY% -m pip install customtkinter pillow pyserial
        echo.
        pause
        exit /b 1
    )
    echo.
)

REM 3. sprawdz pliki
if not exist "testuj_plytke.py" (
    echo BLAD: brak pliku testuj_plytke.py
    pause
    exit /b 1
)
if not exist "zdjecie_plytki.png" (
    echo BLAD: brak pliku zdjecie_plytki.png
    pause
    exit /b 1
)
if not exist "lista_elementow.json" (
    echo BLAD: brak pliku lista_elementow.json
    pause
    exit /b 1
)

REM 4. odpal
echo Uruchamiam program...
echo.
%PY% testuj_plytke.py

if not %errorlevel%==0 (
    echo.
    echo Program zakonczyl sie bledem - skopiuj tekst powyzej.
    pause
)
