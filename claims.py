"""
Stufe 1.2 — Zerlegung von Transkriptsätzen in Teilaussagen (Sub-Claims).

Ein gesprochener Satz enthält oft zwei Behauptungen, die aus verschiedenen
Artikelstellen stammen:

    „Die AfD sei die größere Gefahr, deshalb müsse es Regierungen ohne sie
     geben."          ^-- aus s2                ^-- aus s3

Als ein Claim behandelt bekommt der Satz eine gemischte Zuordnung. Getrennt
bekommt jede Hälfte ihre eigene Fundstelle, ihre eigene Confidence und ihr
eigenes Urteil — für die redaktionelle Prüfung deutlich brauchbarer.

Die Zerlegung ist bewusst konservativ. Sie schneidet nur an Konnektoren,
die im Deutschen zuverlässig eine neue Aussage einleiten, und niemals:

  * innerhalb von Anführungszeichen oder Klammern
  * an Relativsätzen (", der …", ", die …") — die modifizieren nur
  * an „dass"-Sätzen — sonst bleibt „X sagte," als Fragment übrig
  * wenn ein Teil zu kurz wäre

Ob eine Zerlegung tatsächlich verwendet wird, entscheidet die Pipeline
nachträglich anhand der Frage, ob jeder Teil im Artikel überhaupt etwas
findet (siehe pipeline._choose_claims).
"""
from __future__ import annotations

import re

# Konnektoren, die nach Komma eine eigenständige Aussage einleiten.
#
# Bewusst NICHT enthalten: "dass" (sonst bleibt „X sagte," übrig),
# Relativpronomen (die modifizieren nur) und die Nebensatz-Einleiter
# "sodass", "damit", "wenn", "falls", "nachdem", "bevor", "sobald",
# "solange", "insofern". Letztere leiten Folge, Zweck, Bedingung oder
# Zeit ein — das gehört zur selben Aussage. „Er wird verkleidet, sodass
# das Problem behoben ist" ist EIN Sachverhalt, kein zwei.
_CONNECTIVES = {
    # Folge / Begründung
    "deshalb", "deswegen", "daher", "darum", "somit", "folglich",
    "infolgedessen", "weshalb",
    # Nebenordnung
    "außerdem", "zudem", "ferner", "ebenso", "gleichzeitig", "zugleich",
    # Gegensatz
    "aber", "doch", "jedoch", "allerdings", "dennoch", "trotzdem",
    "stattdessen", "hingegen", "wohingegen", "sondern",
    # Unterordnung mit eigenem Sachverhalt
    "während", "weil", "da", "obwohl", "obgleich", "wenngleich",
}

# Nach diesen Wörtern folgt kein eigener Satz ("und zwar", "und das")
_AFTER_UND_BLOCK = {"zwar", "das", "dies", "damit", "dabei", "dann", "so"}

MIN_PART_LEN = 25      # Zeichen; kürzere Teile bleiben am Nachbarn
MIN_PART_LEN_DASH = 35 # nach Gedankenstrich strenger — dort hängen oft
                       # bloße Zusätze statt eigener Aussagen
MAX_PARTS = 3

# Konnektoren, die eine Verneinung aus dem Vorderteil weiterführen.
# „nicht, weil X, sondern weil Y" ist EINE Aussage: Wer bei „weil"
# schneidet, macht aus dem verneinten X eine behauptete Aussage und
# kehrt damit den Sinn um.
_NEG_SENSITIVE = {"weil", "sondern", "denn", "da", "sondern"}

_NEGATION = {
    "nicht", "nichts", "kein", "keine", "keinen", "keinem", "keiner",
    "keines", "nie", "niemals", "keineswegs", "nirgends", "weder",
}

# Präpositionen: Was danach folgt, ist eine Ergänzung, keine Aussage
_PREPOSITIONS = {
    "unter", "über", "mit", "ohne", "für", "von", "bei", "nach", "vor",
    "aus", "seit", "trotz", "wegen", "in", "an", "auf", "zu", "im", "am",
    "beim", "zum", "zur", "gegen", "um", "durch", "neben", "zwischen",
    "statt", "samt", "laut", "gemäß", "entlang", "innerhalb",
}

# Rückverweise, die den Bezug im Nachbarteil haben. Ein Teil mit solchem
# Marker ist ohne seinen Vorgänger nicht sinnvoll prüfbar — er darf nicht
# allein als "keine Quelle" gelten.
_ANAPHORA = {
    "sie", "ihn", "ihm", "ihr", "ihnen", "ihre", "ihrer", "ihres", "ihrem",
    "er", "es", "dies", "diese", "dieser", "dieses", "diesem", "diesen",
    "dabei", "dadurch", "damit", "dafür", "davon", "daran", "darauf",
    "deren", "dessen", "derselbe", "dieselbe", "letzterer", "letztere",
}


