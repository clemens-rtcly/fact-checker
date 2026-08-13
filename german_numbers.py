"""
Stufe 0 — Normalisierung deutscher Zahlen & Entity-Extraktion.

Deterministisch, ohne Abhängigkeiten. Deckt beide Schreibwelten ab:
  Artikel:    "5,3 Millionen Euro", "28 zu 11", "2019", "rund drei Prozent"
  Transkript: "fünf Komma drei Millionen Euro", "achtundzwanzig zu elf",
              "zweitausendneunzehn", "zwanzigsiebenundzwanzig" (Jahres-Lesart)

Entity-Typen (kompatibel zum Alignment-JSON-Schema):
  geld     norm "5300000 EUR"
  prozent  norm "3 %"
  zahl     norm "18" oder Verhältnis "28:11"
  datum    norm "2019"

Personennamen liegen bewusst nicht hier, sondern in ner.py — sie brauchen
ein anderes Verfahren als Zahlen.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


# --------------------------------------------------------------- Zahlwörter

_UNITS = {
    "null": 0, "ein": 1, "eins": 1, "eine": 1, "einen": 1, "einem": 1,
    "einer": 1, "eines": 1, "zwei": 2, "zwo": 2, "drei": 3, "vier": 4,
    "fünf": 5, "fuenf": 5, "sechs": 6, "sieben": 7, "acht": 8, "neun": 9,
    "zehn": 10, "elf": 11, "zwölf": 12, "zwoelf": 12,
    "dreizehn": 13, "vierzehn": 14, "fünfzehn": 15, "fuenfzehn": 15,
    "sechzehn": 16, "siebzehn": 17, "achtzehn": 18, "neunzehn": 19,
}
_TENS = {
    "zwanzig": 20, "dreißig": 30, "dreissig": 30, "vierzig": 40,
    "fünfzig": 50, "fuenfzig": 50, "sechzig": 60, "siebzig": 70,
    "achtzig": 80, "neunzig": 90,
}
_SCALE_WORDS = {
    "million": 1_000_000, "millionen": 1_000_000,
    "mio": 1_000_000, "mio.": 1_000_000,
    "milliarde": 1_000_000_000, "milliarden": 1_000_000_000,
    "mrd": 1_000_000_000, "mrd.": 1_000_000_000,
    "tausend": 1_000, "tsd": 1_000, "tsd.": 1_000,
}
_MONEY_WORDS = {"euro", "euros", "eur", "€"}

# Einheiten-Suffixe, die mit einem Zahlwort verschmelzen:
#   Transkript „dreißigjähriger"  ⇄  Artikel „30-Jährige"
# Ohne diese Regel bleibt die gesprochene Form unerkannt, während die
# Ziffernform als Zahl gefunden wird — der Anker greift dann einseitig.
_UNIT_STEMS = {
    "jährig": "Jahre", "jahr": "Jahre", "jahre": "Jahre", "jahren": "Jahre",
    "tägig": "Tage", "stündig": "Stunden", "minütig": "Minuten",
    "monatig": "Monate", "wöchig": "Wochen",
    "monat": "Monate", "tag": "Tage", "stunde": "Stunden",
    "woche": "Wochen", "hektar": "Hektar",
    "köpfig": "Personen", "stellig": "Stellen",
    "stöckig": "Stockwerke", "spurig": "Spuren", "teilig": "Teile",
}
_PERCENT_STEMS = {"prozentig"}
_ADJ_ENDINGS = ("er", "es", "en", "em", "e", "")


def _split_unit_suffix(word: str) -> tuple[str, str] | None:
    """'dreißigjähriger' -> ('dreißig', 'Jahre'). Sonst None."""
    w = word.lower()
    for stems, label in ((_UNIT_STEMS, None), (_PERCENT_STEMS, "%")):
        for stem in stems:
            for end in _ADJ_ENDINGS:
                suf = stem + end
                if len(w) > len(suf) and w.endswith(suf):
                    return w[: -len(suf)], (label or _UNIT_STEMS[stem])
    return None


def _unit_of_token(word: str) -> str | None:
    """'Jährige' -> 'Jahre' — für die Ziffernform '30-Jährige'."""
    w = word.lower()
    for stem, unit in _UNIT_STEMS.items():
        for end in _ADJ_ENDINGS:
            if w == stem + end:
                return unit
    for stem in _PERCENT_STEMS:
        for end in _ADJ_ENDINGS:
            if w == stem + end:
                return "%"
    return None

# Unbestimmte Artikel: gleiche Form wie das Zahlwort "ein", aber fast nie
# als Zahl gemeint. "eins" fehlt bewusst — das ist immer ein Zahlwort.
_ARTICLE_FORMS = {"ein", "eine", "einen", "einem", "einer", "eines"}
_PERCENT_WORDS = {"prozent", "%"}


def _parse_simple(w: str) -> int | None:
    """0–99 als ein Wort: 'sieben', 'zwanzig', 'achtundzwanzig'."""
    if w in _UNITS:
        return _UNITS[w]
    if w in _TENS:
        return _TENS[w]
    m = re.fullmatch(r"([a-zäöüß]+)und([a-zäöüß]+)", w)
    if m and m.group(1) in _UNITS and _UNITS[m.group(1)] <= 9 and m.group(2) in _TENS:
        return _TENS[m.group(2)] + _UNITS[m.group(1)]
    return None


def _parse_hundreds(w: str) -> int | None:
    """0–9999 mit eingebettetem 'hundert': 'neunzehnhundertvierundachtzig'."""
    if "hundert" in w:
        left, rest = w.split("hundert", 1)
        left_v = _parse_simple(left) if left else 1
        if left_v is None:
            return None
        rest = rest[3:] if rest.startswith("und") else rest
        rest_v = _parse_simple(rest) if rest else 0
        if rest_v is None:
            return None
        return left_v * 100 + rest_v
    return _parse_simple(w)


def parse_number_word(word: str) -> int | None:
    """Ein zusammengeschriebenes deutsches Zahlwort -> int (oder None).

    Beispiele: 'achtundzwanzig' -> 28, 'zweitausendneunzehn' -> 2019,
    'zwanzigsiebenundzwanzig' -> 2027 (gesprochene Jahres-Lesart),
    'dreihundertfünfzig' -> 350.
    """
    w = word.lower().strip()
    if not w:
        return None
    if "tausend" in w:
        left, rest = w.split("tausend", 1)
        left_v = _parse_hundreds(left) if left else 1
        if left_v is None:
            return None
        rest = rest[3:] if rest.startswith("und") else rest
        rest_v = _parse_hundreds(rest) if rest else 0
        if rest_v is None:
            return None
        return left_v * 1000 + rest_v
    v = _parse_hundreds(w)
    if v is not None:
        return v
    # Jahres-Lesart "zwanzig|siebenundzwanzig" -> 20*100 + 27
    for i in range(4, len(w) - 3):
        a, b = _parse_simple(w[:i]), _parse_simple(w[i:])
        if a is not None and b is not None and 11 <= a <= 21:
            year = a * 100 + b
            if 1100 <= year <= 2199:
                return year
    return None


# ------------------------------------------------------------------ Entities

@dataclass
class Entity:
    type: str          # geld | prozent | zahl | datum
    surface: str
    norm: str          # menschenlesbare Normalform (JSON-Schema)
    value: float | str # Vergleichswert
    start: int
    end: int


_TOKEN_RE = re.compile(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?|[A-Za-zÄÖÜäöüß]+|%|€", re.UNICODE)



def _digit_value(tok: str) -> float:
    return float(tok.replace(".", "").replace(",", "."))


@dataclass
class _Tok:
    text: str
    low: str
    start: int
    end: int
    is_digit: bool = False
    num: int | float | None = None
    unit: str | None = None


def _tokenize(text: str) -> list[_Tok]:
    toks: list[_Tok] = []
    for m in _TOKEN_RE.finditer(text):
        raw = m.group(0)
        t = raw.rstrip()
        low = t.lower()
        tok = _Tok(t, low, m.start(), m.start() + len(t))
        if re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?", t):
            tok.is_digit = True
            tok.num = _digit_value(t)
        else:
            tok.num = parse_number_word(low.rstrip("."))
            if tok.num is None:
                teil = _split_unit_suffix(low.rstrip("."))
                if teil:
                    v = parse_number_word(teil[0])
                    if v is not None:
                        tok.num = v
                        tok.unit = teil[1]
        toks.append(tok)
    return toks


def _fmt_num(v: float) -> str:
    if float(v).is_integer():
        return str(int(v))
    return ("%g" % v).replace(".", ",") if False else ("%g" % v)


def extract_entities(text: str) -> list[Entity]:
    """Alle numerischen Entities mit exakten Zeichen-Offsets."""
    ents: list[Entity] = []
    toks = _tokenize(text)
    i, n = 0, len(toks)

    while i < n:
        t = toks[i]
        if t.num is None:
            i += 1
            continue
        # „CO2", „NO2", „H2O": die Ziffer klebt an Buchstaben und meint
        # keine Menge, sondern gehört zur Formel.
        if t.is_digit and t.start > 0 and text[t.start - 1].isalpha():
            i += 1
            continue

        start_tok = i
        value = float(t.num)
        j = i + 1

        # "Komma"-Dezimalstellen: fünf Komma drei (vier ...)
        if j < n and toks[j].low == "komma":
            digits = ""
            k = j + 1
            while k < n and toks[k].num is not None and 0 <= toks[k].num <= 9 \
                    and not toks[k].is_digit:
                digits += str(int(toks[k].num))
                k += 1
            if digits:
                value = float(f"{int(value)}.{digits}")
                j = k

        # Jahres-Lesart über zwei Tokens: "zwanzig" "siebenundzwanzig"
        year_pair = False
        if (not t.is_digit and j == i + 1 and 11 <= value <= 21
                and j < n and toks[j].num is not None and not toks[j].is_digit
                and 0 <= toks[j].num <= 99):
            cand = int(value) * 100 + int(toks[j].num)
            if 1100 <= cand <= 2199:
                value = float(cand)
                j += 1
                year_pair = True

        # Skalenwort: Millionen / Mrd. / tausend ...
        scale = 1
        if j < n and toks[j].low.rstrip(".") in _SCALE_WORDS:
            scale = _SCALE_WORDS[toks[j].low.rstrip(".")]
            j += 1
        value *= scale

        # Einheit
        etype, unit_end = None, None
        if j < n and toks[j].low.rstrip(".") in _MONEY_WORDS:
            etype, unit_end = "geld", j
            j += 1
        elif j < n and toks[j].low.rstrip(".") in _PERCENT_WORDS:
            etype, unit_end = "prozent", j
            j += 1

        # Verhältnis: NUM "zu" NUM  (nur ohne Skala/Einheit sinnvoll)
        if etype is None and scale == 1 and j < n and toks[j].low == "zu" \
                and j + 1 < n and toks[j + 1].num is not None:
            k = j + 1
            v2 = float(toks[k].num)
            end_tok = k
            surface = text[toks[start_tok].start:toks[end_tok].end]
            ents.append(Entity("zahl", surface, f"{int(value)}:{int(v2)}",
                               f"{int(value)}:{int(v2)}",
                               toks[start_tok].start, toks[end_tok].end))
            i = k + 1
            continue

        end_tok = unit_end if unit_end is not None else j - 1

        # Einheiten-Suffix: aus dem Kompositum („dreißigjähriger") oder aus
        # dem Folgetoken („30-Jährige", „30 Jahre"). Beide Schreibweisen
        # bekommen dieselbe Normform, damit der Anker beidseitig greift.
        unit = t.unit if etype is None else None
        if unit is None and etype is None and end_tok + 1 < n:
            u = _unit_of_token(toks[end_tok + 1].low)
            if u is not None:
                unit = u
                end_tok += 1
                j = max(j, end_tok + 1)
        if unit == "%" and etype is None:
            etype = "prozent"
            unit = None

        surface = text[toks[start_tok].start:toks[end_tok].end]

        # „ein/eine/einen …" ist im Deutschen weit überwiegend unbestimmter
        # Artikel, nicht Zahlwort. Nur als Zahl werten, wenn ein Skalenwort
        # oder eine Einheit folgt („eine Million Euro", „ein Prozent").
        if (t.low in _ARTICLE_FORMS and scale == 1 and etype is None
                and unit is None):
            i = start_tok + 1
            continue

        if etype == "geld":
            ents.append(Entity("geld", surface, f"{_fmt_num(value)} EUR",
                               value, toks[start_tok].start, toks[end_tok].end))
        elif etype == "prozent":
            ents.append(Entity("prozent", surface, f"{_fmt_num(value)} %",
                               value, toks[start_tok].start, toks[end_tok].end))
        elif unit is None and scale == 1 and 1900 <= value <= 2099 \
                and float(value).is_integer() \
                and (year_pair or not t.is_digit or len(t.text) == 4):
            ents.append(Entity("datum", surface, str(int(value)),
                               value, toks[start_tok].start, toks[end_tok].end))
        else:
            norm = _fmt_num(value) + (f" {unit}" if unit else "")
            ents.append(Entity("zahl", surface, norm,
                               value, toks[start_tok].start, toks[end_tok].end))
        i = j if j > i else i + 1

    ents.sort(key=lambda e: e.start)
    return ents


def normalize_numbers(text: str) -> str:
    """Ersetzt alle numerischen Entities durch ihre Normalform.

    Dient der lexikalischen Ähnlichkeit: 'fünf Komma drei Millionen Euro'
    und '5,3 Millionen Euro' werden beide zu '5300000 EUR'.
    """
    out, last = [], 0
    for e in extract_entities(text):
        out.append(text[last:e.start])
        out.append(str(e.norm))
        last = e.end
    out.append(text[last:])
    return "".join(out)
