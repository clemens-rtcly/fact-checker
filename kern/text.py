"""
Markup-Normalisierung der Eingabetexte.

Läuft vor der Segmentierung über Artikel UND Transkript. Der einzige
Export ist `strip_html`; alles Weitere sind seine Regex-Bausteine.
"""
from __future__ import annotations

import re
from html import unescape

_BLOCK_TAGS = re.compile(
    r"</?(?:p|div|h[1-6]|br|li|ul|ol|tr|section|article|blockquote)\b[^>]*>",
    re.I)
_ANY_TAG = re.compile(r"<[^>]+>")
_HAS_TAG = re.compile(r"<\s*/?\s*[a-zA-Z][^>]*>")

_MD_HEADING = re.compile(r"^[ \t]{0,3}#{1,6}[ \t]+")
_H_TAG_AUF = re.compile(r"<h([1-6])\b[^>]*>", re.I)
_H_TAG_ZU = re.compile(r"</h[1-6]\s*>", re.I)


def strip_html(text: str) -> str:
    """Normalisiert Auszeichnung auf Markdown und stellt Absatzgrenzen her.

    Aus Redaktionssystemen kopierte Artikel bringen `<p class="">`,
    `</p>` und `<h3>` mit, aus Markdown-Exporten kommen `###`-Zeilen.
    Unbehandelt landet das Markup mitten in den Sätzen.

    Früher wurde beides ersatzlos gelöscht — mit dem ausdrücklichen Ziel,
    die Absatzlogik „Überschrift = §0, Vorspann = §1" wieder greifen zu
    lassen. Diese Positionsannahme gibt es nicht mehr. Stattdessen wird
    HTML auf die Markdown-Schreibweise gebracht (`<h2>` wird `##`), damit
    `segment` echte Überschriften erkennen kann statt sie zu erraten.
    Zwischenüberschriften bleiben als Text erhalten — sie tragen Inhalt
    (etwa „19 Gelege von Bodenbrütern") und dürfen Fundstelle sein.
    """
    t = text
    if _HAS_TAG.search(t):
        t = _H_TAG_AUF.sub(lambda m: "\n\n" + "#" * int(m.group(1)) + " ", t)
        t = _H_TAG_ZU.sub("\n\n", t)
        t = _BLOCK_TAGS.sub("\n\n", t)
        t = _ANY_TAG.sub("", t)
        t = unescape(t)
    t = t.replace("\u00a0", " ")
    t = "\n".join(line.rstrip() for line in t.split("\n"))
    t = "\n".join(line.lstrip() if not _MD_HEADING.match(line) else line
                  for line in t.split("\n"))
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()