def has_anaphor(text: str) -> bool:
    """Enthält der Teil einen Rückverweis auf den Nachbarteil?"""
    words = re.findall(r"[A-Za-zÄÖÜäöüß]+", text.lower())
    return any(w in _ANAPHORA for w in words)


def _has_open_negation(text: str) -> bool:
    """Steht im Vorderteil eine Verneinung, die der Konnektor auflöst?"""
    words = re.findall(r"[A-Za-zÄÖÜäöüß]+", text.lower())
    return any(w in _NEGATION for w in words)


def _depth_ok(text: str, pos: int) -> bool:
    """Liegt `pos` außerhalb von Anführungszeichen und Klammern?"""
    head = text[:pos]
    if (head.count("\u201e") - head.count("\u201c")) != 0:   # „ … “
        return False
    if (head.count("\u00bb") - head.count("\u00ab")) != 0:   # » … «
        return False
    if head.count('"') % 2 != 0:
        return False
    if head.count("(") != head.count(")"):
        return False
    return True


def _cut_points(text: str) -> list[tuple[int, str]]:
    """(Position, Art) der Stellen, an denen ein neuer Teil beginnt."""
    cuts: list[tuple[int, str]] = []

    # Komma + Konnektor
    for m in re.finditer(r",\s+([A-Za-zÄÖÜäöüß]+)", text):
        word = m.group(1).lower()
        start = m.start(1)
        if not _depth_ok(text, start):
            continue
        if word == "und":
            nxt = re.match(r"\s*([A-Za-zÄÖÜäöüß]+)", text[m.end(1):])
            if nxt and nxt.group(1).lower() in _AFTER_UND_BLOCK:
                continue
            cuts.append((start, "komma"))
            continue
        if word not in _CONNECTIVES:
            continue
        # Negationsklammer nicht aufbrechen
        if word in _NEG_SENSITIVE and _has_open_negation(text[:start]):
            continue
        cuts.append((start, "komma"))

    # Semikolon
    for m in re.finditer(r";\s+", text):
        if _depth_ok(text, m.end()):
            cuts.append((m.end(), "komma"))

    # Gedankenstrich zwischen zwei Aussagen
    for m in re.finditer(r"\s+[–—]\s+", text):
        if not _depth_ok(text, m.end()):
            continue
        nxt = re.match(r"([A-Za-zÄÖÜäöüß]+)", text[m.end():])
        if nxt and nxt.group(1).lower() in _PREPOSITIONS:
            continue          # danach folgt eine Ergänzung, keine Aussage
        cuts.append((m.end(), "strich"))

    seen: dict[int, str] = {}
    for pos, kind in cuts:
        seen.setdefault(pos, kind)
    return sorted(seen.items())


def split_sentence(text: str, base: int = 0) -> list[tuple[str, int, int]]:
    """Zerlegt einen Satz in Teilaussagen.

    Liefert [(teiltext, start, end), …] mit absoluten Offsets (base wird
    aufaddiert). Gibt genau ein Element zurück, wenn nicht sinnvoll
    zerlegbar — die Aufrufseite muss also keinen Sonderfall behandeln.
    """
    whole = [(text, base, base + len(text))]
    cuts = _cut_points(text)
    if not cuts:
        return whole

    positions = [c[0] for c in cuts]
    kinds = {c[0]: c[1] for c in cuts}
    bounds = [0] + positions + [len(text)]
    parts: list[tuple[str, int, int, str]] = []
    for a, b in zip(bounds, bounds[1:]):
        s, e = a, b
        while s < e and text[s] in " \t":
            s += 1
        while e > s and text[e - 1] in " \t,;\u2013\u2014":
            e -= 1
        if e <= s:
            continue
        parts.append((text[s:e], base + s, base + e, kinds.get(a, "start")))

    # Zu kurze Teile an den Nachbarn hängen. Nach einem Gedankenstrich gilt
    # eine höhere Mindestlänge, weil dort typischerweise Zusätze stehen.
    changed = True
    while changed and len(parts) > 1:
        changed = False
        for i, (t, s, e, kind) in enumerate(parts):
            need = MIN_PART_LEN_DASH if kind == "strich" else MIN_PART_LEN
            if len(t) >= need:
                continue
            j = i - 1 if i > 0 else i + 1
            lo, hi = min(i, j), max(i, j)
            ns, ne = parts[lo][1], parts[hi][2]
            merged = text[ns - base:ne - base]
            parts[lo:hi + 1] = [(merged, ns, ne, parts[lo][3])]
            changed = True
            break

    if len(parts) < 2 or len(parts) > MAX_PARTS:
        return whole
    return [(t, s, e) for t, s, e, _k in parts]
