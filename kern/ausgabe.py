"""
Zusammenbau des Ergebnis-JSON — der Ausgabevertrag mit dem Viewer.

Feldnamen, Reihenfolge und `meta`-Aufbau sind Schnittstelle: index.html
und eval.py lesen genau diese Struktur. Änderungen hier sind
Schema-Änderungen und gehören in REFERENZ.md dokumentiert.
"""
from __future__ import annotations

from kern.segmentierung import Sent


def assemble(article_text: str, transcript_text: str,
             art_sents: list[Sent], claims_json: list[dict],
             model_label: str) -> dict:
    title = art_sents[0].text if art_sents else "Eigene Analyse"
    return {
        "meta": {"titel": title, "quelle": "Eigenes Paar",
                 "modell": f"stufe0-2 · {model_label}"},
        "article": {
            "text": article_text,
            "sentences": [{"id": s.id, "start": s.start, "end": s.end,
                           "block": s.block, "level": s.level, "paragraph": s.paragraph,
                           "text": s.text} for s in art_sents],
        },
        "transcript": {"text": transcript_text, "claims": claims_json},
    }
