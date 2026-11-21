import csv
import datetime
import json
import random
import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont, ImageTk

try:
    import serial
    from serial.tools import list_ports
    MA_SERIAL = True
except ImportError:
    MA_SERIAL = False

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

RESAMPLE = getattr(Image, "Resampling", Image).LANCZOS
_CZCIONKI = {}


def czcionka(rozmiar=14):
    if rozmiar in _CZCIONKI:
        return _CZCIONKI[rozmiar]

    if sys.platform.startswith("win"):
        kandydaci = ["segoeui.ttf", "arialbd.ttf", "arial.ttf", "tahoma.ttf"]
    elif sys.platform == "darwin":
        kandydaci = ["/System/Library/Fonts/Helvetica.ttc",
                     "/System/Library/Fonts/Supplemental/Arial.ttf", "Arial.ttf"]
    else:
        kandydaci = ["DejaVuSans-Bold.ttf", "DejaVuSans.ttf", "LiberationSans-Bold.ttf", "FreeSans.ttf"]

    for nazwa in kandydaci:
        try:
            f = ImageFont.truetype(nazwa, rozmiar)
            _CZCIONKI[rozmiar] = f
            return f
        except OSError:
            continue

    try:
        f = ImageFont.load_default(size=rozmiar)
    except TypeError:
        f = ImageFont.load_default()
    _CZCIONKI[rozmiar] = f
    return f


def odmiana_bledow(n):
    if n == 1:
        return "1 błąd"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return f"{n} błędy"
    return f"{n} błędów"


# ----------------------------------------------------------------------
# 1. USTAWIENIA I PALETA KOLORÓW (Precision Dark Lab)
# ----------------------------------------------------------------------
try:
    FOLDER = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
except NameError:
    FOLDER = Path.cwd()

PLIK_ZDJECIE = FOLDER / "zdjecie_plytki.png"
PLIK_ELEMENTY = FOLDER / "lista_elementow.json"
PLIK_WZORZEC = FOLDER / "wzorzec.json"
PLIK_CSV = FOLDER / "pomiary_raport.csv"

VCC_MV = 3300.0
R_REF = 3300.0           # 3,3 kΩ -> bezpieczny prąd zwarcia < 1 mA
R_CAL_DOMYSLNE = 140.0   # domyślny opór kabli i multiplekserów
TOLERANCJA = 0.10        # ±10%

PROG_ZWARCIA_OHM = 15.0
PROG_OTWARTY_MV = 3050.0
PROG_ZWORY_KAL_MV = 400.0

ZIELONY = (16, 185, 129)
CZERWONY = (244, 63, 94)
POMARANCZOWY = (245, 158, 11)
ZOLTY = (234, 179, 8)

BG_APP = "#0A0E14"
BG_BAR = "#0F141D"
BG_CARD = "#111620"
BG_ELEV = "#161D2B"
BORDER = "#1E293B"
CYAN_DARK = "#0C2A42"
TEXT_MAIN = "#F1F5F9"
TEXT_MUTED = "#64748B"
TEXT_SUB = "#94A3B8"


# ----------------------------------------------------------------------
# 2. LOGIKA POMIAROWA
# ----------------------------------------------------------------------
def napiecie_na_ohm(mv, r_cal=R_CAL_DOMYSLNE):
    if mv is None or mv >= PROG_OTWARTY_MV:
        return None
    razem = R_REF * mv / (VCC_MV - mv)
    return max(razem - r_cal, 0.0)


def formatuj_ohm(r):
    if r is None:
        return "przerwa (∞)"
    if r >= 1000:
        return f"{r / 1000:.2f} kΩ"
    return f"{r:.0f} Ω"


def jest_dioda(mv_a, mv_b):
    return (mv_a < PROG_OTWARTY_MV <= mv_b) or (mv_b < PROG_OTWARTY_MV <= mv_a)


def opis_kierunku_mv(mv):
    return "otwarty" if mv >= PROG_OTWARTY_MV else f"{mv / 1000:.2f} V"


def porownaj(wzorzec, pomiar, elementy, r_cal=R_CAL_DOMYSLNE):
    wyniki = []
    for el in elementy:
        a, b = el["piny"]
        typ = el.get("typ", "linia" if el["nazwa"].upper().startswith("VCC") else "element")
        w_ab, w_ba = wzorzec.get(f"{a}-{b}"), wzorzec.get(f"{b}-{a}")
        m_ab, m_ba = pomiar.get(f"{a}-{b}"), pomiar.get(f"{b}-{a}")
        x, y = el.get("x", 50), el.get("y", 50)

        if (w_ab is None and w_ba is None) or (m_ab is None and m_ba is None):
            wyniki.append({"nazwa": el["nazwa"], "typ": typ, "piny": f"{a}↔{b}", "wzor": "-",
                           "pomiar": "-", "delta": "—", "delta_num": None,
                           "status": "BRAK DANYCH", "kolor": ZOLTY, "x": x, "y": y})
            continue

        oba_kierunki = (w_ab is not None and w_ba is not None and
                        m_ab is not None and m_ba is not None)

        if oba_kierunki and jest_dioda(w_ab, w_ba):
            w_przewodzilo_ab = w_ab < PROG_OTWARTY_MV
            m_przewodzi_ab = m_ab < PROG_OTWARTY_MV
            m_przewodzi_ba = m_ba < PROG_OTWARTY_MV

            w_txt = f"{opis_kierunku_mv(w_ab)} / {opis_kierunku_mv(w_ba)}"
            m_txt = f"{opis_kierunku_mv(m_ab)} / {opis_kierunku_mv(m_ba)}"
            odwrocona = ((w_przewodzilo_ab and not m_przewodzi_ab and m_przewodzi_ba) or
                         (not w_przewodzilo_ab and m_przewodzi_ab and not m_przewodzi_ba))

            if odwrocona:
                status, kolor = "ODWRÓCONA", CZERWONY
            elif (not m_przewodzi_ab) and (not m_przewodzi_ba):
                status, kolor = "PRZERWA", POMARANCZOWY
            elif m_przewodzi_ab and m_przewodzi_ba:
                status, kolor = "ZWARCIE", CZERWONY
            else:
                status, kolor = "OK", ZIELONY

            wyniki.append({"nazwa": el["nazwa"], "typ": typ, "piny": f"{a}↔{b}", "wzor": w_txt,
                           "pomiar": m_txt, "delta": "polaryz.", "delta_num": None,
                           "status": status, "kolor": kolor, "x": x, "y": y})
            continue

        w_pom = w_ab if w_ab is not None else w_ba
        m_pom = m_ab if m_ab is not None else m_ba

        rw = napiecie_na_ohm(w_pom, r_cal)
        rm = napiecie_na_ohm(m_pom, r_cal)
        w_txt, m_txt = formatuj_ohm(rw), formatuj_ohm(rm)

        if rw is not None and rm is not None and rw > 0:
            delta_num = (rm - rw) / rw * 100.0
            delta_txt = f"{delta_num:+.1f}%"
        elif not oba_kierunki:
            delta_num = None
            delta_txt = "1-kier."
        else:
            delta_num = None
            delta_txt = "—"

        if rw is None and rm is None:
            status, kolor = "OK", ZIELONY
        elif rw is None and rm is not None:
            status, kolor = "ZWARCIE" if rm < PROG_ZWARCIA_OHM else "PRZEBICIE", CZERWONY
        elif rm is None:
            status, kolor = "PRZERWA", POMARANCZOWY
        elif rw > PROG_ZWARCIA_OHM and rm < max(PROG_ZWARCIA_OHM, rw * 0.1):
            status, kolor = "ZWARCIE", CZERWONY
        elif rw <= PROG_ZWARCIA_OHM:
            status, kolor = ("OK", ZIELONY) if rm <= PROG_ZWARCIA_OHM * 2 else ("ZŁA WARTOŚĆ", CZERWONY)
        else:
            roznica = abs(rm - rw) / rw
            if roznica > TOLERANCJA:
                status, kolor = "ZŁA WARTOŚĆ", CZERWONY
            elif roznica > TOLERANCJA / 2:
                status, kolor = "BLISKO GRANICY", ZOLTY
            else:
                status, kolor = "OK", ZIELONY

        wyniki.append({"nazwa": el["nazwa"], "typ": typ, "piny": f"{a}↔{b}", "wzor": w_txt,
                       "pomiar": m_txt, "delta": delta_txt, "delta_num": delta_num,
                       "status": status, "kolor": kolor, "x": x, "y": y})
    return wyniki


