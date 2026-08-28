"""
Stufe 2 — Embeddings: Aufruf und Skalierung der Ähnlichkeitsmatrix.

Der eigentliche Modellzugriff steckt in der übergebenen `embed_fn`
(saia.py, lokal oder Cloud) — hier liegt nur, was die Pipeline damit
macht: Artikelsätze als Dokumente, Claims als Suchanfragen einbetten
und die Kosinuswerte auf eine nutzbare Spanne bringen.
"""
from __future__ import annotations

from kern.lexik import _cos_dense
from kern.segmentierung import Sent


def _normalize_matrix(rows: list[list[float]]) -> list[list[float]]:
    """Lineare Spreizung der Embedding-Kosinuswerte über alle Paare.

    Bewusst **global** und nicht zeilenweise: Das absolute Niveau bleibt
    erhalten, damit ein Claim ohne gute Fundstelle auch nach der
    Normalisierung niedrig liegt — Voraussetzung für `keine_quelle`.

    Oberer Anker ist das Maximum, nicht P95. Mit P95 lagen bei realen
    Dokumenten sämtliche Zeilenmaxima oberhalb der Grenze und wurden auf
    1,0 geklemmt; das Embedding unterschied am oberen Ende dann gar nichts
    mehr, und die Rangfolge entschied sich allein über Lexik und Position.
    Die untere Grenze bleibt bei P10, weil E5-Modelle auch für völlig
    unverwandte Paare noch Werte um 0,7 liefern.
    """
    flat = sorted(v for row in rows for v in row)
    if not flat:
        return rows
    lo = flat[int(0.10 * (len(flat) - 1))]
    hi = flat[-1]
    span = (hi - lo) or 1e-9
    return [[min(1.0, max(0.0, (v - lo) / span)) for v in row] for row in rows]


def berechne(embed_fn, art_sents: list[Sent],
             claims_raw: list[Sent]) -> list[list[float]] | None:
    """Ähnlichkeitsmatrix Claims × Artikelsätze über die embed_fn.

    Artikelsätze laufen als Dokumente (`is_query=False`), Claims als
    Suchanfragen (`is_query=True`) — E5-Instruct unterscheidet beide
    Rollen im Prompt-Präfix. Liefert die embed_fn nichts Brauchbares,
    ist das Ergebnis None und die Fusion renormalisiert ohne Embeddings.
    """
    doc_vecs = embed_fn([s.text for s in art_sents], is_query=False)
    q_vecs = embed_fn([c.text for c in claims_raw], is_query=True)
    if not (doc_vecs and q_vecs):
        return None
    return _normalize_matrix(
        [[_cos_dense(q, d) for d in doc_vecs] for q in q_vecs])
