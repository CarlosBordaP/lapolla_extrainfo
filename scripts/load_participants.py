"""Load the pool participants into Polla via POST /participants/bulk.

Authoritative list (52 users) from the Golpredictor roster, with sign-up time.
Columns: username | display name | registration (Bogotá local "DD Mon - HH:MM").
Points are intentionally NOT loaded. Idempotent.

Usage:  .venv/bin/python scripts/load_participants.py [base_url]
"""

from __future__ import annotations

import datetime as dt
import sys

import httpx

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
BOGOTA_TO_UTC = dt.timedelta(hours=5)  # Bogotá is UTC-5
MONTHS = {"Ene": 1, "Feb": 2, "Mar": 3, "Abr": 4, "May": 5, "Jun": 6,
          "Jul": 7, "Ago": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dic": 12}

# username | display name | registration (Bogotá)
RAW = """
ale_rondon | Alejandro Rondón Arango | 06 Jun - 14:04
aceventura82 | O z | 08 May - 16:57
arturov | Julián Valderrama | 23 May - 19:59
fonse | Alberto Fonseca | 11 Jun - 00:24
anamariah | Ana Maria Hernandez | 11 Jun - 12:32
sebasrondon | Sebastian Rondon | 07 Jun - 00:33
almaro71 | Alexander Martinez | 21 May - 11:09
djaramip | Dayro Valentierra | 22 May - 09:46
hagiplox | Harryson Avila | 10 Jun - 16:32
xxgiovany | Giovany Rondón | 09 Jun - 21:23
jeduard7 | Eduard Quiasua | 10 Jun - 22:07
marysita | Marysita Sánchez | 01 Jun - 15:43
xavival89 | Javier Arturo Valderrama Martinez | 08 Jun - 18:19
clamajagra | Claudia Jaramillo | 21 May - 08:49
kqatarb | Kevin L | 22 May - 13:31
hernachis | Hernán Hernández | 10 Jun - 10:20
wladino1 | Wilson Esteven Ladino Criollo | 11 Jun - 11:31
oasilv | Orlando Silva | 13 May - 16:21
jimenav | Jimena Valderrama | 14 May - 20:57
kevinb | Kevin Andrés Borda Penagos | 21 May - 08:58
yoyisyoli65 | Yolanda Perez | 21 May - 08:58
lizbautista | Liz Bautista | 02 Jun - 22:04
kliche | Carlos Mario Borda Penagos | 05 Jun - 15:39
mrondon91 | Michael Rondón | 09 Jun - 11:11
andman01 | Andrea Mantilla | 10 Jun - 16:33
nelsongutier | Nelson Gutierrez | 10 Jun - 16:36
sjnietor | Steffen Nieto | 13 May - 12:18
neavagil | Nelson Valderrama Gil | 10 Jun - 20:21
pipe1017 | Paguen de Una vez | 19 May - 19:25
afrondon | Andres Rondon | 06 Jun - 20:51
juanc2020 | Juan Camilo Ramírez López | 10 Jun - 09:28
dadatope | Daniel Eduardo Torres Perez | 11 Jun - 08:53
juanitaamaya | Juanita Amaya Valderrama | 11 Jun - 13:41
fonserate | Sandra Fonseca | 17 May - 10:29
andressosara | Andres Sosa | 01 Jun - 21:49
diracco | Diana Convers | 03 Jun - 16:46
andresduqueb | Andres Duque | 08 Jun - 18:27
refz29 | Ricardo Esteban Fonseca Zarate | 08 Jun - 23:23
ramirez026 | Henry Ramirez | 02 Jun - 14:06
oswal83 | Osw4L Mr RoboT | 08 Jun - 11:00
bordacarlos | Carlos Eduardo Borda | 09 Jun - 09:07
tomasamaya | Tomas Amaya | 09 Jun - 11:37
sebasleon215 | Sebastian Leon | 10 Jun - 09:49
fgc22 | Fernando Luis Gil Correa | 10 Jun - 13:21
andresmcj | El Mayoral Del Tranvía | 11 Jun - 13:07
angelabust | Angela Maria Bustos Orjuela | 28 May - 12:10
nurisg | Nuris Lizeth García | 02 Jun - 08:58
juandarod26 | Juan David Rodriguez Arango | 09 Jun - 16:30
ivanchop123 | Iván Ernesto Piraquive Lopez | 11 Jun - 12:56
donfabio | Fabioarturo Valderrama | 01 Jun - 19:47
seanroar | Sergio Rodriguez | 09 Jun - 16:37
mayeli | Claudia Mayeli Guerrero | 11 Jun - 12:29
"""


def parse_registration(s: str) -> str:
    """'06 Jun - 14:04' (Bogotá) -> UTC ISO with Z."""
    day_mon, time = [x.strip() for x in s.split("-")]
    day, mon = day_mon.split()
    hh, mm = time.split(":")
    bogota = dt.datetime(2026, MONTHS[mon], int(day), int(hh), int(mm))
    return (bogota + BOGOTA_TO_UTC).isoformat() + "Z"


def build() -> list[dict]:
    out = []
    for line in RAW.strip().splitlines():
        username, name, reg = [p.strip() for p in line.split("|")]
        out.append({
            "username": username,
            "display_name": name,
            "registered_at": parse_registration(reg),
        })
    return out


def main() -> None:
    participants = build()
    print(f"Preparados {len(participants)} jugadores. Cargando en {BASE_URL} …")
    r = httpx.post(
        f"{BASE_URL}/participants/bulk",
        json={"participants": participants},
        cookies={"polla_user": "kevinb"},  # admin
        timeout=30,
    )
    print(r.status_code, r.json())


if __name__ == "__main__":
    main()