# ----------------------------------------------------------------------
# 3. NAKŁADKA NA ZDJĘCIE PCB
# ----------------------------------------------------------------------
def narysuj(wyniki, baza_rgba, orig_size):
    w2, h2 = baza_rgba.size
    skala = w2 / float(orig_size[0])
    nakladka = Image.new("RGBA", (w2, h2), (0, 0, 0, 0))
    rysuj = ImageDraw.Draw(nakladka)
    font = czcionka(max(16, int(11.5 * skala)))
    zajete_etykiety = []

    for w in wyniki:
        cx, cy = int(w["x"] * skala), int(w["y"] * skala)
        status, kolor = w["status"], w["kolor"]

        if status == "OK":
            r = int(13 * skala)
            rysuj.ellipse([cx - r, cy - r, cx + r, cy + r],
                          outline=kolor + (170,), width=3)
        else:
            r = int(22 * skala)
            rysuj.ellipse([cx - r, cy - r, cx + r, cy + r],
                          fill=kolor + (55,), outline=kolor + (245,), width=5)
            b = r + int(5 * skala)
            k = int(6 * skala)
            for sx, sy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
                px, py = cx + sx * b, cy + sy * b
                rysuj.line([(px, py), (px - sx * k, py)], fill=kolor + (240,), width=4)
                rysuj.line([(px, py), (px, py - sy * k)], fill=kolor + (240,), width=4)

            opis_statusu = "ZWARCIE LINII" if (status == "ZWARCIE" and w.get("typ") == "linia") else status
            tekst = f"{w['nazwa']} · {opis_statusu} ({w['pomiar']})"
            tw = rysuj.textlength(tekst, font=font) + 20
            th = 32
            tx = max(12, min(w2 - tw - 12, cx - tw / 2))
            ty = (cy - b - th - 10) if (cy + b + th + 48 > h2) else (cy + b + 10)

            def _koliduje(t_x, t_y, t_w, t_h):
                for (z_x, z_y, z_w, z_h) in zajete_etykiety:
                    if (t_x < z_x + z_w and t_x + t_w > z_x and
                            t_y < z_y + z_h and t_y + t_h > z_y):
                        return True
                return False

            przesuniec = 0
            while _koliduje(tx, ty, tw, th) and przesuniec < 6:
                ty += th + 6
                przesuniec += 1
            if ty + th > h2 - 4:
                ty = max(4, h2 - th - 4)
            zajete_etykiety.append((tx, ty, tw, th))
            try:
                rysuj.rounded_rectangle([tx, ty, tx + tw, ty + th], radius=8,
                                        fill=(11, 15, 22, 235), outline=kolor + (235,), width=3)
            except AttributeError:
                rysuj.rectangle([tx, ty, tx + tw, ty + th],
                                fill=(11, 15, 22, 235), outline=kolor + (235,), width=3)
            rysuj.text((tx + 10, ty + 4), tekst, fill=(241, 245, 249, 255), font=font)

    return Image.alpha_composite(baza_rgba, nakladka).convert("RGB")


# ----------------------------------------------------------------------
# 4. PLIKI, SYMULATOR DANYCH + RAPORT CSV
# ----------------------------------------------------------------------
def wczytaj_elementy():
    with open(PLIK_ELEMENTY, encoding="utf-8") as f:
        return json.load(f)["elementy"]


def zrob_pomiar_demo(elementy, psuj=None, r_cal=R_CAL_DOMYSLNE):
    t0 = time.perf_counter()
    dane = {}
    typowe = {"R1": 470, "R2": 1000, "R3": 2200, "R4": 330, "R5": 1000,
              "R6": 4700, "D1": None, "D2": None, "U1": 680, "VCC-GND": 10000}
    for el in elementy:
        a, b = el["piny"]
        opor = typowe.get(el["nazwa"], 1000)
        if opor is None:
            dane[f"{a}-{b}"] = 1900.0
            dane[f"{b}-{a}"] = VCC_MV
        else:
            razem = opor + r_cal
            mv = VCC_MV * razem / (R_REF + razem) + random.uniform(-3, 3)
            dane[f"{a}-{b}"] = mv
            dane[f"{b}-{a}"] = mv

    if psuj == "zwarcie":
        dane["0-15"] = VCC_MV * r_cal / (R_REF + r_cal) + 4
        dane["15-0"] = dane["0-15"]
    elif psuj == "zly_rezystor":
        razem = 1030 + r_cal
        dane["0-1"] = VCC_MV * razem / (R_REF + razem)
        dane["1-0"] = dane["0-1"]
    elif psuj == "odwrocona_dioda":
        dane["6-8"], dane["8-6"] = dane["8-6"], dane["6-8"]
    elif psuj == "przerwa":
        dane["2-3"] = VCC_MV
        dane["3-2"] = VCC_MV

    czas_ms = round(random.uniform(350, 420) + (time.perf_counter() - t0) * 1000, 1)
    return dane, czas_ms


def zapisz_wiersz_csv(wyniki, czas_ms, tryb):
    nowy = not PLIK_CSV.exists()
    bledy = [f"{w['nazwa']}:{w['status']}" for w in wyniki if w["status"] != "OK"]
    werdykt = "FAIL" if bledy else "PASS"
    with open(PLIK_CSV, "a", newline="", encoding="utf-8-sig") as f:
        pisarz = csv.writer(f, delimiter=";")
        if nowy:
            pisarz.writerow(["czas", "tryb", "czas_skanu_ms", "werdykt", "liczba_bledow", "bledy"])
        pisarz.writerow([
            datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            tryb, czas_ms, werdykt, len(bledy), ", ".join(bledy)
        ])


