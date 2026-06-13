"""Load the 2026 World Cup group-stage fixture into Polla via POST /matches/bulk.

Source times are US Eastern (EDT = UTC-4 in June) and converted to UTC. Team names
are translated to Spanish (to match the Golpredictor pool). Idempotent: re-running
skips matches that already exist.

Usage:  .venv/bin/python scripts/load_wc2026_groups.py [base_url]
"""

from __future__ import annotations

import datetime as dt
import sys

import httpx

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
ET_TO_UTC = dt.timedelta(hours=4)  # EDT is UTC-4 in June

# date | HH:MM ET | Home vs Away | Group  (full group stage, 72 matches)
RAW = """
2026-06-11 | 15:00 ET | Mexico vs South Africa | Group A
2026-06-11 | 22:00 ET | South Korea vs Czechia | Group A
2026-06-12 | 15:00 ET | Canada vs Bosnia and Herzegovina | Group B
2026-06-12 | 21:00 ET | United States vs Paraguay | Group D
2026-06-13 | 15:00 ET | Qatar vs Switzerland | Group B
2026-06-13 | 21:00 ET | Brazil vs Morocco | Group C
2026-06-14 | 00:00 ET | Haiti vs Scotland | Group C
2026-06-14 | 01:00 ET | Australia vs Türkiye | Group D
2026-06-14 | 13:00 ET | Germany vs Curaçao | Group E
2026-06-14 | 16:00 ET | Netherlands vs Japan | Group F
2026-06-14 | 19:00 ET | Ivory Coast vs Ecuador | Group E
2026-06-14 | 22:00 ET | Sweden vs Tunisia | Group F
2026-06-15 | 13:00 ET | Spain vs Cape Verde | Group H
2026-06-15 | 18:00 ET | Belgium vs Egypt | Group G
2026-06-15 | 18:00 ET | Saudi Arabia vs Uruguay | Group H
2026-06-16 | 00:00 ET | Iran vs New Zealand | Group G
2026-06-16 | 15:00 ET | France vs Senegal | Group I
2026-06-16 | 18:00 ET | Iraq vs Norway | Group I
2026-06-16 | 21:00 ET | Argentina vs Algeria | Group J
2026-06-17 | 00:00 ET | Austria vs Jordan | Group J
2026-06-17 | 13:00 ET | Portugal vs DR Congo | Group K
2026-06-17 | 16:00 ET | England vs Croatia | Group L
2026-06-17 | 19:00 ET | Ghana vs Panama | Group L
2026-06-17 | 22:00 ET | Uzbekistan vs Colombia | Group K
2026-06-18 | 12:00 ET | Czechia vs South Africa | Group A
2026-06-18 | 15:00 ET | Switzerland vs Bosnia and Herzegovina | Group B
2026-06-18 | 18:00 ET | Canada vs Qatar | Group B
2026-06-18 | 23:00 ET | Mexico vs South Korea | Group A
2026-06-19 | 15:00 ET | United States vs Australia | Group D
2026-06-19 | 18:00 ET | Scotland vs Morocco | Group C
2026-06-19 | 21:00 ET | Brazil vs Haiti | Group C
2026-06-20 | 00:00 ET | Türkiye vs Paraguay | Group D
2026-06-20 | 13:00 ET | Netherlands vs Sweden | Group F
2026-06-20 | 16:00 ET | Germany vs Ivory Coast | Group E
2026-06-20 | 19:00 ET | Ecuador vs Curaçao | Group E
2026-06-21 | 00:00 ET | Tunisia vs Japan | Group F
2026-06-21 | 12:00 ET | Spain vs Saudi Arabia | Group H
2026-06-21 | 15:00 ET | Belgium vs Iran | Group G
2026-06-21 | 18:00 ET | Uruguay vs Cape Verde | Group H
2026-06-21 | 21:00 ET | New Zealand vs Egypt | Group G
2026-06-22 | 13:00 ET | Argentina vs Austria | Group J
2026-06-22 | 17:00 ET | France vs Iraq | Group I
2026-06-22 | 20:00 ET | Norway vs Senegal | Group I
2026-06-22 | 23:00 ET | Jordan vs Algeria | Group J
2026-06-23 | 13:00 ET | Portugal vs Uzbekistan | Group K
2026-06-23 | 16:00 ET | England vs Ghana | Group L
2026-06-23 | 19:00 ET | Panama vs Croatia | Group L
2026-06-23 | 22:00 ET | Colombia vs DR Congo | Group K
2026-06-24 | 15:00 ET | Switzerland vs Canada | Group B
2026-06-24 | 15:00 ET | Bosnia and Herzegovina vs Qatar | Group B
2026-06-24 | 18:00 ET | Scotland vs Brazil | Group C
2026-06-24 | 18:00 ET | Morocco vs Haiti | Group C
2026-06-24 | 21:00 ET | Czechia vs Mexico | Group A
2026-06-24 | 21:00 ET | South Africa vs South Korea | Group A
2026-06-25 | 16:00 ET | Ecuador vs Germany | Group E
2026-06-25 | 16:00 ET | Curaçao vs Ivory Coast | Group E
2026-06-25 | 19:00 ET | Japan vs Sweden | Group F
2026-06-25 | 19:00 ET | Tunisia vs Netherlands | Group F
2026-06-25 | 22:00 ET | Türkiye vs United States | Group D
2026-06-25 | 22:00 ET | Paraguay vs Australia | Group D
2026-06-26 | 15:00 ET | Norway vs France | Group I
2026-06-26 | 15:00 ET | Senegal vs Iraq | Group I
2026-06-26 | 20:00 ET | Cape Verde vs Saudi Arabia | Group H
2026-06-26 | 20:00 ET | Uruguay vs Spain | Group H
2026-06-26 | 23:00 ET | Egypt vs Iran | Group G
2026-06-27 | 00:00 ET | New Zealand vs Belgium | Group G
2026-06-27 | 17:00 ET | Panama vs England | Group L
2026-06-27 | 17:00 ET | Croatia vs Ghana | Group L
2026-06-27 | 19:30 ET | Colombia vs Portugal | Group K
2026-06-27 | 19:30 ET | DR Congo vs Uzbekistan | Group K
2026-06-27 | 22:00 ET | Algeria vs Austria | Group J
2026-06-27 | 22:00 ET | Jordan vs Argentina | Group J
"""

