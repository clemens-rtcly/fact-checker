"""
Stufe 1 — Lexikalisches Alignment: Abdeckung, Ko-Lokalität, Matrizen.

Das Hauptsignal der Pipeline. Für jedes Paar (Claim, Artikelsatz)
entstehen hier zwei Werte:

  lex   Kosinus der Char-n-Gramm-TF-IDF-Vektoren über den VOLLEN Text
  cov   asymmetrischer Abdeckungsscore über INHALTSWÖRTER
        (A · B-Dämpfer + Ko-Lokalitäts-Bonus, siehe _coverage_score)

Beide Sichten bleiben nebeneinander bestehen, weil sie unterschiedliche
Fehler abfangen. `berechne` baut daraus das `Lexikalisch`-Bündel, auf dem
alle nachgelagerten Schritte (Fusion, Restabdeckung, Confidence,
Evidenz-Spannen) rechnen — einmal berechnet, überall gelesen.
"""
from __future__ import annotations

from dataclasses import dataclass

from konfig import CFG
from kern.lexik import (_content_grams, _content_tokens, _cos_sparse,
                        _ngrams, _prep, erzeuge_tfidf)
from kern.segmentierung import Sent
from stufe1 import zitate

_COLOC_W = 8       # Fenstergröße in Tokens
_COLOC_MIN = 5     # ab so vielen Treffern zählt das Maß voll


def _colocality(claim_tok_grams: list[set[str]], claim_pos: list[int],
                sent_tok_grams: list[set[str]], sent_pos: list[int],
                schwelle: float = 0.6) -> float:
    """Liegen Wörter, die im Artikelsatz nah beieinanderstehen, auch im
    Claim nah beieinander?

    Reihenfolgefrei — es zählt nur der Abstand, nicht die Richtung. Beim
    Zusammenfassen für Audio wird die Wortstellung regelmäßig gedreht;
    ein reihenfolgetreues Maß bestraft das zu Unrecht und findet bei
    umgestellten Sätzen nur Bruchstücke.

    Gedämpft bei wenigen Treffern: Aus zwei zufällig passenden Wörtern
    lässt sich keine Struktur ablesen.
    """
    treffer: list[tuple[int, int]] = []
    for sg, sp in zip(sent_tok_grams, sent_pos):
        if not sg:
            continue
        best, bi = 0.0, -1
        for k, cg in enumerate(claim_tok_grams):
            if not cg:
                continue
            v = len(sg & cg) / len(sg)
            if v > best:
                best, bi = v, k
        if best >= schwelle:
            treffer.append((claim_pos[bi], sp))
    if len(treffer) < 2:
        return 0.0
    nah = ges = 0
    for i in range(len(treffer)):
        for j in range(i + 1, len(treffer)):
            if abs(treffer[i][0] - treffer[j][0]) <= _COLOC_W:
                ges += 1
                nah += abs(treffer[i][1] - treffer[j][1]) <= _COLOC_W
    if not ges:
        return 0.0
    return (nah / ges) * min(1.0, len(treffer) / _COLOC_MIN)


def _coverage_score(claim_cvec, claim_cgrams, sent_cvec, sent_cgrams,
                    coloc: float, sent_cgrams_a: set[str] | None = None) -> float:
    """Asymmetrischer Abdeckungsscore für ein Paar.

    Drei Bestandteile, die unterschiedliche Fehler abfangen:

      A  Anteil des CLAIMS, den der Satz abdeckt — das Hauptsignal, denn
         belegt zu sein heißt, dass der Satz den Claim erklärt.
      B  Anteil des SATZES, den der Claim abdeckt — nur als milder
         Dämpfer. Lange Sätze decken kurze Claims zufällig leichter ab
         (gemessene Korrelation Satzlänge/A: +0,40). Eine symmetrische
         Verrechnung wäre falsch: Bei echter Zusammenfassung ist B
         naturgemäß klein, ohne dass die Zuordnung schlechter wäre.
      K  Ko-Lokalität — stehen im Satz benachbarte Wörter auch im Claim
         benachbart? Reihenfolgefrei.

    A und B laufen nur über Inhaltswörter. Sonst sammelt sich Gewicht in
    Artikeln und Hilfsverben: Gemessen tragen Funktionswörter im Schnitt
    15 bis 18 Prozent des Claim-Gewichts, in Einzelfällen über 35. Genau
    daran scheiterte ein Fall, in dem „diese … sind" eine Verdichtung mit
    einem inhaltlich unbeteiligten Satz auslöste (13,7 % Restbeitrag; nach
    der Filterung 1,3 %).

    `sent_cgrams_a` erlaubt für A eine ERWEITERTE Wortmenge, während B und
    der Vektor beim rohen Satz bleiben (Sprecherkontext, siehe zitate.py).
    Beides muss getrennt bleiben: Würde der geerbte Kontext auch in B
    einfließen, machte er den Satz künstlich länger und der Dämpfer würde
    genau die Sätze bestrafen, denen der Kontext helfen soll — gemessen
    fiel die Abdeckung dadurch von 0,479 auf 0,461, obwohl mehr Evidenz
    vorlag.
    """
    total = sum(claim_cvec.values()) or 1.0
    grams_a = sent_cgrams if sent_cgrams_a is None else sent_cgrams_a
    a = sum(w for g, w in claim_cvec.items() if g in grams_a) / total
    tot_s = sum(sent_cvec.values()) or 1.0
    b = sum(w for g, w in sent_cvec.items() if g in claim_cgrams) / tot_s

    floor, ref = CFG["cov_b_floor"], CFG["cov_b_ref"]
    damp = floor + (1.0 - floor) * min(1.0, b / ref if ref else 1.0)
    return min(1.0, a * damp + CFG["cov_contig"] * coloc)


