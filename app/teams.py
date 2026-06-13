"""Team-name aliases: Golpredictor predictions are in Spanish, the score API is in
English. We normalize both sides to a canonical key so matches auto-link.

Keys are accent-stripped, lowercased Spanish names; values are the accent-stripped,
lowercased English form the score API uses. Same-language and accent-only
differences (México/Mexico) already collapse without an entry here.

Not exhaustive for all 48 nations — extend as needed, or use the manual link
endpoint (POST /matches/{id}/link) for any pair the map doesn't cover.
"""

from __future__ import annotations

# spanish_normalized -> english_normalized
TEAM_ALIASES: dict[str, str] = {
    "sudafrica": "south africa",
    "estados unidos": "united states",
    "eeuu": "united states",
    "inglaterra": "england",
    "alemania": "germany",
    "espana": "spain",
    "francia": "france",
    "brasil": "brazil",
    "paises bajos": "netherlands",
    "holanda": "netherlands",
    "belgica": "belgium",
    "croacia": "croatia",
    "suiza": "switzerland",
    "japon": "japan",
    "corea del sur": "south korea",
    "arabia saudita": "saudi arabia",
    "marruecos": "morocco",
    "camerun": "cameroon",
    "costa de marfil": "ivory coast",
    "egipto": "egypt",
    "tunez": "tunisia",
    "argelia": "algeria",
    "polonia": "poland",
    "dinamarca": "denmark",
    "suecia": "sweden",
    "noruega": "norway",
    "escocia": "scotland",
    "gales": "wales",
    "irlanda": "ireland",
    "nueva zelanda": "new zealand",
    "catar": "qatar",
    "iran": "iran",
    "irak": "iraq",
    "emiratos arabes unidos": "united arab emirates",
    "jordania": "jordan",
    "turquia": "turkey",
    "grecia": "greece",
    "republica checa": "czech republic",
    "ucrania": "ukraine",
    "corea del norte": "north korea",
    "bosnia y herzegovina": "bosnia and herzegovina",
    "curazao": "curacao",
    "cabo verde": "cape verde",
    "rd congo": "dr congo",
}
