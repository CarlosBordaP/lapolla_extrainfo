"""OCR: parse a Golpredictor prediction screenshot into structured data.

Default engine is Google Gemini 1.5 Pro (free tier), which returns the table as
CSV that we parse. Claude vision is kept as an alternative engine. The parsed
result is NOT saved directly — it feeds a human confirm/edit step before the DB.
"""

from __future__ import annotations

import base64
import io
import json
import re
from dataclasses import dataclass, field

from app.config import get_settings

# --- Prompts -----------------------------------------------------------------

_GEMINI_PROMPT = """Analiza esta captura de la pantalla de pronósticos de \
Golpredictor para UN partido y extrae los datos.

Devuelve EXCLUSIVAMENTE CSV (sin texto adicional, sin ```, sin explicaciones).

Estructura exacta:
1) Primera línea:  PARTIDO,<equipo local>,<equipo visitante>,<fecha y hora del encabezado>
2) Si ARRIBA de la tabla, después de un título "Pronóstico:", aparece un marcador \
(es el pronóstico del usuario que subió la imagen, que NO está en la tabla), \
devuélvelo como segunda línea:  TOP,<local>,<visitante>  (si no se ve, omite esta línea)
3) Línea de encabezado:  usuario,nombre,local,visitante,acumulado
4) Una línea por cada participante de la tabla:
   - usuario: la columna "Usuario"
   - nombre: la columna "Nombre" (si tiene comas, reemplázalas por espacios)
   - local: primer número del pronóstico (goles del equipo local); déjalo VACÍO si no se ve
   - visitante: segundo número del pronóstico (goles del equipo visitante); déjalo VACÍO si no se ve
   - acumulado: número entero de la columna de puntos acumulados antes de este partido \
(puede llamarse "Pts. Ac.", "Acumulado", "Pts Ac" o similar); déjalo VACÍO si la columna \
no aparece o el valor está en blanco

Reglas:
- El pronóstico aparece como dos números separados por guion entre las banderas \
(ej. "2 - 0" => local=2, visitante=0).
- Si un participante NO puso pronóstico (el campo aparece en blanco o con "–"), \
deja AMBOS campos vacíos: usuario,nombre,,,<acumulado>
- Si solo se ve uno de los dos números, pon el que se ve y deja el otro VACÍO.
- El marcador del título superior (TOP) es de quien sube la imagen y NO se repite \
en la tabla; extráelo aparte.
- No inventes filas ni números; extrae exactamente lo que se ve.
"""


@dataclass
class ParsedScreenshot:
    home_team: str
    away_team: str
    kickoff_text: str
    predictions: list[dict]  # {username, display_name, pred_home, pred_away}
    top_home: int | None = None  # uploader's own prediction (shown above the table)
    top_away: int | None = None
    raw: str = field(default="", repr=False)  # raw model output (CSV/JSON) for validation

    def to_dict(self) -> dict:
        return {
            "home_team": self.home_team,
            "away_team": self.away_team,
            "kickoff_text": self.kickoff_text,
            "predictions": self.predictions,
            "top": (
                {"pred_home": self.top_home, "pred_away": self.top_away}
                if self.top_home is not None
                else None
            ),
            "raw_csv": self.raw,
        }


def extract_predictions(image_bytes: bytes, media_type: str = "image/jpeg") -> ParsedScreenshot:
    """Dispatch to the configured OCR engine."""
    provider = get_settings().ocr_provider.lower()
    if provider == "gemini":
        return _extract_gemini(image_bytes)
    if provider == "claude":
        return _extract_claude(image_bytes, media_type)
    raise RuntimeError(f"Proveedor OCR desconocido: {provider!r} (usa 'gemini' o 'claude').")


# --- Gemini ------------------------------------------------------------------

def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return text.strip()


def _parse_score(s: str) -> int | None:
    s = s.strip()
    try:
        return int(s) if s else None
    except ValueError:
        return None


