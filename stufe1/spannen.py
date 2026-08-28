"""
Evidenz-Spannen: Welche Regionen eines Fundstellen-Satzes stützen den
Claim tatsächlich?

Gehört zur lexikalischen Stufe, weil der Vergleich über dieselben
Zeichen-3-Gramme läuft wie die Abdeckung — nur eben tokenweise statt
satzweise. Das Ergebnis sind die Markierungen, die der Viewer im
Artikeltext hervorhebt (`sources[].spans`).
"""
from __future__ import annotations

import re

from kern.lexik import _FUNC_WORDS, _ngrams, _prep
from kern.segmentierung import Sent
from stufe0.anker import _anchorworthy, _numeric, _values_equal
from stufe0.zahlen import Entity

_SPAN_FUZZ = 0.6      # Anteil gemeinsamer Zeichen-3-Gramme je Token
_SPAN_GAP = 4         # max. Abstand in Tokens innerhalb einer Region


def _evidence_spans(claim_grams: set[str], sent_text: str,
                    anchor_spans: list[tuple[int, int]]
                    ) -> list[tuple[int, int]]:
    """Regionen des Satzes, die den Claim tatsächlich stützen.

    Ersetzt die frühere Regel „Ankerregion, sonst ganzer Satz". Die war in
    beide Richtungen falsch: Eine Zahl im Satz schrumpfte die Anzeige auf
    die Ziffern zusammen, ein Satz ohne Zahl wurde vollständig markiert.

    Der Vergleich läuft über Zeichen-3-Gramme statt über Wortgleichheit,
    weil Transkripte Eigennamen phonetisch verformen („Pfass" für PFAS).
    Die Reihenfolge bleibt unberücksichtigt, denn Zusammenfassungen
    stellen um.

    Drei Token-Zustände, die streng auseinandergehalten werden:

      treffer        im Claim belegt
      abgelehnt      geprüft und nicht gefunden
      übersprungen   gar nicht geprüft (Funktionswort, sehr kurz)

    Zwei Trefferregionen werden **nur** über übersprungene Tokens
    verbunden. Ein einziges abgelehntes Wort dazwischen trennt sie — sonst
    verschmolz „Laut Feuerwehr konnte es zu einer Geruchsbelästigung" zu
    einer Region, obwohl „konnte" im Transkript gar nicht vorkommt.

    An den Rändern wächst eine Region über übersprungene Tokens hinaus,
    aber nur, wenn bis zur Satzgrenze nichts Abgelehntes mehr folgt. So
    bleibt „… nicht verfügbar waren." vollständig, während „… die
    Geschäfte, der erst zwei Jahre zuvor …" nach „Geschäfte" endet und das
    Relativpronomen nicht mehr einschließt.

    Offsets relativ zum Satzanfang, aufsteigend und überschneidungsfrei.
    """
    toks = [(m.group(0), m.start(), m.end())
            for m in re.finditer(r"[\wäöüß]+", sent_text)]
    zustand: list[str] = []
    for w, _a, _b in toks:
        wl = w.lower()
        if wl in _FUNC_WORDS or (len(wl) < 4 and not wl.isdigit()):
            zustand.append("uebersprungen")
            continue
        wg = set(_ngrams(_prep(w)))
        if not wg:
            zustand.append("uebersprungen")
            continue
        zustand.append("treffer"
                       if len(wg & claim_grams) / len(wg) >= _SPAN_FUZZ
                       else "abgelehnt")

    idx = [k for k, z in enumerate(zustand) if z == "treffer"]
    if not idx:
        return [(0, len(sent_text))]

    gruppen: list[list[int]] = [[idx[0]]]
    for k in idx[1:]:
        blockiert = any(zustand[j] == "abgelehnt"
                        for j in range(gruppen[-1][-1] + 1, k))
        if blockiert:
            gruppen.append([k])
        else:
            gruppen[-1].append(k)

    regionen: list[tuple[int, int]] = []
    for g in gruppen:
        lo_k, hi_k = g[0], g[-1]
        if all(zustand[j] == "uebersprungen" for j in range(hi_k + 1, len(zustand))):
            hi_k = len(zustand) - 1
        if all(zustand[j] == "uebersprungen" for j in range(0, lo_k)):
            lo_k = 0
        lo, hi = toks[lo_k][1], toks[hi_k][2]
        if not sent_text[hi:].strip(" .,;:!?\u201c\u201e\u201d\"')»"):
            hi = len(sent_text)
        if not sent_text[:lo].strip(" \u201e\u201c\"('«"):
            lo = 0
        regionen.append((lo, hi))

    for a, b in anchor_spans:
        if not any(lo <= a and b <= hi for lo, hi in regionen):
            regionen.append((a, b))

    regionen.sort()
    verschmolzen: list[tuple[int, int]] = []
    for lo, hi in regionen:
        if verschmolzen and lo <= verschmolzen[-1][1]:
            verschmolzen[-1] = (verschmolzen[-1][0], max(verschmolzen[-1][1], hi))
        else:
            verschmolzen.append((lo, hi))
    return verschmolzen


def quellen_json(srcs: list[int], redundant: list[int],
                 claim_grams_ci: set[str], claim_ents_ci: list[Entity],
                 art_sents: list[Sent],
                 art_ents: list[list[Entity]]) -> list[dict]:
    """Quellspannen je Fundstelle (Teilspanne = Ankerregion, sonst Satz).

    Läuft unabhängig von den Stufen-Schaltern: Die Spannen sind
    Anzeige-Verfeinerung, kein gewerteter Mechanismus — auch ein Lauf
    „--ohne 0" soll im Viewer lesbare Markierungen zeigen.
    """
    sources = []
    for rank, si in enumerate(srcs):
        s = art_sents[si]
        hits = [ae for ae in _numeric(art_ents[si])
                if _anchorworthy(ae) and any(_values_equal(ce, ae)
                       for ce in _numeric(claim_ents_ci))]
        anchor_spans = [(h.start - s.start, h.end - s.start) for h in hits]
        inseln = _evidence_spans(claim_grams_ci, s.text, anchor_spans)
        spans = [[s.start + lo, s.start + hi] for lo, hi in inseln]
        role = "redundant" if si in redundant else "primaer"
        # start/end bleibt die Hülle — ältere Viewer lesen nur diese.
        sources.append({"sentence": s.id,
                        "start": spans[0][0], "end": spans[-1][1],
                        "spans": spans, "role": role})
    return sources
