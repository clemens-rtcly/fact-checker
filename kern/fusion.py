"""
Fusion der Signale zu EINEM Score je (Claim, Artikelsatz).

Vier Bestandteile: Abdeckung (cov), Kosinus (lex), Position (pos) und —
falls Stufe 2 lief — Embedding (emb). Anker aus Stufe 0 werden nicht
addiert, sondern in den verbleibenden Spielraum skaliert.
"""
from __future__ import annotations

from konfig import CFG
from kern.segmentierung import Sent


def matrix(cov: list[list[float]], lex: list[list[float]],
           emb: list[list[float]] | None, anchor: list[list[float]],
           art_sents: list[Sent], m: int, n: int
           ) -> tuple[list[list[float]], list[bool]]:
    """Fusionierte Matrix (Claims × Sätze) plus Fragesatz-Merkliste."""
    if emb is not None:
        w_e, w_c = CFG["w_emb"], CFG["w_cov"]
        w_l, w_p = CFG["w_lex"], CFG["w_pos"]
    else:
        # Ohne Embeddings wird auf dieselbe Summe renormalisiert statt
        # gestaucht — sonst bedeuten t_direct und t_none im Offline- und
        # im Embedding-Modus verschiedene Dinge.
        tot = CFG["w_cov"] + CFG["w_lex"] + CFG["w_pos"]
        w_e = 0.0
        w_c = CFG["w_cov"] / tot
        w_l = CFG["w_lex"] / tot
        w_p = CFG["w_pos"] / tot

    # Teaserfragen im Vorspann sind lexikalische Magnete: Sie enthalten das
    # Themenvokabular des ganzen Textes („Hat das Großereignis Auswirkungen
    # auf das Gastgewerbe im Kreis?"), behaupten aber nichts. Jeder
    # zusammenfassende Claim dockt an ihnen an — gemessen an einem realen
    # Paar gewannen sie zwei Claims mit deutlichem Abstand vor den Sätzen,
    # die die Frage beantworten. Ein Fragesatz kann nie Beleg sein, weil er
    # keine Aussage trifft; deshalb ein harter Abschlag statt Ausschluss —
    # so bleibt er sichtbar, falls doch einmal nichts Besseres existiert.
    ist_frage = [s.text.rstrip().endswith("?") for s in art_sents]

    def fused_at(ci: int, si: int) -> float:
        pos = 1.0 - abs(si / max(n - 1, 1) - ci / max(m - 1, 1))
        base = w_c * cov[ci][si] + w_l * lex[ci][si] + w_p * pos
        if emb is not None:
            base += w_e * emb[ci][si]
        base = min(base, 1.0)
        if ist_frage[si]:
            base *= CFG["frage_faktor"]
        # Anker werden in den verbleibenden Spielraum skaliert statt addiert.
        # Additiv überschritten Basis + Anker regelmäßig 1,0 und wurden
        # abgeschnitten — dann lagen Platz 1 und Platz 2 gleichauf und die
        # Margin fiel fälschlich auf 0.
        return base + anchor[ci][si] * (1.0 - base)

    fused = [[fused_at(ci, si) for si in range(n)] for ci in range(m)]
    return fused, ist_frage
