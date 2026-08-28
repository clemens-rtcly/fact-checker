"""
Stufe 0.5 — Personenerkennung und -abgleich.

Ersetzt die frühere Heuristik „zwei großgeschriebene Wörter nebeneinander".
Die trug im Deutschen strukturell nicht, weil alle Substantive
großgeschrieben werden: „im Osten Regierungen ohne sie" sah aus wie ein
Name und wurde als unbelegt gemeldet.

Zwei Backends:

  spacy   de_core_news_sm, auf Nachrichtentext trainiert (bevorzugt)
          pip install spacy && python3 -m spacy download de_core_news_sm

  regex   Rückfall ohne Abhängigkeit. Erkennt großgeschriebene Wortfolgen,
          verwirft aber alles, dessen Bestandteile einzeln im Artikel
          vorkommen, und alles mit bekannten Nicht-Namen-Wörtern.
          Findet weniger als spaCy und meldet dafür kaum Fehlalarme.

Der Abgleich ist in beiden Fällen tokenbasiert, nicht zeichenkettenbasiert:
„Kraft" im Transkript gilt als belegt, wenn der Artikel „Sabine Kraft"
nennt (Teilnamen sind in Transkripten die Regel, nicht die Ausnahme).
"""
from __future__ import annotations

import re
import threading

# ---------------------------------------------------------------- Backend

_SPACY_MODEL = "de_core_news_sm"
_nlp = None
_nlp_state = "unversucht"          # unversucht | spacy | regex
_lock = threading.Lock()


def backend() -> str:
    """'spacy' oder 'regex' — welcher Pfad tatsächlich aktiv ist."""
    _ensure()
    return _nlp_state


def _ensure() -> None:
    global _nlp, _nlp_state
    if _nlp_state != "unversucht":
        return
    with _lock:
        if _nlp_state != "unversucht":
            return
        try:
            import spacy
            # Nur der NER-Pipe wird gebraucht; das spart deutlich Zeit.
            _nlp = spacy.load(_SPACY_MODEL,
                              disable=["lemmatizer", "attribute_ruler"])
            _nlp_state = "spacy"
        except Exception:
            _nlp = None
            _nlp_state = "regex"


# ------------------------------------------------------------- Regex-Fallback

_NAME_RE = re.compile(r"\b([A-ZÄÖÜ][a-zäöüß]{1,}(?:[- ][A-ZÄÖÜ][a-zäöüß]{1,})+)\b")

_TITLES = {
    "dr", "prof", "herr", "frau", "professor", "professorin",
    "oberbürgermeister", "oberbürgermeisterin", "bürgermeister",
    "bürgermeisterin", "kämmerer", "kämmerin", "minister", "ministerin",
    "senator", "senatorin", "landrat", "landrätin", "fraktionschef",
    "fraktionschefin", "sprecher", "sprecherin", "geschäftsführer",
    "geschäftsführerin", "vorstand", "vorsitzender", "vorsitzende",
    "trainer", "trainerin", "kanzler", "kanzlerin", "präsident",
    "präsidentin", "intendant", "intendantin",
}

# Wörter, die im Deutschen einen Satz eröffnen und nie einen Namen
_STOP_FIRST = {
    "der", "die", "das", "den", "dem", "des", "ein", "eine", "einen",
    "einem", "einer", "eines", "im", "am", "beim", "zum", "zur", "und",
    "mit", "nach", "vor", "für", "von", "bei", "aus", "trotz", "neben",
    "während", "wegen", "über", "unter", "ohne", "gegen", "seit", "bis",
    "durch", "auch", "aber", "diese", "dieser", "dieses", "alle", "seine",
    "ihre", "sein", "ihr", "neue", "neuer", "neues", "als", "wie", "dass",
}

# Wortstämme, die nie Teil eines Personennamens sind
_NOT_NAME = {
    "million", "millionen", "milliarde", "milliarden", "tausend", "euro",
    "prozent", "komma", "uhr", "stimmen", "jahr", "jahre", "jahren",
    "osten", "westen", "norden", "süden", "stadt", "gemeinde", "land",
    "bund", "regierung", "regierungen", "partei", "parteien", "rat",
    "haushalt", "januar", "februar", "märz", "april", "mai", "juni",
    "juli", "august", "september", "oktober", "november", "dezember",
    "montag", "dienstag", "mittwoch", "donnerstag", "freitag", "samstag",
    "sonntag", "morgen", "abend", "gefahr", "vergleich", "höhe", "sanierung",
}