def parse_csv(raw: str) -> ParsedScreenshot:
    """Parse the CSV the model returns into a ParsedScreenshot. Robust to commas
    in names. Supports 5-column format (with acumulado) and 4-column legacy format."""
    home = away = kickoff = ""
    top_home = top_away = None
    predictions: list[dict] = []
    has_accumulated_col = False
    for line in _strip_fences(raw).splitlines():
        if not line.strip():
            continue
        parts = [p.strip().strip('"') for p in line.split(",")]
        head = parts[0].lower()
        if head == "partido":
            home = parts[1] if len(parts) > 1 else ""
            away = parts[2] if len(parts) > 2 else ""
            kickoff = ", ".join(parts[3:]) if len(parts) > 3 else ""
            continue
        if head == "top":  # uploader's own prediction (above the table)
            try:
                top_home, top_away = int(parts[1]), int(parts[2])
            except (ValueError, IndexError):
                pass
            continue
        if head == "usuario":  # header row — detect 5-column format
            has_accumulated_col = len(parts) >= 5 and "acumulado" in [p.lower() for p in parts]
            continue
        if has_accumulated_col:
            if len(parts) < 5:
                continue
            username = parts[0]
            name = " ".join(parts[1:-3]).strip() or username
            pred_home = _parse_score(parts[-3])
            pred_away = _parse_score(parts[-2])
            accumulated = _parse_score(parts[-1])
        else:
            if len(parts) < 4:
                continue
            username = parts[0]
            name = " ".join(parts[1:-2]).strip() or username
            pred_home = _parse_score(parts[-2])
            pred_away = _parse_score(parts[-1])
            accumulated = None
        predictions.append({
            "username": username, "display_name": name,
            "pred_home": pred_home, "pred_away": pred_away,
            "accumulated": accumulated,
        })
    return ParsedScreenshot(home, away, kickoff, predictions, top_home, top_away, raw=raw)


_STANDINGS_PROMPT = """Extrae la tabla de posiciones de Golpredictor de esta imagen.
Devuelve EXCLUSIVAMENTE CSV con encabezado `usuario,puntos` y una fila por
participante: la columna "Usuario" y la columna "Puntos" (número entero). Lee el
usuario con cuidado. Sin ``` ni texto adicional."""


def extract_standings(image_bytes: bytes) -> list[dict]:
    """OCR a Golpredictor standings screenshot -> [{username, points}]. Gemini only."""
    settings = get_settings()
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY no está configurada — requerida para el OCR.")
    from google import genai
    from PIL import Image

    client = genai.Client(api_key=settings.gemini_api_key)
    image = Image.open(io.BytesIO(image_bytes))
    response = client.models.generate_content(
        model=settings.gemini_model, contents=[_STANDINGS_PROMPT, image]
    )
    rows = []
    for line in _strip_fences(response.text or "").splitlines():
        parts = [p.strip().strip('"') for p in line.split(",")]
        if not parts or parts[0].lower() == "usuario":
            continue
        try:
            rows.append({"username": parts[0], "points": int(parts[-1])})
        except (ValueError, IndexError):
            continue
    return rows


def _extract_gemini(image_bytes: bytes) -> ParsedScreenshot:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY no está configurada — requerida para el OCR (Gemini).")
    from google import genai  # imported lazily so the app runs without the dep
    from PIL import Image

    client = genai.Client(api_key=settings.gemini_api_key)
    image = Image.open(io.BytesIO(image_bytes))
    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=[_GEMINI_PROMPT, image],
    )
    return parse_csv(response.text or "")


# --- Claude (alternative engine) ---------------------------------------------

_CLAUDE_SYSTEM = """You extract football match predictions from a screenshot of \
the Golpredictor prediction screen. Each table row is one participant: Usuario \
(unique handle), Nombre (display name), Pronostico (predicted score "H - A"). \
IGNORE the logged-in user's own prediction shown on top, outside the table — it's \
a duplicate. Extract every table row exactly."""

_CLAUDE_SCHEMA = {
    "type": "object",
    "properties": {
        "match": {
            "type": "object",
            "properties": {
                "home_team": {"type": "string"},
                "away_team": {"type": "string"},
                "kickoff_text": {"type": "string"},
            },
            "required": ["home_team", "away_team", "kickoff_text"],
            "additionalProperties": False,
        },
        "predictions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "username": {"type": "string"},
                    "display_name": {"type": "string"},
                    "pred_home": {"type": "integer"},
                    "pred_away": {"type": "integer"},
                },
                "required": ["username", "display_name", "pred_home", "pred_away"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["match", "predictions"],
    "additionalProperties": False,
}


def _extract_claude(image_bytes: bytes, media_type: str) -> ParsedScreenshot:
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY no está configurada — requerida para el OCR (Claude).")
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
    response = client.messages.create(
        model=settings.ocr_model,
        max_tokens=16000,
        system=_CLAUDE_SYSTEM,
        output_config={"format": {"type": "json_schema", "schema": _CLAUDE_SCHEMA}},
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_b64}},
                {"type": "text", "text": "Extract the match and every prediction row."},
            ],
        }],
    )
    text = next(b.text for b in response.content if b.type == "text")
    data = json.loads(text)
    return ParsedScreenshot(
        home_team=data["match"]["home_team"],
        away_team=data["match"]["away_team"],
        kickoff_text=data["match"]["kickoff_text"],
        predictions=data["predictions"],
        raw=text,
    )
