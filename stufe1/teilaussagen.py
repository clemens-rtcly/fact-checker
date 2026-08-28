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

Zwei Hälften dieses Moduls:

  Zerlegung   `split_sentence`, `has_anaphor` — rein regelbasiert,
              arbeitet auf einem einzelnen Satz (früher claims.py).
  Auswahl     `waehle_claims` — entscheidet nachträglich anhand einer
              lexikalischen Probe, ob eine Zerlegung tatsächlich
              verwendet wird (früher pipeline._choose_claims).
"""
from __future__ import annotations

import re

from konfig import CFG
from kern.lexik import (_covered_weight, _cos_sparse, _ngrams, _prep,
                        erzeuge_tfidf)
from kern.segmentierung import Sent, segment

# ------------------------------------------------------------------ Zerlegung

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
    if (head.count("\u201e") - head.count("\u201c")) != 0:   # „ … "
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


# -------------------------------------------------------------------- Auswahl

def waehle_claims(transcript_text: str, art_sents: list[Sent],
                  aktiv: bool = True) -> list[Sent]:
    """Claims bilden — ganze Sätze oder Teilaussagen (Stufe 1.2).

    Eine Zerlegung wird zurückgenommen, wenn ein Teil im Artikel nichts
    findet **und** einen Rückverweis auf den Nachbarteil enthält („ohne
    sie", „dabei"). Solche Fragmente sind allein nicht prüfbar und würden
    fälschlich als unbelegt erscheinen.

    Ein Teil ohne Rückverweis, der im Artikel nichts findet, bleibt
    dagegen bewusst getrennt: Das ist der Fall einer erfundenen zweiten
    Satzhälfte, und der soll als `keine_quelle` sichtbar werden statt in
    der Zuordnung des ersten Teils zu verschwinden.

    Die Prüfung läuft rein lexikalisch und kostet daher keine Embeddings —
    eingebettet wird erst der endgültige Claim-Satz.

    `aktiv=False` (Schalter STUFEN["1.2_teilaussagen"]) liefert die
    ungeteilten Transkriptsätze zurück.
    """
    sentences = segment(transcript_text, "transcript", "c")
    if not aktiv or not art_sents:
        return sentences

    cand = {s.id: split_sentence(s.text, s.start) for s in sentences}
    if all(len(v) < 2 for v in cand.values()):
        return sentences

    tmp = erzeuge_tfidf([s.text for s in art_sents]
                        + [s.text for s in sentences]
                        + [p[0] for v in cand.values() for p in v])
    art_vecs = [tmp.vec(s.text) for s in art_sents]
    art_gr = [set(_ngrams(_prep(s.text)).keys()) for s in art_sents]

    final: list[Sent] = []
    for s in sentences:
        parts = cand[s.id]
        if len(parts) > 1:
            orphan = any(
                max(_cos_sparse(tmp.vec(t), av) for av in art_vecs)
                < CFG["split_min_lex"] and has_anaphor(t)
                for t, _a, _b in parts)
            # Eine Zerlegung lohnt nur, wenn die Teile auf verschiedene
            # Artikelsätze zeigen. Landen alle beim selben Satz, war die
            # Trennung folgenlos und erzeugt nur zusätzliche Zeilen.
            besten = []
            for t, _a, _b in parts:
                cv = tmp.vec(t)
                besten.append(max(range(len(art_sents)),
                                  key=lambda i: _covered_weight(cv, art_gr[i])))
            if orphan or len(set(besten)) < 2:
                parts = [(s.text, s.start, s.end)]
        for t, a, b in parts:
            final.append(Sent("", a, b, t, s.paragraph, s.block,
                              level=s.level, part=len(parts) > 1))

    for i, s in enumerate(final, 1):
        s.id = f"c{i}"
    return final