def _strip_titles(tokens: list[str]) -> list[str]:
    out = [t for t in tokens if t.lower().rstrip(".") not in _TITLES]
    return out or tokens


# ------------------------------------------------------------------- API

def persons(text: str) -> list[tuple[str, int, int]]:
    """Personennamen als (surface, start, end) mit Zeichen-Offsets."""
    _ensure()
    if _nlp_state == "spacy":
        doc = _nlp(text)
        out = []
        for ent in doc.ents:
            if ent.label_ != "PER":
                continue
            surface = ent.text.strip()
            if not surface:
                continue
            start = ent.start_char + (len(ent.text) - len(ent.text.lstrip()))
            out.append((surface, start, start + len(surface)))
        return out

    # Rückfall: konservativ, lieber weniger als falsch
    out = []
    for m in _NAME_RE.finditer(text):
        tokens = re.split(r"[- ]", m.group(1))
        if tokens[0].lower() in _STOP_FIRST:
            # „Die Bauarbeiten", „Der Gemeinderat" — Artikel plus Substantiv,
            # im Deutschen nicht von einem Namen zu unterscheiden.
            tokens = tokens[1:]
            if len(tokens) < 2:
                continue
        if any(t.lower() in _NOT_NAME for t in tokens):
            continue
        start = m.start(1) + (len(m.group(1)) - len(" ".join(tokens))
                              if len(tokens) < len(re.split(r"[- ]", m.group(1)))
                              else 0)
        surface = text[start:m.end(1)]
        out.append((surface, start, m.end(1)))
    return out


def entities(text: str,
             labels: tuple[str, ...] = ("PER", "ORG")
             ) -> list[tuple[str, int, int, str]]:
    """Benannte Entitäten als (surface, start, end, label).

    Wie `persons()`, aber nicht auf Personen beschränkt. Für die
    Sprecherzuordnung in Zitatblöcken werden auch Organisationen
    gebraucht: „so eine Sprecherin" verweist auf das City-Hotel
    Geilenkirchen, nicht auf eine Person.

    Im Regex-Rückfall lassen sich Personen und Organisationen nicht
    trennen; alle Treffer tragen dann das Label '?'. Für die
    Sprecherzuordnung genügt das — dort zählt nur, ob überhaupt ein
    Eigenname vorliegt.
    """
    _ensure()
    if _nlp_state == "spacy":
        out = []
        for ent in _nlp(text).ents:
            if ent.label_ not in labels:
                continue
            surface = ent.text.strip()
            if not surface:
                continue
            start = ent.start_char + (len(ent.text) - len(ent.text.lstrip()))
            out.append((surface, start, start + len(surface), ent.label_))
        return out
    return [(s, a, b, "?") for s, a, b in persons(text)]


def name_tokens(surface: str) -> set[str]:
    """Vergleichbare Namensbestandteile: kleingeschrieben, ohne Titel."""
    toks = _strip_titles(re.split(r"[-\s]+", surface.strip()))
    return {t.lower().strip(".,;:„“\"'") for t in toks if len(t) > 1}


def matches(claim_name: str, article_names: list[str],
            article_text: str | None = None) -> bool:
    """Gilt der Name im Claim durch den Artikel als belegt?

    Erstens über Tokenmengen: „Kraft" gilt durch „Sabine Kraft" als belegt
    und umgekehrt — Teilnamen sind in Transkripten die Regel.

    Zweitens, falls das scheitert, über den Rohtext. Das fängt den
    Regex-Rückfall ab, der Einzelnamen („Merz") nicht als Entität erkennt:
    Kommen alle Namensbestandteile als eigenständige Wörter im Artikel
    vor, ist der Name belegt. Ein tatsächlich abweichender Name („Ehrler"
    statt „Ehrle") fällt weiterhin durch.
    """
    a = name_tokens(claim_name)
    if not a:
        return True
    for other in article_names:
        b = name_tokens(other)
        if not b:
            continue
        if a <= b or b <= a:
            return True
    if article_text:
        low = article_text.lower()
        if all(re.search(r"\b" + re.escape(tok) + r"\b", low) for tok in a):
            return True
    return False