# ------------------------------------------------------------------- Bündel

@dataclass
class Lexikalisch:
    """Alle lexikalischen Sichten eines Laufs, einmal berechnet.

    Zwei Namensfamilien, die streng auseinanderzuhalten sind:

      *_grams    n-Gramm-Mengen über den VOLLEN Text (für Evidenz-Spannen)
      *_cgrams   nur über INHALTSWÖRTER (für Abdeckung und Restbeitrag);
                 `art_cgrams_a` zusätzlich mit geerbtem Sprecherkontext —
                 darf nur dort gelesen werden, wo der Kommentar an der
                 Rechnung es ausdrücklich sagt (A-Term, „bereits erklärt").
    """
    lex: list[list[float]]            # Kosinus voll, Claims × Sätze
    cov: list[list[float]]            # Abdeckungsscore, Claims × Sätze
    art_grams: list[set[str]]
    claim_grams: list[set[str]]
    art_cgrams: list[set[str]]
    art_cgrams_a: list[set[str]]
    claim_cgrams: list[set[str]]
    art_cvecs: list[dict[str, float]]
    claim_cvecs: list[dict[str, float]]
    claim_ctoks: list[list[tuple[str, int]]]


def berechne(art_sents: list[Sent], claims_raw: list[Sent]) -> Lexikalisch:
    """Matrizen und Wortmengen für einen Lauf aufbauen (Stufe 1)."""
    m, n = len(claims_raw), len(art_sents)

    tfidf = erzeuge_tfidf([s.text for s in art_sents]
                          + [c.text for c in claims_raw])
    art_vecs = [tfidf.vec(s.text) for s in art_sents]
    claim_vecs = [tfidf.vec(c.text) for c in claims_raw]
    lex = [[_cos_sparse(cv, av) for av in art_vecs] for cv in claim_vecs]

    # Inhaltswort-Sicht für Abdeckung und Nähe. Der volle Text bleibt für
    # den Kosinus erhalten — beide Sichten fangen andere Fehler ab.
    art_grams = [set(_ngrams(_prep(s.text)).keys()) for s in art_sents]
    claim_grams = [set(_ngrams(_prep(c.text)).keys()) for c in claims_raw]

    # ---------------- Sprecherkontext (Zitatblöcke)
    # Zwei Wortmengen je Artikelsatz. Die angereicherte bestimmt nur, WAS
    # gefunden wird; berichtet und gespannt wird ausschließlich auf dem
    # rohen Satz. Sonst stünde im Inspector „erklärt 80 %", während ein
    # Teil davon aus einem Nachbarsatz stammt.
    kontexte = zitate.sprecherkontexte(art_sents)

    art_ctoks = [_content_tokens(s.text) for s in art_sents]
    claim_ctoks = [_content_tokens(c.text) for c in claims_raw]
    art_cgrams = [_content_grams(t) for t in art_ctoks]
    # A-Term darf den geerbten Kontext sehen, B-Term und Vektor nicht
    art_cgrams_a = [
        (art_cgrams[i] | _content_grams(_content_tokens(kontexte[i])))
        if kontexte[i] else art_cgrams[i]
        for i in range(len(art_sents))]
    claim_cgrams = [_content_grams(t) for t in claim_ctoks]
    art_cvecs = [{g: w for g, w in art_vecs[si].items() if g in art_cgrams[si]}
                 for si in range(n)]
    claim_cvecs = [{g: w for g, w in claim_vecs[ci].items()
                    if g in claim_cgrams[ci]} for ci in range(m)]
    art_tokgrams = [[set(_ngrams(_prep(w))) for w, _ in t] for t in art_ctoks]
    claim_tokgrams = [[set(_ngrams(_prep(w))) for w, _ in t] for t in claim_ctoks]
    art_tokpos = [[p for _, p in t] for t in art_ctoks]
    claim_tokpos = [[p for _, p in t] for t in claim_ctoks]

    cov = []
    for ci in range(m):
        zeile = []
        for si in range(n):
            # Ko-Lokalität nur rechnen, wo überhaupt Inhalt gemeinsam ist —
            # spart den teuren Tokenvergleich für die meisten Paare.
            grob = (len(claim_cgrams[ci] & art_cgrams_a[si])
                    / max(len(claim_cgrams[ci]), 1))
            k = 0.0
            if grob >= 0.10:
                k = _colocality(claim_tokgrams[ci], claim_tokpos[ci],
                                art_tokgrams[si], art_tokpos[si])
            zeile.append(_coverage_score(claim_cvecs[ci], claim_cgrams[ci],
                                         art_cvecs[si], art_cgrams[si], k,
                                         sent_cgrams_a=art_cgrams_a[si]))
        cov.append(zeile)

    return Lexikalisch(lex=lex, cov=cov,
                       art_grams=art_grams, claim_grams=claim_grams,
                       art_cgrams=art_cgrams, art_cgrams_a=art_cgrams_a,
                       claim_cgrams=claim_cgrams,
                       art_cvecs=art_cvecs, claim_cvecs=claim_cvecs,
                       claim_ctoks=claim_ctoks)