ES = {
    "Mexico": "México", "South Africa": "Sudáfrica", "South Korea": "Corea del Sur",
    "Czechia": "República Checa", "Canada": "Canadá", "United States": "Estados Unidos",
    "Bosnia and Herzegovina": "Bosnia y Herzegovina", "Paraguay": "Paraguay", "Qatar": "Catar",
    "Switzerland": "Suiza", "Brazil": "Brasil", "Morocco": "Marruecos", "Haiti": "Haití",
    "Scotland": "Escocia", "Australia": "Australia", "Türkiye": "Turquía", "Germany": "Alemania",
    "Curaçao": "Curazao", "Netherlands": "Países Bajos", "Japan": "Japón",
    "Ivory Coast": "Costa de Marfil", "Ecuador": "Ecuador", "Sweden": "Suecia", "Tunisia": "Túnez",
    "Spain": "España", "Cape Verde": "Cabo Verde", "Belgium": "Bélgica", "Egypt": "Egipto",
    "Saudi Arabia": "Arabia Saudita", "Uruguay": "Uruguay", "Iran": "Irán",
    "New Zealand": "Nueva Zelanda", "France": "Francia", "Senegal": "Senegal", "Iraq": "Irak",
    "Norway": "Noruega", "Argentina": "Argentina", "Algeria": "Argelia", "Austria": "Austria",
    "Jordan": "Jordania", "Portugal": "Portugal", "DR Congo": "RD Congo", "England": "Inglaterra",
    "Croatia": "Croacia", "Ghana": "Ghana", "Panama": "Panamá", "Uzbekistan": "Uzbekistán",
    "Colombia": "Colombia",
}


def es(name: str) -> str:
    return ES.get(name, name)


def build() -> list[dict]:
    out = []
    for line in RAW.strip().splitlines():
        date, et, teams, _group = [p.strip() for p in line.split("|")]
        et = et.replace(" ET", "").strip()
        home, away = [t.strip() for t in teams.split(" vs ")]
        kickoff_utc = dt.datetime.strptime(f"{date} {et}", "%Y-%m-%d %H:%M") + ET_TO_UTC
        out.append({
            "home_team": es(home), "away_team": es(away),
            "kickoff_utc": kickoff_utc.isoformat(), "stage": "group",
        })
    return out


def main() -> None:
    matches = build()
    print(f"Preparados {len(matches)} partidos. Cargando en {BASE_URL} …")
    r = httpx.post(
        f"{BASE_URL}/matches/bulk",
        json={"matches": matches},
        cookies={"polla_user": "kevinb"},  # admin
        timeout=30,
    )
    print(r.status_code, r.json())


if __name__ == "__main__":
    main()
