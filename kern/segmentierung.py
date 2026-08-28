"""
Segmentierung: Absätze und Sätze mit exakten Zeichen-Offsets.

Stufenübergreifend — Artikel und Transkript laufen durch denselben Code,
und alle nachgelagerten Stufen rechnen auf den `Sent`-Objekten von hier.
Die Offsets sind der Vertrag mit dem Viewer: `start`/`end` zeigen immer
in den Originaltext.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_ABBREV = {
    "z.b", "bzw", "ca", "dr", "prof", "mio", "mrd", "nr", "u.a", "d.h",
    "o.ä", "o.a", "vgl", "ggf", "inkl", "evtl", "usw", "str", "abs", "art",
    "etc", "sog", "u.u", "v.a", "bspw", "geb", "st", "hr", "fr", "min",
    "max", "tel", "co", "jh", "jhd", "s", "vgl",
}

_SENT_END = re.compile(r"[.!?…]+[»«\"'\u201c\u201d\u201e)\]]*")


def _ist_jahr(w: str) -> bool:
    """Vierstellige Jahreszahl (1000-2999).

    Einzige Ausnahme von der Ordnungszahl-Regel: "Das Werk schloss
    1998. Danach ..." endet wirklich einen Satz, waehrend "50.
    Geburtstag" oder "100. Tag" Ordnungszahlen mitten im Satz sind.
    """
    return len(w) == 4 and 1000 <= int(w) <= 2999


@dataclass
class Sent:
    id: str
    start: int
    end: int
    text: str
    paragraph: int
    block: str           # 'heading' | 'body'
    level: int = 0       # Überschriftenebene 1-6, sonst 0
    part: bool = False   # True = Teilaussage aus Stufe 1.2 (kein ganzer Satz)


def _split_sentences_in(text: str, p_start: int, p_end: int) -> list[tuple[int, int]]:
    """Satzgrenzen innerhalb eines Absatzes, als absolute Offsets."""
    out = []
    seg_start = p_start
    for m in _SENT_END.finditer(text, p_start, p_end):
        end = m.end()
        # Punkt mit Zeichen unmittelbar davor UND dahinter (x.x): Tausender-
        # punkt, Dezimalpunkt, Domain, Versionsnummer. Nie eine Satzgrenze,
        # denn nach einem echten Satzende steht Leerraum.
        if (m.group(0) == "." and end < p_end and not text[end].isspace()
                and m.start() > p_start and not text[m.start() - 1].isspace()):
            continue
        # Folgekontext prüfen: nach Satzende kommt Leerraum + Großbuchstabe/Ziffer/Anführung
        rest = text[end:p_end]
        nxt = rest.lstrip()
        if nxt and not re.match(r"[A-ZÄÖÜ0-9\u201e\u201c\"'«»(]", nxt):
            continue
        # Wort vor dem Punkt: Abkürzung oder Ordnungszahl -> keine Grenze
        before = text[seg_start:m.start()]
        wm = re.search(r"([A-Za-zÄÖÜäöüß.]+|\d+)$", before)
        if wm:
            w = wm.group(1).lower().rstrip(".")
            if w in _ABBREV:
                continue
            if w.isdigit() and "." in m.group(0) and not _ist_jahr(w):
                continue  # "3. Platz", "50. Geburtstag", "100. Tag"
        out.append((seg_start, end))
        seg_start = end
        while seg_start < p_end and text[seg_start].isspace():
            seg_start += 1
    if seg_start < p_end and text[seg_start:p_end].strip():
        out.append((seg_start, p_end))
    # Whitespace an den Rändern abschneiden
    trimmed = []
    for s, e in out:
        while s < e and text[s].isspace():
            s += 1
        while e > s and text[e - 1].isspace():
            e -= 1
        if e > s:
            trimmed.append((s, e))
    return trimmed


_MD_HEAD = re.compile(r"^(\s{0,3}#{1,6}\s+)(?=\S)")
_MD_SETEXT = re.compile(r"^\s{0,3}(=+|-{2,})\s*$")
_HTML_HEAD = re.compile(r"^(\s*<h([1-6])\b[^>]*>)", re.I)
_HTML_HEAD_ZU = re.compile(r"(</h[1-6]\s*>\s*)$", re.I)


def _ueberschrift(text: str, p_start: int, p_end: int):
    """(Ebene, Inhaltsbeginn, Inhaltsende) für einen Absatz, oder None.

    Erkannt wird, was tatsächlich als Überschrift ausgezeichnet ist:
    Markdown (`# …` bis `###### …`, Setext mit `===` bzw. `---` in der
    Folgezeile) und HTML (`<h1>` bis `<h6>`). Die Auszeichnungszeichen
    selbst fallen aus dem Inhaltsbereich heraus, damit sie im Viewer
    nicht als Text erscheinen — die Zeichen-Offsets bleiben exakt, es
    wird nur enger geschnitten.

    Bewusst NICHT erkannt wird die Position. Früher galt der erste Absatz
    pauschal als Überschrift und der zweite als Vorspann. Das ist eine
    Annahme über die Textgestalt, keine Beobachtung: Bei einem Transkript
    ohne Überschrift, einem Artikel, der direkt mit dem Vorspann beginnt,
    oder einem Text mit mehreren Zwischentiteln lag sie falsch — und sie
    wirkte sich bis in die Schriftgröße im Viewer und in den Aufbau der
    NLI-Prämisse aus.
    """
    roh = text[p_start:p_end]
    zeilen = roh.split("\n")

    m = _MD_HEAD.match(roh)
    if m:
        return roh[:m.end()].count("#"), p_start + len(m.group(1)), p_end

    # Setext: Titelzeile, darunter === oder ---
    if len(zeilen) >= 2 and _MD_SETEXT.match(zeilen[1]) and zeilen[0].strip():
        stufe = 1 if zeilen[1].strip().startswith("=") else 2
        return stufe, p_start, p_start + len(zeilen[0])
    return None


def segment(text: str, kind: str, id_prefix: str) -> list[Sent]:
    """Absätze + Sätze mit exakten Zeichen-Offsets. kind: 'article'|'transcript'.

    `block` ist 'heading' oder 'body'; bei Überschriften steht die Ebene
    in `level`. Die frühere Dreiteilung headline/lead/body kam aus der
    Absatzposition und wurde durch echte Auszeichnung ersetzt.
    """
    sents: list[Sent] = []
    para_idx = 0
    counter = 1
    for pm in re.finditer(r"[^\n]+(?:\n(?!\n)[^\n]*)*", text):
        p_start, p_end = pm.start(), pm.end()
        kopf = _ueberschrift(text, p_start, p_end)
        stufe, a, b = kopf if kopf else (0, p_start, p_end)
        for s, e in _split_sentences_in(text, a, b):
            sents.append(Sent(f"{id_prefix}{counter}", s, e, text[s:e],
                              para_idx, "heading" if stufe else "body",
                              level=stufe))
            counter += 1
        para_idx += 1
    return sents