# ----------------------------------------------------------------------
# 5. OKNO KONFIGURACJI PINÓW I POZYCJI NA PŁYTCE
# ----------------------------------------------------------------------
class KonfiguratorPinow(ctk.CTkToplevel):
    def __init__(self, master, elementy, orig_img, on_save):
        super().__init__(master)
        self.title("Konfiguracja pinów i elementów (lista_elementow.json)")
        self.geometry("1060x690")
        self.minsize(920, 600)
        self.configure(fg_color=BG_APP)
        self.transient(master)
        self.grab_set()

        self.elementy = [dict(e, piny=list(e["piny"])) for e in elementy]
        self.orig_img = orig_img.convert("RGB")
        self.on_save = on_save
        self._tk_img = None
        self._skala = 1.0
        self._ox = 0
        self._oy = 0

        self._zbuduj_ui()
        self._odswiez_liste()
        self.after(80, self._rysuj_podglad)

    def _zbuduj_ui(self):
        lewy = ctk.CTkFrame(self, width=420, fg_color=BG_CARD, corner_radius=10,
                            border_width=1, border_color=BORDER)
        lewy.pack(side="left", fill="y", padx=14, pady=14)
        lewy.pack_propagate(False)

        ctk.CTkLabel(lewy, text="MAPA PINÓW I ELEMENTÓW", text_color=TEXT_MAIN,
                     font=ctk.CTkFont("Segoe UI", 14, "bold")).pack(anchor="w", padx=14, pady=(12, 2))
        ctk.CTkLabel(lewy, text="Kliknij na zdjęcie po prawej, aby pobrać współrzędne (X, Y)",
                     text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI", 11)).pack(anchor="w", padx=14, pady=(0, 8))

        self.lista_box = ctk.CTkScrollableFrame(lewy, fg_color="#0B0F17", corner_radius=8,
                                                border_width=1, border_color=BORDER)
        self.lista_box.pack(fill="both", expand=True, padx=12, pady=(0, 10))

        form = ctk.CTkFrame(lewy, fg_color=BG_ELEV, corner_radius=8, border_width=1, border_color=BORDER)
        form.pack(fill="x", padx=12, pady=(0, 10))

        r1 = ctk.CTkFrame(form, fg_color="transparent")
        r1.pack(fill="x", padx=10, pady=(10, 6))
        ctk.CTkLabel(r1, text="Nazwa:", width=54, anchor="w", text_color=TEXT_SUB,
                     font=ctk.CTkFont("Segoe UI", 11, "bold")).pack(side="left")
        self.ent_nazwa = ctk.CTkEntry(r1, width=130, placeholder_text="np. R1, D1")
        self.ent_nazwa.pack(side="left", padx=(0, 10))
        ctk.CTkLabel(r1, text="Typ:", text_color=TEXT_SUB,
                     font=ctk.CTkFont("Segoe UI", 11, "bold")).pack(side="left", padx=(0, 4))
        self.var_typ = ctk.StringVar(value="element")
        ctk.CTkOptionMenu(r1, variable=self.var_typ, width=110, values=["element", "linia"]).pack(side="left")

        r2 = ctk.CTkFrame(form, fg_color="transparent")
        r2.pack(fill="x", padx=10, pady=4)
        piny_str = [str(i) for i in range(16)]
        ctk.CTkLabel(r2, text="Pin A:", width=54, anchor="w", text_color=TEXT_SUB,
                     font=ctk.CTkFont("Segoe UI", 11, "bold")).pack(side="left")
        self.var_pin_a = ctk.StringVar(value="0")
        ctk.CTkOptionMenu(r2, variable=self.var_pin_a, width=70, values=piny_str).pack(side="left", padx=(0, 14))
        ctk.CTkLabel(r2, text="Pin B:", text_color=TEXT_SUB,
                     font=ctk.CTkFont("Segoe UI", 11, "bold")).pack(side="left", padx=(0, 6))
        self.var_pin_b = ctk.StringVar(value="1")
        ctk.CTkOptionMenu(r2, variable=self.var_pin_b, width=70, values=piny_str).pack(side="left")

        r3 = ctk.CTkFrame(form, fg_color="transparent")
        r3.pack(fill="x", padx=10, pady=(4, 10))
        ctk.CTkLabel(r3, text="X:", width=24, anchor="w", text_color=TEXT_SUB,
                     font=ctk.CTkFont("Segoe UI", 11, "bold")).pack(side="left")
        self.ent_x = ctk.CTkEntry(r3, width=64)
        self.ent_x.insert(0, "250")
        self.ent_x.pack(side="left", padx=(0, 10))
        ctk.CTkLabel(r3, text="Y:", width=24, anchor="w", text_color=TEXT_SUB,
                     font=ctk.CTkFont("Segoe UI", 11, "bold")).pack(side="left")
        self.ent_y = ctk.CTkEntry(r3, width=64)
        self.ent_y.insert(0, "250")
        self.ent_y.pack(side="left", padx=(0, 10))

        ctk.CTkButton(r3, text="+ Dodaj / Zmień", height=30, fg_color="#0284C7", hover_color="#0369A1",
                      font=ctk.CTkFont("Segoe UI", 11, "bold"),
                      command=self._dodaj_lub_zmien).pack(side="right")

        dol = ctk.CTkFrame(lewy, fg_color="transparent")
        dol.pack(fill="x", padx=12, pady=(0, 12))
        ctk.CTkButton(dol, text="Zapisz do pliku", height=36, fg_color="#10B981", hover_color="#059669",
                      text_color="#062016", font=ctk.CTkFont("Segoe UI", 12, "bold"),
                      command=self._zapisz_i_zamknij).pack(side="left", fill="x", expand=True, padx=(0, 6))
        ctk.CTkButton(dol, text="Anuluj", height=36, width=90, fg_color=BG_ELEV, hover_color="#243044",
                      command=self.destroy).pack(side="right")

        prawy = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=10,
                             border_width=1, border_color=BORDER)
        prawy.pack(side="right", fill="both", expand=True, padx=(0, 14), pady=14)
        ctk.CTkLabel(prawy, text="KLIKNIJ NA PŁYTCE, ABY USTAWIĆ POZYCJĘ ELEMENTU",
                     text_color="#38BDF8", font=ctk.CTkFont("Segoe UI", 11, "bold")).pack(anchor="w", padx=14, pady=(10, 4))

        self.canvas = tk.Canvas(prawy, bg="#0B0F17", highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill="both", expand=True, padx=10, pady=(2, 10))
        self.canvas.bind("<Configure>", lambda _e: self._rysuj_podglad())
        self.canvas.bind("<Button-1>", self._klik_na_pcb)

    def _odswiez_liste(self):
        for w in self.lista_box.winfo_children():
            w.destroy()
        for idx, el in enumerate(self.elementy):
            row = ctk.CTkFrame(self.lista_box, fg_color=BG_ELEV, corner_radius=6, height=32)
            row.pack(fill="x", pady=2, padx=2)
            row.pack_propagate(False)
            typ_txt = " [linia]" if el.get("typ") == "linia" else ""
            opis = f"{el['nazwa']}{typ_txt}  |  piny {el['piny'][0]}↔{el['piny'][1]}  |  ({el.get('x', 0)}, {el.get('y', 0)})"
            ctk.CTkLabel(row, text=opis, text_color=TEXT_MAIN, anchor="w",
                         font=ctk.CTkFont("Consolas", 11)).pack(side="left", padx=8, fill="x", expand=True)
            ctk.CTkButton(row, text="Edytuj", width=52, height=22, fg_color="#1E293B", hover_color="#334155",
                          font=ctk.CTkFont("Segoe UI", 10),
                          command=lambda i=idx: self._wczytaj_do_edycji(i)).pack(side="left", padx=2)
            ctk.CTkButton(row, text="✕", width=26, height=22, fg_color="#3D121E", hover_color="#5B1E2E",
                          text_color="#FDA4AF", font=ctk.CTkFont("Segoe UI", 10, "bold"),
                          command=lambda i=idx: self._usun(i)).pack(side="left", padx=(2, 6))

    def _wczytaj_do_edycji(self, idx):
        el = self.elementy[idx]
        self.ent_nazwa.delete(0, "end")
        self.ent_nazwa.insert(0, el["nazwa"])
        self.var_pin_a.set(str(el["piny"][0]))
        self.var_pin_b.set(str(el["piny"][1]))
        self.var_typ.set(el.get("typ", "linia" if el["nazwa"].upper().startswith("VCC") else "element"))
        self.ent_x.delete(0, "end")
        self.ent_x.insert(0, str(el.get("x", 0)))
        self.ent_y.delete(0, "end")
        self.ent_y.insert(0, str(el.get("y", 0)))
        self._rysuj_podglad()

    def _usun(self, idx):
        self.elementy.pop(idx)
        self._odswiez_liste()
        self._rysuj_podglad()

    def _dodaj_lub_zmien(self):
        nazwa = self.ent_nazwa.get().strip()
        if not nazwa:
            messagebox.showwarning("Brak nazwy", "Wpisz nazwę elementu (np. R1, D1, VCC-GND).", parent=self)
            return
        a, b = int(self.var_pin_a.get()), int(self.var_pin_b.get())
        if a == b:
            messagebox.showwarning("Błędne piny", "Pin A i Pin B muszą być różne.", parent=self)
            return
        try:
            x, y = int(float(self.ent_x.get())), int(float(self.ent_y.get()))
        except ValueError:
            messagebox.showwarning("Błędne X/Y", "Współrzędne X i Y muszą być liczbami.", parent=self)
            return

        nowy = {"nazwa": nazwa, "piny": [a, b], "x": x, "y": y, "typ": self.var_typ.get()}
        istniejacy = next((i for i, e in enumerate(self.elementy) if e["nazwa"] == nazwa), None)
        if istniejacy is not None:
            self.elementy[istniejacy] = nowy
        else:
            self.elementy.append(nowy)
        self._odswiez_liste()
        self._rysuj_podglad()

    def _klik_na_pcb(self, event):
        if self._skala <= 0:
            return
        ox = int(round((event.x - self._ox) / self._skala))
        oy = int(round((event.y - self._oy) / self._skala))
        ox = max(0, min(self.orig_img.width, ox))
        oy = max(0, min(self.orig_img.height, oy))
        self.ent_x.delete(0, "end")
        self.ent_x.insert(0, str(ox))
        self.ent_y.delete(0, "end")
        self.ent_y.insert(0, str(oy))
        self._rysuj_podglad()

    def _rysuj_podglad(self):
        wc = self.canvas.winfo_width()
        hc = self.canvas.winfo_height()
        if wc < 50 or hc < 50:
            return
        self._skala = min((wc - 20) / self.orig_img.width, (hc - 20) / self.orig_img.height)
        nw = max(1, int(self.orig_img.width * self._skala))
        nh = max(1, int(self.orig_img.height * self._skala))
        self._ox = (wc - nw) // 2
        self._oy = (hc - nh) // 2

        kopia = self.orig_img.copy()
        d = ImageDraw.Draw(kopia)
        sk = max(1.0, self.orig_img.width / 512.0)
        font = czcionka(int(12 * sk))
        rm = int(10 * sk)
        for el in self.elementy:
            ex, ey = el.get("x", 0), el.get("y", 0)
            d.ellipse([ex - rm, ey - rm, ex + rm, ey + rm], outline=(16, 185, 129), width=max(2, int(3 * sk)))
            d.text((ex + rm + 2, ey - int(8 * sk)), f"{el['nazwa']} ({el['piny'][0]}-{el['piny'][1]})",
                   fill=(241, 245, 249), font=font)

        try:
            cx, cy = int(float(self.ent_x.get())), int(float(self.ent_y.get()))
            cr = int(14 * sk)
            d.line([(cx - cr, cy), (cx + cr, cy)], fill=(56, 189, 248), width=max(2, int(3 * sk)))
            d.line([(cx, cy - cr), (cx, cy + cr)], fill=(56, 189, 248), width=max(2, int(3 * sk)))
        except ValueError:
            pass

        self._tk_img = ImageTk.PhotoImage(kopia.resize((nw, nh), RESAMPLE))
        self.canvas.delete("all")
        self.canvas.create_image(self._ox, self._oy, image=self._tk_img, anchor="nw")

    def _zapisz_i_zamknij(self):
        if not self.elementy:
            messagebox.showwarning("Pusta lista", "Dodaj przynajmniej jeden element.", parent=self)
            return
        with open(PLIK_ELEMENTY, "w", encoding="utf-8") as f:
            json.dump({"elementy": self.elementy}, f, indent=2, ensure_ascii=False)
        self.on_save(self.elementy)
        self.destroy()


# ----------------------------------------------------------------------
# 6. GŁÓWNE OKNO PROGRAMU
# ----------------------------------------------------------------------
ctk.set_appearance_mode("dark")


