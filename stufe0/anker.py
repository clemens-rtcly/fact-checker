"""
Stufe 0 — Anker: harte Übereinstimmungen als Score-Bonus.

Zahlen, Geldbeträge, Jahre und Personennamen, die Claim und Artikelsatz
teilen, lokalisieren eine Fundstelle stärker als jedes weiche Signal.
Der Bonus wird nicht addiert, sondern in der Fusion in den verbleibenden
Spielraum skaliert (siehe kern/fusion.py) — hier entsteht nur die Matrix.

Zweiter Mechanismus: `komplementaere` ergänzt nach der Quellenwahl
eindeutige Zahlen-Anker, deren Satz noch fehlt, auch wenn sein
Wortbeitrag klein ist.

Die drei Entity-Hilfen (`_numeric`, `_anchorworthy`, `_values_equal`)
liegen hier, weil sie definieren, was überhaupt als Anker taugt — auch
die Quellspannen (stufe1/spannen.py) und die Verifikation
(stufe0/verifikation.py) lesen sie von hier.
"""
from __future__ import annotations

from konfig import CFG
from kern.segmentierung import Sent
from stufe0 import personen as ner
from stufe0.zahlen import Entity


def _numeric(ents: list[Entity]) -> list[Entity]:
    return [e for e in ents if e.type in ("geld", "prozent", "zahl", "datum")]


def _anchorworthy(e: Entity) -> bool:
    """Taugt die Entität als Anker bzw. als Teilspanne?

    Bloße kleine Zahlen („zwei Ministerpräsidenten", „drei Punkte") kommen
    in jedem Text vor, unterscheiden also nichts und erzeugen als
    Teilspanne nur vier Zeichen lange Schnipsel. Geldbeträge, Prozentwerte,
    Jahreszahlen und Verhältnisse bleiben vollwertige Anker.
    """
    if e.type != "zahl":
        return True
    if isinstance(e.value, str):        # Verhältnis wie 28:11
        return True
    return float(e.value) >= 10


def _values_equal(a: Entity, b: Entity) -> bool:
    if isinstance(a.value, str) or isinstance(b.value, str):
        return str(a.value) == str(b.value)
    # Währungsellipse: Im Deutschen wird die wiederholte Einheit
    # weggelassen — „20 Milliarden Euro … rund 62 Milliarden". Der zweite
    # Betrag erbt die Währung aus dem Kontext, wird aber als `zahl`
    # geparst. Ohne diese Ausnahme fand ein `geld`-Claim seinen
    # gleichwertigen `zahl`-Beleg nicht und meldete stattdessen einen
    # Konflikt gegen den nächstbesten anderen Geldbetrag im Artikel.
    if a.type != b.type and {a.type, b.type} not in (
            {"zahl", "datum"}, {"zahl", "geld"}, {"zahl", "prozent"}):
        return False
    return abs(float(a.value) - float(b.value)) < 1e-6


def matrix(claim_ents: list[list[Entity]], art_ents: list[list[Entity]],
           claim_persons: list[list[tuple[str, int, int]]],
           art_persons: list[list[tuple[str, int, int]]],
           art_sents: list[Sent],
           m: int, n: int) -> tuple[list[list[float]], list[list[str]]]:
    """Anker-Bonusmatrix (Claims × Sätze) plus Notizen je Claim.

    Numerische Anker: voller Bonus bei eindeutiger Fundstelle, kleiner
    bei 2–3, keiner darüber. Namensanker spiegeln die Staffel, bleiben
    aber darunter (Begründung an den CFG-Werten in konfig.py).
    """
    anchor = [[0.0] * n for _ in range(m)]
    anchor_notes: list[list[str]] = [[] for _ in range(m)]
    for ci, ents in enumerate(claim_ents):
        for e in _numeric(ents):
            if not _anchorworthy(e):
                continue
            hits = [si for si, ses in enumerate(art_ents)
                    if any(_values_equal(e, se) for se in _numeric(ses))]
            bonus = (CFG["anchor_unique"] if len(hits) == 1
                     else CFG["anchor_multi"] if 2 <= len(hits) <= 3 else 0.0)
            for si in hits:
                anchor[ci][si] += bonus
            if len(hits) == 1:
                anchor_notes[ci].append(
                    f"Anker {e.norm} eindeutig in {art_sents[hits[0]].id}")
        for surface, _s, _e in claim_persons[ci]:
            hits = [si for si, names in enumerate(art_persons)
                    if ner.matches(surface, [nm for nm, _a, _b in names])]
            bonus = (CFG["anchor_name_unique"] if len(hits) == 1
                     else CFG["anchor_name"] if len(hits) == 2 else 0.0)
            if not bonus:
                continue
            for si in hits:
                anchor[ci][si] += bonus
            if len(hits) == 1:
                anchor_notes[ci].append(
                    f"Name \u201e{surface}\u201c eindeutig in "
                    f"{art_sents[hits[0]].id}")
    anchor = [[min(v, CFG["anchor_cap"]) for v in row] for row in anchor]
    return anchor, anchor_notes


def komplementaere(claim_ents_ci: list[Entity],
                   art_ents: list[list[Entity]],
                   srcs: list[int]) -> list[int]:
    """Komplementäre Zahlen-Anker: eindeutige Anker außerhalb der
    bisherigen Fundstellen ergänzen, auch wenn ihr Wortbeitrag klein ist.

    Liefert die zu ergänzenden Satzindizes (sortiert, ohne Dubletten);
    das Anhängen an `srcs` und die Notiz übernimmt der Orchestrator.
    """
    covered_vals = {str(ae.value) for si in srcs
                    for ae in _numeric(art_ents[si])}
    anchor_extra: list[int] = []
    for e in _numeric(claim_ents_ci):
        if not _anchorworthy(e):
            continue
        hits = [si for si, ses in enumerate(art_ents)
                if any(_values_equal(e, se) for se in _numeric(ses))]
        if len(hits) == 1 and hits[0] not in srcs \
                and str(e.value) not in covered_vals:
            anchor_extra.append(hits[0])
    return anchor_extra