class Aplikacja(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("ICT-SCAN PRO  |  In-Circuit Golden Sample Inspector")
        self.geometry("1480x860")
        self.minsize(1280, 740)
        self.configure(fg_color=BG_APP)

        self.wzorzec = None
        self.r_cal = R_CAL_DOMYSLNE
        self.elementy = wczytaj_elementy()
        self.port_usb = None
        self._serial_bufor = ""
        self._serial_job = None
        self._oczekiwana_akcja = None
        self._timeout_job = None

        self.licznik_pass = 0
        self.licznik_fail = 0
        self.historia = []
        self.licznik_testow = 0
        self.aktywny_nr = None

        orig = Image.open(PLIK_ZDJECIE).convert("RGBA")
        self.orig_size = orig.size
        skala_rob = 2 if max(orig.size) <= 900 else 1
        self.baza_2x = orig.resize((orig.width * skala_rob, orig.height * skala_rob), RESAMPLE)
        self.bazowa_skala = min(1.0, 620.0 / max(orig.size))
        self.zoom = 1.0
        self.pan_x = 0
        self.pan_y = 0
        self._drag_start = None
        self._ostatni_obraz_pil = self.baza_2x.convert("RGB")
        self._tk_img = None
        self._canvas_img_id = None

        self.szerokosc_prawej = 660
        self.skala_tabeli = 1.0
        self.pelny_ekran_tabeli = False
        self._ostatnia_szer_prawa = 0
        self.ostatnie_wyniki = None
        self.wiersze_tabeli = []

        self._zbuduj_gorny_pasek()
        self._zbuduj_obszar_roboczy()

        self.after(120, self._odswiez_canvas)
        self._wczytaj_wzorzec_z_dysku()

    # ------------------------------------------------------------------
    def _wczytaj_wzorzec_z_dysku(self):
        if not PLIK_WZORZEC.exists():
            self.pisz(f"System gotowy (R_cal = {self.r_cal:.0f} Ω). Podłóż dobrą płytkę i zapisz wzorzec.")
            return
        try:
            with open(PLIK_WZORZEC, encoding="utf-8") as f:
                dane = json.load(f)
            pasuje = all(
                f"{el['piny'][0]}-{el['piny'][1]}" in dane or f"{el['piny'][1]}-{el['piny'][0]}" in dane
                for el in self.elementy
            )
            if not pasuje:
                self.pisz("Stary plik wzorzec.json nie pasuje do obecnej listy elementów — kliknij [★ Zapisz wzorzec].")
                return
            self.wzorzec = dane
            self.baner.configure(fg_color="#1D170C", border_color="#D97706")
            self.baner_tytul.configure(text="●  WZORZEC WCZYTANY Z PLIKU", text_color="#FBBF24")
            self.baner_opis.configure(text=f"Załadowano {PLIK_WZORZEC.name} • Kliknij [▶ Testuj płytkę] lub zapisz nowy")
            self.pisz(f"Wczytano wzorzec z {PLIK_WZORZEC.name} ({len(dane)} pomiarów, R_cal = {self.r_cal:.0f} Ω).")
        except Exception as e:
            self.pisz(f"Nie udało się wczytać {PLIK_WZORZEC.name}: {e}")

    # ------------------------------------------------------------------
    def _zbuduj_gorny_pasek(self):
        bar = ctk.CTkFrame(self, height=62, fg_color=BG_BAR, corner_radius=0,
                           border_width=1, border_color=BORDER)
        bar.pack(side="top", fill="x")
        bar.pack_propagate(False)

        lewa = ctk.CTkFrame(bar, fg_color="transparent")
        lewa.pack(side="left", padx=16)
        ctk.CTkLabel(lewa, text=" ICT ", fg_color=CYAN_DARK, text_color="#38BDF8",
                     corner_radius=6, font=ctk.CTkFont("Consolas", 13, "bold"),
                     height=28).pack(side="left", padx=(0, 10))
        tyt_box = ctk.CTkFrame(lewa, fg_color="transparent")
        tyt_box.pack(side="left")
        ctk.CTkLabel(tyt_box, text="ICT-SCAN PRO", text_color=TEXT_MAIN,
                     font=ctk.CTkFont("Segoe UI", 15, "bold")).pack(anchor="w")
        ctk.CTkLabel(tyt_box, text="GOLDEN SAMPLE DIAGNOSTICS  •  E(X)PLORY",
                     text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI", 9, "bold")).pack(anchor="w")

        prawa = ctk.CTkFrame(bar, fg_color="transparent")
        prawa.pack(side="right", padx=16)

        ctk.CTkButton(prawa, text="▶  Testuj płytkę", height=36, width=148,
                      fg_color="#0284C7", hover_color="#0369A1", text_color="white",
                      border_width=1, border_color="#38BDF8", corner_radius=8,
                      font=ctk.CTkFont("Segoe UI", 13, "bold"),
                      command=self.testuj).pack(side="right", padx=(6, 0))

        ctk.CTkButton(prawa, text="★  Zapisz wzorzec", height=36, width=148,
                      fg_color="#1F190D", hover_color="#2E2412", text_color="#FBBF24",
                      border_width=1, border_color="#D97706", corner_radius=8,
                      font=ctk.CTkFont("Segoe UI", 13, "bold"),
                      command=self.zapisz_wzorzec).pack(side="right", padx=(6, 0))

        ctk.CTkButton(prawa, text="⚙  Kalibruj", height=36, width=98,
                      fg_color=BG_ELEV, hover_color="#243044", text_color=TEXT_SUB,
                      border_width=1, border_color="#334155", corner_radius=8,
                      font=ctk.CTkFont("Segoe UI", 12, "bold"),
                      command=self.kalibruj).pack(side="right", padx=(6, 0))

        ctk.CTkButton(prawa, text="⚙  Piny", height=36, width=86,
                      fg_color=BG_ELEV, hover_color="#243044", text_color="#38BDF8",
                      border_width=1, border_color="#1E3A5F", corner_radius=8,
                      font=ctk.CTkFont("Segoe UI", 12, "bold"),
                      command=self.otworz_konfigurator_pinow).pack(side="right", padx=(6, 0))

        srodek = ctk.CTkFrame(bar, fg_color="transparent")
        srodek.pack(side="right", padx=8)

        ctk.CTkLabel(srodek, text="SYMULACJA:", text_color=TEXT_MUTED,
                     font=ctk.CTkFont("Segoe UI", 10, "bold")).pack(side="left", padx=(0, 5))
        self.scenariusz = ctk.StringVar(value="dobra płytka")
        ctk.CTkOptionMenu(srodek, variable=self.scenariusz, width=136, height=32,
                          fg_color=BG_ELEV, button_color="#243044", button_hover_color="#334155",
                          dropdown_fg_color=BG_CARD, text_color=TEXT_MAIN,
                          font=ctk.CTkFont("Segoe UI", 11),
                          values=["dobra płytka", "zwarcie", "zly_rezystor",
                                  "odwrocona_dioda", "przerwa"]).pack(side="left", padx=(0, 10))

        ctk.CTkLabel(srodek, text="ŹRÓDŁO:", text_color=TEXT_MUTED,
                     font=ctk.CTkFont("Segoe UI", 10, "bold")).pack(side="left", padx=(0, 5))
        porty = self._lista_portow()
        self.wybor_portu = ctk.StringVar(value=porty[0])
        self.menu_porty = ctk.CTkOptionMenu(
            srodek, variable=self.wybor_portu, values=porty, width=142, height=32,
            fg_color=BG_ELEV, button_color="#243044", button_hover_color="#334155",
            dropdown_fg_color=BG_CARD, text_color=TEXT_MAIN,
            font=ctk.CTkFont("Segoe UI", 11), command=self.zmien_port
        )
        self.menu_porty.pack(side="left")
        ctk.CTkButton(srodek, text="↻", width=30, height=32, fg_color=BG_ELEV, hover_color="#243044",
                      border_width=1, border_color="#334155", text_color=TEXT_SUB,
                      font=ctk.CTkFont("Segoe UI", 13, "bold"),
                      command=self._odswiez_porty).pack(side="left", padx=(4, 0))

    # ------------------------------------------------------------------
    def _zbuduj_obszar_roboczy(self):
        self.kontener = ctk.CTkFrame(self, fg_color="transparent")
        self.kontener.pack(fill="both", expand=True, padx=14, pady=14)

        self.lewa = ctk.CTkFrame(self.kontener, fg_color="transparent")
        self.lewa.pack(side="left", fill="both", expand=True)

        kpi_row = ctk.CTkFrame(self.lewa, fg_color="transparent", height=64)
        kpi_row.pack(fill="x", pady=(0, 12))
        kpi_row.pack_propagate(False)

        self.kpi_czas = self._dodaj_kpi(kpi_row, "CZAS SKANU", "— ms", "#38BDF8")
        self.kpi_elementy = self._dodaj_kpi(kpi_row, "ZAKRES TESTU",
                                            f"{len(self.elementy)} elem. / 16 pinów", TEXT_MAIN)
        self.kpi_seria = self._dodaj_kpi(kpi_row, "STATYSTYKA SERII", "0 PASS · 0 FAIL", TEXT_SUB, ostatni=True)

        self.karta_pcb = ctk.CTkFrame(self.lewa, fg_color=BG_CARD, corner_radius=10,
                                      border_width=1, border_color=BORDER)
        self.karta_pcb.pack(fill="both", expand=True)

        pcb_top = ctk.CTkFrame(self.karta_pcb, fg_color="transparent", height=36)
        pcb_top.pack(fill="x", padx=14, pady=(10, 4))
        ctk.CTkLabel(pcb_top, text="INSPEKCJA PCB",
                     text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI", 11, "bold")).pack(side="left")

        legenda = ctk.CTkFrame(pcb_top, fg_color="transparent")
        legenda.pack(side="right")
        for kolor_kropki, nazwa_leg in (("#10B981", "OK"), ("#F43F5E", "BŁĄD"), ("#F59E0B", "PRZERWA")):
            ctk.CTkLabel(legenda, text="●", text_color=kolor_kropki,
                         font=ctk.CTkFont("Segoe UI", 12)).pack(side="left", padx=(6, 2))
            ctk.CTkLabel(legenda, text=nazwa_leg, text_color=TEXT_SUB,
                         font=ctk.CTkFont("Segoe UI", 10, "bold")).pack(side="left")

        zoom_box = ctk.CTkFrame(pcb_top, fg_color=BG_ELEV, corner_radius=6, border_width=1, border_color=BORDER)
        zoom_box.pack(side="right", padx=(8, 10))
        btn_kw = dict(width=26, height=22, fg_color="transparent", hover_color="#243044",
                      text_color=TEXT_MAIN, corner_radius=4, font=ctk.CTkFont("Consolas", 12, "bold"))
        ctk.CTkButton(zoom_box, text="−", command=lambda: self._zmien_zoom(-0.15), **btn_kw).pack(side="left", padx=2, pady=2)
        self.lbl_zoom = ctk.CTkLabel(zoom_box, text="100%", width=42, text_color="#38BDF8",
                                     font=ctk.CTkFont("Consolas", 11, "bold"))
        self.lbl_zoom.pack(side="left", padx=2)
        ctk.CTkButton(zoom_box, text="+", command=lambda: self._zmien_zoom(+0.15), **btn_kw).pack(side="left", padx=2, pady=2)
        ctk.CTkButton(zoom_box, text="1:1", width=32, height=22, fg_color="#1E293B", hover_color="#334155",
                      text_color=TEXT_SUB, corner_radius=4, font=ctk.CTkFont("Consolas", 10, "bold"),
                      command=self._resetuj_widok_pcb).pack(side="left", padx=(2, 3), pady=2)

        self.canvas = tk.Canvas(self.karta_pcb, bg="#0B0F17", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=10, pady=(2, 10))
        self.canvas.bind("<Configure>", lambda _e: self._odswiez_canvas())
        self.canvas.bind("<MouseWheel>", self._na_scroll_myszy)
        self.canvas.bind("<Button-4>", lambda _e: self._zmien_zoom(+0.10))
        self.canvas.bind("<Button-5>", lambda _e: self._zmien_zoom(-0.10))
        self.canvas.bind("<ButtonPress-1>", self._start_przesuwania)
        self.canvas.bind("<B1-Motion>", self._przesuwaj_pcb)
        self.canvas.bind("<ButtonRelease-1>", lambda _e: self.canvas.configure(cursor=""))

        self.splitter = ctk.CTkFrame(self.kontener, width=6, fg_color="transparent", cursor="sb_h_double_arrow")
        self.splitter.pack(side="left", fill="y", padx=1)
        self.splitter_grip = ctk.CTkFrame(self.splitter, width=2, height=64, fg_color="#334155", corner_radius=1)
        self.splitter_grip.place(relx=0.5, rely=0.5, anchor="center")

        for w in (self.splitter, self.splitter_grip):
            w.bind("<Enter>", lambda _e: self.splitter_grip.configure(fg_color="#38BDF8"))
            w.bind("<Leave>", lambda _e: self.splitter_grip.configure(fg_color="#334155"))
            w.bind("<B1-Motion>", self._przesun_podzial)

        # --- PRAWA KOLUMNA ---
        self.prawa = ctk.CTkFrame(self.kontener, width=self.szerokosc_prawej, fg_color="transparent")
        self.prawa.pack(side="right", fill="y")
        self.prawa.pack_propagate(False)
        self.prawa.bind("<Configure>", self._na_zmiane_szerokosci_prawej)

        self.baner = ctk.CTkFrame(self.prawa, height=82, fg_color=BG_CARD, corner_radius=10,
                                  border_width=1, border_color=BORDER)
        self.baner.pack(fill="x", pady=(0, 10))
        self.baner.pack_propagate(False)

        self.baner_tytul = ctk.CTkLabel(self.baner, text="●  OCZEKIWANIE NA WZORZEC",
                                        text_color=TEXT_MAIN,
                                        font=ctk.CTkFont("Segoe UI", 19, "bold"))
        self.baner_tytul.pack(anchor="w", padx=18, pady=(15, 2))
        self.baner_opis = ctk.CTkLabel(self.baner,
                                       text="Wybierz sprawną płytkę i kliknij [★ Zapisz wzorzec] na górnym pasku",
                                       text_color=TEXT_SUB, font=ctk.CTkFont("Segoe UI", 12))
        self.baner_opis.pack(anchor="w", padx=18)

        karta_hist = ctk.CTkFrame(self.prawa, height=44, fg_color=BG_CARD, corner_radius=8,
                                  border_width=1, border_color=BORDER)
        karta_hist.pack(fill="x", pady=(0, 10))
        karta_hist.pack_propagate(False)
        ctk.CTkLabel(karta_hist, text="HISTORIA:", text_color=TEXT_MUTED,
                     font=ctk.CTkFont("Segoe UI", 9, "bold")).pack(side="left", padx=(12, 8))
        self.pasek_historii = ctk.CTkFrame(karta_hist, fg_color="transparent")
        self.pasek_historii.pack(side="left", fill="both", expand=True, padx=(0, 8))
        ctk.CTkLabel(self.pasek_historii, text="brak wykonanych testów w tej sesji",
                     text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI", 11)).pack(side="left")

        karta_tab = ctk.CTkFrame(self.prawa, fg_color=BG_CARD, corner_radius=10,
                                 border_width=1, border_color=BORDER)
        karta_tab.pack(fill="both", expand=True, pady=(0, 10))

        tab_top = ctk.CTkFrame(karta_tab, fg_color="transparent")
        tab_top.pack(fill="x", padx=14, pady=(10, 6))
        ctk.CTkLabel(tab_top, text="ANALIZA WĘZŁÓW",
                     text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI", 11, "bold")).pack(side="left")

        self.btn_fullscreen = ctk.CTkButton(
            tab_top, text="⛶ Pełny", width=74, height=26, corner_radius=6,
            fg_color=BG_ELEV, hover_color="#243044", border_width=1, border_color="#334155",
            text_color="#38BDF8", font=ctk.CTkFont("Segoe UI", 11, "bold"),
            command=self._przelacz_pelny_ekran_tabeli
        )
        self.btn_fullscreen.pack(side="right", padx=(8, 0))

        skala_box = ctk.CTkFrame(tab_top, fg_color=BG_ELEV, corner_radius=6, border_width=1, border_color=BORDER)
        skala_box.pack(side="right", padx=(10, 0))
        ctk.CTkButton(skala_box, text="A−", width=28, height=22, fg_color="transparent", hover_color="#243044",
                      text_color=TEXT_MAIN, font=ctk.CTkFont("Segoe UI", 11, "bold"),
                      command=lambda: self._zmien_skale_tabeli(-0.15)).pack(side="left", padx=2, pady=2)
        self.lbl_skala_tab = ctk.CTkLabel(skala_box, text="100%", width=40, text_color="#38BDF8",
                                          font=ctk.CTkFont("Consolas", 10, "bold"))
        self.lbl_skala_tab.pack(side="left", padx=2)
        ctk.CTkButton(skala_box, text="A+", width=28, height=22, fg_color="transparent", hover_color="#243044",
                      text_color=TEXT_MAIN, font=ctk.CTkFont("Segoe UI", 11, "bold"),
                      command=lambda: self._zmien_skale_tabeli(+0.15)).pack(side="left", padx=2, pady=2)

        self.lbl_tab_info = ctk.CTkLabel(tab_top,
                                         text=f"TOL. ±{int(TOLERANCJA * 100)}% · R_CAL {self.r_cal:.0f} Ω",
                                         text_color=TEXT_SUB, font=ctk.CTkFont("Consolas", 10, "bold"))
        self.lbl_tab_info.pack(side="right")

        self.nag = ctk.CTkFrame(karta_tab, fg_color=BG_ELEV, height=32, corner_radius=6)
        self.nag.pack(fill="x", padx=10, pady=(0, 4))
        self.nag.pack_propagate(False)
        self._rysuj_naglowek_tabeli()

        self.tabela = ctk.CTkScrollableFrame(karta_tab, fg_color="transparent")
        self.tabela.pack(fill="both", expand=True, padx=6, pady=(0, 8))

        karta_log = ctk.CTkFrame(self.prawa, height=168, fg_color="#090C11", corner_radius=10,
                                 border_width=1, border_color=BORDER)
        karta_log.pack(fill="x")
        karta_log.pack_propagate(False)

        log_top = ctk.CTkFrame(karta_log, fg_color="transparent")
        log_top.pack(fill="x", padx=12, pady=(6, 2))
        ctk.CTkLabel(log_top, text="SERIAL MONITOR (USB JSON) & DZIENNIK", text_color=TEXT_MUTED,
                     font=ctk.CTkFont("Segoe UI", 9, "bold")).pack(side="left")

        ctk.CTkButton(log_top, text="Wyczyść", width=62, height=20, fg_color=BG_ELEV, hover_color="#243044",
                      text_color=TEXT_SUB, font=ctk.CTkFont("Segoe UI", 10),
                      command=self._wyczysc_log).pack(side="right", padx=(6, 0))
        self.pokaz_pelny_json = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(log_top, text="Pełny JSON", variable=self.pokaz_pelny_json,
                        checkbox_width=14, checkbox_height=14, border_width=1,
                        text_color=TEXT_SUB, font=ctk.CTkFont("Segoe UI", 10)).pack(side="right")

        self.log = ctk.CTkTextbox(karta_log, fg_color="transparent", text_color=TEXT_SUB,
                                  wrap="word", font=ctk.CTkFont("Consolas", 11))
        self.log.pack(fill="both", expand=True, padx=8, pady=(0, 4))

        cmd_bar = ctk.CTkFrame(karta_log, fg_color="transparent", height=28)
        cmd_bar.pack(fill="x", padx=10, pady=(0, 8))
        self.ent_cmd = ctk.CTkEntry(cmd_bar, height=26, fg_color=BG_CARD, border_color=BORDER,
                                    font=ctk.CTkFont("Consolas", 11),
                                    placeholder_text="Wyślij komendę przez Serial Monitor (np. SCAN, PING)...")
        self.ent_cmd.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.ent_cmd.bind("<Return>", lambda _e: self._wyslij_komende_serial())
        ctk.CTkButton(cmd_bar, text="Wyślij", width=68, height=26, fg_color="#1E293B", hover_color="#334155",
                      font=ctk.CTkFont("Segoe UI", 11, "bold"),
                      command=self._wyslij_komende_serial).pack(side="right")

    def _dodaj_kpi(self, parent, tytul, wartosc, kolor, ostatni=False):
        karta = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=10,
                             border_width=1, border_color=BORDER)
        karta.pack(side="left", fill="both", expand=True, padx=(0, 0 if ostatni else 10))
        ctk.CTkLabel(karta, text=tytul, text_color=TEXT_MUTED,
                     font=ctk.CTkFont("Segoe UI", 9, "bold")).pack(anchor="w", padx=14, pady=(10, 0))
        lbl = ctk.CTkLabel(karta, text=wartosc, text_color=kolor,
                           font=ctk.CTkFont("Consolas", 15, "bold"))
        lbl.pack(anchor="w", padx=14, pady=(0, 8))
        return lbl

    # ------------------------------------------------------------------
    # KONFIGURATOR PINÓW (w natywnej skali zdjęcia 1:1)
    # ------------------------------------------------------------------
    def otworz_konfigurator_pinow(self):
        orig_img = self.baza_2x.resize(self.orig_size, RESAMPLE)
        KonfiguratorPinow(self, self.elementy, orig_img, self._po_zapisie_pinow)

    def _po_zapisie_pinow(self, nowe_elementy):
        self.elementy = nowe_elementy
        self.kpi_elementy.configure(text=f"{len(self.elementy)} elem. / 16 pinów")
        self.pisz(f"Zapisano nową mapę pinów: {len(self.elementy)} elementów w {PLIK_ELEMENTY.name}.")
        if self.wzorzec is not None:
            pasuje = all(
                f"{el['piny'][0]}-{el['piny'][1]}" in self.wzorzec or f"{el['piny'][1]}-{el['piny'][0]}" in self.wzorzec
                for el in self.elementy
            )
            if not pasuje:
                self.wzorzec = None
                self.baner.configure(fg_color=BG_CARD, border_color=BORDER)
                self.baner_tytul.configure(text="●  OCZEKIWANIE NA NOWY WZORZEC", text_color=TEXT_MAIN)
                self.baner_opis.configure(text="Zmieniono piny — kliknij [★ Zapisz wzorzec] dla nowej konfiguracji")
                self.pisz("Nowe piny nie były we wzorcu — zapisz wzorzec ponownie.")

    # ------------------------------------------------------------------
    # ZOOM, PRZESUWANIE PCB, PRZECIĄGANIE I PEŁNY EKRAN TABELI
    # ------------------------------------------------------------------
    def _zmien_zoom(self, delta):
        nowy = round(max(0.55, min(2.0, self.zoom + delta)), 2)
        if nowy == self.zoom:
            return
        self.zoom = nowy
        self.lbl_zoom.configure(text=f"{int(round(self.zoom * 100))}%")
        self._odswiez_canvas()

    def _resetuj_widok_pcb(self):
        if self.zoom == 1.0 and self.pan_x == 0 and self.pan_y == 0:
            return
        self.zoom = 1.0
        self.pan_x = 0
        self.pan_y = 0
        self.lbl_zoom.configure(text="100%")
        self._odswiez_canvas()

    def _na_scroll_myszy(self, event):
        self._zmien_zoom(0.10 if event.delta > 0 else -0.10)

    def _start_przesuwania(self, event):
        self._drag_start = (event.x, event.y)
        self.canvas.configure(cursor="fleur")

    def _przesuwaj_pcb(self, event):
        if self._drag_start is None:
            return
        dx = event.x - self._drag_start[0]
        dy = event.y - self._drag_start[1]
        self._drag_start = (event.x, event.y)
        limit = int(320 * self.zoom)
        self.pan_x = max(-limit, min(limit, self.pan_x + dx))
        self.pan_y = max(-limit, min(limit, self.pan_y + dy))
        self._odswiez_canvas()

    def _odswiez_canvas(self):
        if self._ostatni_obraz_pil is None or self.pelny_ekran_tabeli:
            return
        wc = self.canvas.winfo_width()
        hc = self.canvas.winfo_height()
        if wc < 10 or hc < 10:
            wc, hc = 600, 560

        docel_w = max(80, int(self.orig_size[0] * self.bazowa_skala * self.zoom))
        docel_h = max(80, int(self.orig_size[1] * self.bazowa_skala * self.zoom))
        nowy = self._ostatni_obraz_pil.resize((docel_w, docel_h), RESAMPLE)
        self._tk_img = ImageTk.PhotoImage(nowy)

        cx = wc // 2 + self.pan_x
        cy = hc // 2 + self.pan_y
        if self._canvas_img_id is None:
            self._canvas_img_id = self.canvas.create_image(cx, cy, image=self._tk_img, anchor="center")
        else:
            self.canvas.itemconfig(self._canvas_img_id, image=self._tk_img)
            self.canvas.coords(self._canvas_img_id, cx, cy)

    def pokaz_zdjecie(self, obraz):
        self._ostatni_obraz_pil = obraz
        self._odswiez_canvas()

    def _przesun_podzial(self, event):
        if self.pelny_ekran_tabeli:
            return
        prawy_brzeg = self.winfo_rootx() + self.winfo_width() - 14
        nowa = prawy_brzeg - event.x_root - 6
        max_szer = min(780, max(660, self.winfo_width() - 620))
        nowa = max(550, min(max_szer, int(nowa)))
        if abs(nowa - self.szerokosc_prawej) >= 3:
            self.szerokosc_prawej = nowa
            self.prawa.configure(width=nowa)
            self._odswiez_kolumny_tabeli()

    def _przelacz_pelny_ekran_tabeli(self):
        if not self.pelny_ekran_tabeli:
            self.pelny_ekran_tabeli = True
            self.lewa.pack_forget()
            self.splitter.pack_forget()
            self.prawa.pack_forget()
            self.prawa.pack(side="left", fill="both", expand=True)
            self.btn_fullscreen.configure(text="◫ Podziel")
        else:
            self.pelny_ekran_tabeli = False
            self.prawa.pack_forget()
            self.lewa.pack(side="left", fill="both", expand=True)
            self.splitter.pack(side="left", fill="y", padx=1)
            self.prawa.configure(width=self.szerokosc_prawej)
            self.prawa.pack(side="right", fill="y")
            self.prawa.pack_propagate(False)
            self.btn_fullscreen.configure(text="⛶ Pełny")
            self.after(40, self._odswiez_canvas)
        self.after(30, self._odswiez_kolumny_tabeli)

    def _na_zmiane_szerokosci_prawej(self, event):
        if abs(event.width - self._ostatnia_szer_prawa) > 6:
            self._ostatnia_szer_prawa = event.width
            self._odswiez_kolumny_tabeli()

    def _odswiez_kolumny_tabeli(self):
        self._konfiguruj_kolumny_wiersza(self.nag)
        for w in self.wiersze_tabeli:
            self._konfiguruj_kolumny_wiersza(w)

    def _zmien_skale_tabeli(self, delta):
        nowa = round(max(0.85, min(1.30, self.skala_tabeli + delta)), 2)
        if nowa == self.skala_tabeli:
            return
        self.skala_tabeli = nowa
        self.lbl_skala_tab.configure(text=f"{int(round(self.skala_tabeli * 100))}%")
        self._rysuj_naglowek_tabeli()
        if self.ostatnie_wyniki is not None:
            self.odswiez_tabele(self.ostatnie_wyniki)

    def _konfiguruj_kolumny_wiersza(self, frame):
        szer_p = self.prawa.winfo_width()
        if szer_p < 200:
            szer_p = self.szerokosc_prawej
        avail = max(430, szer_p - 86)
        frame.grid_columnconfigure(0, minsize=int(avail * 0.16))
        frame.grid_columnconfigure(1, minsize=int(avail * 0.25))
        frame.grid_columnconfigure(2, minsize=int(avail * 0.25))
        frame.grid_columnconfigure(3, minsize=int(avail * 0.12))
        frame.grid_columnconfigure(4, weight=1, minsize=int(120 * self.skala_tabeli))

    def _rysuj_naglowek_tabeli(self):
        for widget in self.nag.winfo_children():
            widget.destroy()
        s = self.skala_tabeli
        self.nag.configure(height=int(32 * s))
        self._konfiguruj_kolumny_wiersza(self.nag)
        f_nag = ctk.CTkFont("Segoe UI", max(9, int(11 * s)), "bold")
        for col, tyt in enumerate(("ELEMENT", "WZORZEC", "POMIAR", "Δ ODCHYL.", "STATUS")):
            stick = "e" if col == 4 else "w"
            pad = (0, 14) if col == 4 else ((14, 4) if col == 0 else (4, 4))
            ctk.CTkLabel(self.nag, text=tyt, text_color=TEXT_MUTED, font=f_nag).grid(
                row=0, column=col, sticky=stick, padx=pad, pady=4)

    # ------------------------------------------------------------------
    # SERIAL MONITOR + POŁĄCZENIE USB (nieblokujące)
    # ------------------------------------------------------------------
    def _lista_portow(self):
        return ["DEMO (Symulator)"] + (
            [p.device for p in list_ports.comports()] if MA_SERIAL else []
        )

    def _odswiez_porty(self):
        porty = self._lista_portow()
        self.menu_porty.configure(values=porty)
        if self.wybor_portu.get() not in porty:
            self.wybor_portu.set(porty[0])
            self.zmien_port(porty[0])
        self.pisz(f"Odświeżono porty USB: {', '.join(porty)}")

    def pisz(self, tekst):
        czas = datetime.datetime.now().strftime("%H:%M:%S")
        self.log.insert("end", f"[{czas}] {tekst}\n")
        self.log.see("end")

    def _wyczysc_log(self):
        self.log.delete("1.0", "end")

    def _wyslij_komende_serial(self):
        komenda = self.ent_cmd.get().strip()
        if not komenda:
            return
        if self.port_usb is None or not self.port_usb.is_open:
            self.pisz("Tryb DEMO — wybierz port COM u góry, aby wysłać komendę do mikrokontrolera.")
            return
        try:
            self.port_usb.write((komenda + "\n").encode("utf-8"))
            self.pisz(f"[TX] {komenda}")
            self.ent_cmd.delete(0, "end")
        except Exception as e:
            self.pisz(f"[TX Błąd] {e}")

    def zmien_port(self, wybor):
        self._zatrzymaj_nasluch_serial()
        if self.port_usb is not None:
            try:
                self.port_usb.close()
            except Exception:
                pass
            self.port_usb = None

        if wybor == "DEMO (Symulator)" or not MA_SERIAL:
            self.pisz("Tryb pracy: DEMO (symulator).")
            return

        try:
            self.port_usb = serial.Serial(wybor, 115200, timeout=0.05, write_timeout=1.0)
            self._serial_bufor = ""
            time.sleep(0.3)
            self.pisz(f"Połączono z Serial Monitor USB: {wybor} @ 115200")
            self._czytaj_serial_cyklicznie()
        except Exception as e:
            self.pisz(f"Błąd portu {wybor}: {e}")
            self.wybor_portu.set("DEMO (Symulator)")

    def _zatrzymaj_nasluch_serial(self):
        self._anuluj_timeout_usb()
        self._oczekiwana_akcja = None
        if self._serial_job is not None:
            try:
                self.after_cancel(self._serial_job)
            except Exception:
                pass
            self._serial_job = None

    def _czytaj_serial_cyklicznie(self):
        if self.port_usb is None or not self.port_usb.is_open:
            return
        try:
            if self.port_usb.in_waiting > 0:
                surowe = self.port_usb.read(self.port_usb.in_waiting)
                self._serial_bufor += surowe.decode("utf-8", errors="replace")
                while "\n" in self._serial_bufor:
                    linia, self._serial_bufor = self._serial_bufor.split("\n", 1)
                    linia = linia.strip()
                    if linia:
                        self._obsluz_linie_serial(linia)
        except Exception as e:
            self.pisz(f"[USB Rozłączono] {e}")
            self.wybor_portu.set("DEMO (Symulator)")
            self.zmien_port("DEMO (Symulator)")
            return
        self._serial_job = self.after(60, self._czytaj_serial_cyklicznie)

    def _obsluz_linie_serial(self, linia):
        if linia.startswith("{"):
            try:
                pakiet = json.loads(linia)
            except json.JSONDecodeError:
                self.pisz(f"[RX] {linia}")
                return

            if "readings" in pakiet:
                try:
                    czas_ms = float(pakiet.get("scan_ms", 0))
                    dane = {f"{r['a']}-{r['b']}": float(r["mv"]) for r in pakiet["readings"]}
                except (KeyError, TypeError, ValueError) as e:
                    self.pisz(f"[RX Błąd formatu JSON] {e}")
                    return

                if self.pokaz_pelny_json.get():
                    self.pisz(f"[RX JSON] {linia}")
                else:
                    self.pisz(f"[RX JSON] Odebrano {len(dane)} pomiarów ({czas_ms:.0f} ms)")

                self._anuluj_timeout_usb()
                akcja = self._oczekiwana_akcja
                self._oczekiwana_akcja = None

                if akcja == "kalibracja":
                    self._finalizuj_kalibracje_z_danych(dane)
                elif akcja == "wzorzec":
                    self._finalizuj_wzorzec_z_danych(dane, czas_ms)
                else:
                    if self.wzorzec is None:
                        self.pisz("Odebrano skan z płytki — kliknij [★ Zapisz wzorzec], aby zapisać go jako bazę.")
                    else:
                        self._finalizuj_test_z_danych(dane, czas_ms)
                return

        self.pisz(f"[RX] {linia}")

    def _uruchom_timeout_usb(self, akcja):
        self._anuluj_timeout_usb()
        self._oczekiwana_akcja = akcja
        self._timeout_job = self.after(4500, self._na_timeout_usb)

    def _anuluj_timeout_usb(self):
        if self._timeout_job is not None:
            try:
                self.after_cancel(self._timeout_job)
            except Exception:
                pass
            self._timeout_job = None

    def _na_timeout_usb(self):
        self._timeout_job = None
        if self._oczekiwana_akcja is not None:
            self._oczekiwana_akcja = None
            msg = "Tester nie odesłał JSON-a w 4.5 s — sprawdź kod mikrokontrolera lub kabel."
            self.baner.configure(fg_color="#1D170C", border_color="#D97706")
            self.baner_tytul.configure(text="●  BRAK ODPOWIEDZI USB", text_color="#FBBF24")
            self.baner_opis.configure(text=msg)
            self.pisz(msg)

    # ------------------------------------------------------------------
    # AKCJE: KALIBRUJ, ZAPISZ WZORZEC, TESTUJ
    # ------------------------------------------------------------------
    def kalibruj(self):
        if not messagebox.askokcancel(
            "Kalibracja (tarowanie kabli)",
            "Przed kalibracją ZDEJMIJ PŁYTKĘ z testera.\n\n"
            "Zewrzyj dwie dowolne igły przewodem (w trybie DEMO symulowane automatycznie) i kliknij OK."
        ):
            return
        if self.port_usb is not None and self.port_usb.is_open:
            try:
                self.port_usb.write(b"SCAN\n")
                self.pisz("[TX] SCAN (kalibracja)")
                self._uruchom_timeout_usb("kalibracja")
            except Exception as e:
                messagebox.showwarning("Błąd USB", str(e))
        else:
            nowe_r_cal = round(random.uniform(138.0, 152.0), 1)
            self._zastosuj_kalibracje(nowe_r_cal)

    def _finalizuj_kalibracje_z_danych(self, dane):
        try:
            przewodzace = [v for v in dane.values() if v < PROG_OTWARTY_MV]
            if len(przewodzace) > 4:
                raise RuntimeError("Wykryto wiele połączeń — zdejmij płytkę z testera przed kalibracją!")
            if not przewodzace:
                raise RuntimeError("Nie wykryto zwory kalibracyjnej — zewrzyj dwie igły przewodem.")
            min_mv = min(przewodzace)
            if min_mv >= PROG_ZWORY_KAL_MV:
                raise RuntimeError(f"Za duży opór zwory ({min_mv:.0f} mV) — sprawdź styk przewodu.")
            nowe_r_cal = max(0.0, R_REF * min_mv / (VCC_MV - min_mv))
            if not (20.0 <= nowe_r_cal <= 450.0):
                raise RuntimeError(f"Nierealny wynik ({nowe_r_cal:.0f} Ω) — pozostawiono R_cal = {self.r_cal:.1f} Ω.")
            self._zastosuj_kalibracje(round(nowe_r_cal, 1))
        except Exception as e:
            messagebox.showwarning("Kalibracja odrzucona", str(e))
            self.pisz(f"Kalibracja przerwana: {e}")

    def _zastosuj_kalibracje(self, nowe_r_cal):
        self.r_cal = nowe_r_cal
        self.lbl_tab_info.configure(text=f"TOL. ±{int(TOLERANCJA * 100)}% · R_CAL {self.r_cal:.1f} Ω")
        self.pisz(f"Skalibrowano opór własny kabli: R_cal = {self.r_cal:.1f} Ω.")
        if self.wzorzec is not None:
            self.pisz("Wskazówka: po nowej kalibracji warto zapisać wzorzec ponownie.")

    def zapisz_wzorzec(self):
        if self.port_usb is not None and self.port_usb.is_open:
            try:
                self.port_usb.write(b"SCAN\n")
                self.pisz("[TX] SCAN (wzorzec)")
                self._uruchom_timeout_usb("wzorzec")
            except Exception as e:
                self.pisz(f"Błąd wysyłania USB: {e}")
        else:
            dane, czas_ms = zrob_pomiar_demo(self.elementy, r_cal=self.r_cal)
            self._finalizuj_wzorzec_z_danych(dane, czas_ms)

    def _finalizuj_wzorzec_z_danych(self, dane, czas_ms):
        self.wzorzec = dane
        try:
            with open(PLIK_WZORZEC, "w", encoding="utf-8") as f:
                json.dump(self.wzorzec, f, indent=2)
        except Exception as e:
            self.pisz(f"Ostrzeżenie zapisu {PLIK_WZORZEC.name}: {e}")
        self.kpi_czas.configure(text=f"{czas_ms:.0f} ms")
        self.pisz(f"Zapisano wzorzec ({len(self.wzorzec)} pomiarów w {czas_ms:.0f} ms).")
        self.baner.configure(fg_color="#1D170C", border_color="#D97706")
        self.baner_tytul.configure(text="●  WZORZEC SKALIBROWANY", text_color="#FBBF24")
        self.baner_opis.configure(text="Włóż kolejną płytkę i kliknij [▶ Testuj płytkę]")

    def testuj(self):
        if self.wzorzec is None:
            self.pisz("Najpierw zapisz wzorzec!")
            return
        if self.port_usb is not None and self.port_usb.is_open:
            try:
                self.port_usb.write(b"SCAN\n")
                self.pisz("[TX] SCAN (test)")
                self._uruchom_timeout_usb("test")
            except Exception as e:
                self.pisz(f"Błąd wysyłania USB: {e}")
        else:
            scen = None if self.scenariusz.get() == "dobra płytka" else self.scenariusz.get()
            dane, czas_ms = zrob_pomiar_demo(self.elementy, scen, r_cal=self.r_cal)
            self._finalizuj_test_z_danych(dane, czas_ms)

    def _finalizuj_test_z_danych(self, pomiar, czas_ms):
        wyniki = porownaj(self.wzorzec, pomiar, self.elementy, r_cal=self.r_cal)
        obraz = narysuj(wyniki, self.baza_2x, self.orig_size)
        self._ostatni_obraz_pil = obraz
        if not self.pelny_ekran_tabeli:
            self.pokaz_zdjecie(obraz)

        wyniki_posortowane = sorted(wyniki, key=lambda w: w["status"] == "OK")
        bledy = [w for w in wyniki if w["status"] != "OK"]

        self.odswiez_tabele(wyniki_posortowane)
        try:
            zapisz_wiersz_csv(wyniki, czas_ms, self.wybor_portu.get())
        except Exception as e:
            self.pisz(f"Nie udało się dopisać do CSV: {e}")

        self.licznik_testow += 1
        nr = self.licznik_testow
        self.historia.append({
            "nr": nr, "czas_ms": czas_ms, "wyniki": wyniki_posortowane,
            "obraz": obraz, "bledy": bledy, "n_bledow": len(bledy),
        })
        if len(self.historia) > 10:
            self.historia.pop(0)
        self.aktywny_nr = nr
        self._odswiez_pasek_historii()

        if bledy:
            self.licznik_fail += 1
            self.pisz(f"#{nr} FAIL ({czas_ms:.0f} ms): " + ", ".join(f"{b['nazwa']}={b['status']}" for b in bledy))
        else:
            self.licznik_pass += 1
            self.pisz(f"#{nr} PASS ({czas_ms:.0f} ms) – wszystkie elementy OK.")

        self._ustaw_baner_wyniku(bledy, czas_ms)
        self.kpi_czas.configure(text=f"{czas_ms:.0f} ms")
        self.kpi_seria.configure(text=f"{self.licznik_pass} PASS · {self.licznik_fail} FAIL")

    # ------------------------------------------------------------------
    def odswiez_tabele(self, wyniki):
        self.ostatnie_wyniki = wyniki
        self.wiersze_tabeli = []
        for widget in self.tabela.winfo_children():
            widget.destroy()

        s = self.skala_tabeli
        wys_wiersza = int(44 * s)
        f_nazwa = ctk.CTkFont("Segoe UI", max(11, int(14 * s)), "bold")
        f_val = ctk.CTkFont("Consolas", max(10, int(12 * s)))
        f_val_b = ctk.CTkFont("Consolas", max(10, int(12 * s)), "bold")
        f_delta = ctk.CTkFont("Consolas", max(9, int(11 * s)))
        f_delta_b = ctk.CTkFont("Consolas", max(9, int(11 * s)), "bold")
        f_badge = ctk.CTkFont("Segoe UI", max(9, int(11 * s)), "bold")
        szer_paska = int(58 * s)

        style_statusow = {
            ZIELONY:      ("#141B26", "#1E293B", "#10B981", "#0B241D", "#34D399"),
            CZERWONY:     ("#231218", "#5B1E2E", "#F43F5E", "#3D121E", "#FDA4AF"),
            POMARANCZOWY: ("#221A10", "#5C3D14", "#F59E0B", "#36250B", "#FCD34D"),
            ZOLTY:        ("#1F1C10", "#4F4614", "#EAB308", "#302B0B", "#FDE047"),
        }

        for w in wyniki:
            tlo_row, ramka, pasek, tlo_badge, txt_badge = style_statusow.get(
                w["kolor"], ("#141B26", BORDER, "#64748B", BG_ELEV, TEXT_MAIN)
            )
            wiersz = ctk.CTkFrame(self.tabela, height=wys_wiersza, fg_color=tlo_row, corner_radius=6,
                                  border_width=1, border_color=ramka)
            wiersz.pack(fill="x", pady=2)
            wiersz.pack_propagate(False)
            self._konfiguruj_kolumny_wiersza(wiersz)
            wiersz.grid_rowconfigure(0, weight=1)
            self.wiersze_tabeli.append(wiersz)

            lewy = ctk.CTkFrame(wiersz, fg_color="transparent")
            lewy.grid(row=0, column=0, sticky="w", padx=(6, 4))
            ctk.CTkFrame(lewy, width=4, height=int(22 * s), fg_color=pasek, corner_radius=2).pack(side="left", padx=(0, 8))
            ctk.CTkLabel(lewy, text=w["nazwa"], text_color=TEXT_MAIN, font=f_nazwa).pack(side="left")

            ctk.CTkLabel(wiersz, text=w["wzor"], text_color=TEXT_SUB, font=f_val).grid(
                row=0, column=1, sticky="w", padx=4)
            ctk.CTkLabel(wiersz, text=w["pomiar"],
                         text_color=TEXT_MAIN if w["status"] == "OK" else txt_badge,
                         font=f_val_b if w["status"] != "OK" else f_val).grid(
                row=0, column=2, sticky="w", padx=4)

            delta_box = ctk.CTkFrame(wiersz, fg_color="transparent")
            delta_box.grid(row=0, column=3, sticky="w", padx=4)
            ctk.CTkLabel(delta_box, text=w["delta"],
                         text_color=TEXT_MUTED if w["status"] == "OK" else txt_badge,
                         font=f_delta_b if w["status"] != "OK" else f_delta,
                         height=int(14 * s)).pack(anchor="w")

            pasek_tlo = ctk.CTkFrame(delta_box, width=szer_paska, height=4, fg_color="#1E293B", corner_radius=2)
            pasek_tlo.pack(anchor="w", pady=(2, 0))
            pasek_tlo.pack_propagate(False)
            if w["delta_num"] is not None:
                ulamek = max(0.08, min(1.0, abs(w["delta_num"]) / (TOLERANCJA * 200.0)))
                kolor_p = ("#10B981" if w["status"] == "OK" else
                           ("#EAB308" if w["status"] == "BLISKO GRANICY" else "#F43F5E"))
                ctk.CTkFrame(pasek_tlo, width=int(szer_paska * ulamek), height=4,
                             fg_color=kolor_p, corner_radius=2).pack(side="left")
            elif w["status"] != "OK":
                ctk.CTkFrame(pasek_tlo, width=szer_paska, height=4,
                             fg_color=pasek, corner_radius=2).pack(side="left")
            else:
                ctk.CTkFrame(pasek_tlo, width=int(szer_paska * 0.32), height=4,
                             fg_color="#10B981", corner_radius=2).pack(side="left")

            ctk.CTkLabel(wiersz, text=w["status"], width=int(120 * s), height=int(26 * s),
                         corner_radius=4, fg_color=tlo_badge, text_color=txt_badge,
                         font=f_badge).grid(row=0, column=4, sticky="e", padx=(4, 10))

    def _odswiez_pasek_historii(self):
        for w in self.pasek_historii.winfo_children():
            w.destroy()
        for item in self.historia[-7:]:
            jest_ok = item["n_bledow"] == 0
            aktywny = (item["nr"] == self.aktywny_nr)
            tlo = ("#0F352A" if jest_ok else "#3D121E") if aktywny else ("#0B221B" if jest_ok else "#231016")
            ramka = "#38BDF8" if aktywny else ("#10B981" if jest_ok else "#F43F5E")
            kolor_txt = "#34D399" if jest_ok else "#FDA4AF"
            etykieta = f"#{item['nr']} {'PASS' if jest_ok else 'FAIL'}"
            ctk.CTkButton(self.pasek_historii, text=etykieta, width=68, height=26,
                          corner_radius=6, fg_color=tlo, hover_color="#1E293B",
                          border_width=1, border_color=ramka, text_color=kolor_txt,
                          font=ctk.CTkFont("Consolas", 10, "bold"),
                          command=lambda n=item["nr"]: self.pokaz_z_historii(n)).pack(side="left", padx=2)

    def _ustaw_baner_wyniku(self, bledy, czas_ms, z_historii_nr=None):
        prefiks = f"Z historii (#{z_historii_nr})  •  " if z_historii_nr else ""
        if bledy:
            ma_zwarcie = any(b["status"] == "ZWARCIE" for b in bledy)
            podtytul = (f"{prefiks}Czas: {czas_ms:.0f} ms  •  Zwarcie na linii przed podaniem prądu (sprawdź całą ścieżkę)"
                        if ma_zwarcie else
                        f"{prefiks}Czas: {czas_ms:.0f} ms  •  Wykryto błędy przed podaniem zasilania")
            self.baner.configure(fg_color="#231016", border_color="#E11D48")
            self.baner_tytul.configure(text=f"●  FAIL — WYKRYTO {odmiana_bledow(len(bledy)).upper()}",
                                       text_color="#FB7185")
            self.baner_opis.configure(text=podtytul)
        else:
            self.baner.configure(fg_color="#0B221B", border_color="#10B981")
            self.baner_tytul.configure(text="●  PASS — PŁYTKA SPRAWNA", text_color="#34D399")
            self.baner_opis.configure(
                text=f"{prefiks}Czas skanu: {czas_ms:.0f} ms  •  Wszystkie węzły w normie (±{int(TOLERANCJA*100)}%)"
            )

    def pokaz_z_historii(self, nr):
        item = next((x for x in self.historia if x["nr"] == nr), None)
        if item is None:
            return
        self.aktywny_nr = nr
        self.pokaz_zdjecie(item["obraz"])
        self.odswiez_tabele(item["wyniki"])
        self._ustaw_baner_wyniku(item["bledy"], item["czas_ms"], z_historii_nr=nr)
        self.kpi_czas.configure(text=f"{item['czas_ms']:.0f} ms")
        self._odswiez_pasek_historii()

    def zamknij(self):
        self._zatrzymaj_nasluch_serial()
        if self.port_usb is not None:
            try:
                self.port_usb.close()
            except Exception:
                pass
        self.destroy()


if __name__ == "__main__":
    if PLIK_ZDJECIE.exists() and PLIK_ELEMENTY.exists():
        app = Aplikacja()
        app.protocol("WM_DELETE_WINDOW", app.zamknij)
        app.mainloop()
    else:
        print(f"Brakuje {PLIK_ZDJECIE} lub {PLIK_ELEMENTY} w folderze {FOLDER}")