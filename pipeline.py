"""
Alignment-Pipeline — Orchestrator.

Hier steht nur noch die Reihenfolge; jede Rechnung liegt in ihrem
Stufen-Modul. Die Stufen und ihre Orte:

  Stufe 0    stufe0/zahlen.py        Zahl-Normalisierung & Entitäten
             stufe0/anker.py         Anker-Boni + komplementäre Fundstellen
             stufe0/verifikation.py  Zahlkonflikt-Prüfung gegen Fundstellen
  Stufe 0.5  stufe0/personen.py      Personen über NER + Namensabgleich
  Stufe 0.6  stufe0/identifier.py    Orte, Organisationen, Kürzel —
                                     exakter Abgleich, Fast-Identität gilt
                                     als Verdacht
  Stufe 0.8  stufe0/wortlaut.py      Wortlaut-Diff bei nahezu wörtlicher
                                     Übernahme
  Stufe 1    stufe1/abdeckung.py     Char-n-Gramm-TF-IDF, asymmetrische
                                     Claim-Abdeckung mit Wortfolgen-Bonus
             stufe1/zitate.py        Sprecherkontext für Zitatblöcke
             stufe1/spannen.py       Evidenz-Spannen für den Viewer
  Stufe 1.2  stufe1/teilaussagen.py  Sätze an Konnektoren zerlegen
  Stufe 1.5  stufe1/restabdeckung.py weitere Quellen nach Zusatzbeitrag
  Stufe 2    stufe2/saia.py          Embeddings (SAIA oder lokal, optional)
             stufe2/skalierung.py    Matrix-Normalisierung
  Stufe 3    stufe3/nli.py           NLI-Modelle (lokal, optional)
             stufe3/praemisse.py     Prämissenbau je Claim
             stufe3/nachentscheidung.py  Urteil -> `bedeutung_verschoben`,
                                     Flag `nli_widerspruch`

Quer dazu: kern/ (Text, Segmentierung, Lexik, Fusion, Entscheidung,
Ausgabe) und konfig.py (CFG, STUFEN, VARIANTE).

Die Reihenfolge der Blöcke in `align` ist Teil des Ausgabevertrags:
Notizen und Flags erscheinen im JSON in Aufrufreihenfolge. Wer hier
umsortiert, ändert die Ausgabe.

Einzelne Mechanismen lassen sich über `stufen` abschalten
(konfig.STUFEN, CLI: `batch.py --ohne 0.5,wortlaut`) — zur Messung, was
jede Stufe beiträgt. Stufe 1 ist nicht abschaltbar: Sie ist das Rückgrat,
auf dem alle Schwellen kalibriert sind.

Ausgabe: JSON exakt im Schema des Split-View-Prototyps
(article.sentences, transcript.claims mit relation/sources/confidence/
margin/entities/flags/note).

Keine externen Abhängigkeiten. Embeddings werden als Funktion injiziert.
"""
from __future__ import annotations

import konfig
from konfig import CFG, STUFEN, VARIANTE  # noqa: F401  (Kompat-Ausfuhr)
from kern import ausgabe, entscheidung, fusion
from kern.lexik import TfIdf  # noqa: F401  (Kompat-Ausfuhr für Altskripte)
from kern.segmentierung import Sent, segment  # noqa: F401  (Kompat-Ausfuhr)
from kern.text import strip_html
from stufe0 import anker, personen as ner, verifikation, wortlaut
from stufe0.zahlen import extract_entities
from stufe1 import abdeckung, restabdeckung, spannen, teilaussagen
from stufe2 import skalierung
from stufe3 import nachentscheidung, praemisse


def align(article_text: str, transcript_text: str,
          embed_fn=None, model_label: str = "ohne Embeddings",
          nli_fn=None, stufen: dict[str, bool] | None = None) -> dict:
    """Hauptfunktion.

    embed_fn(texts, is_query) -> list[list[float]] | None
    nli_fn(pairs) -> list[{"entailment","neutral","contradiction": float}]
        Optional (Stufe 3). Bekommt (Prämisse, Hypothese)-Paare und liefert
        Wahrscheinlichkeiten in Eingabereihenfolge, siehe nli.classify.
    stufen
        Überschreibungen für konfig.STUFEN, z. B. {"0.5_personen": False}.
        Nur bei Abweichung vom Standard wird `meta.stufen` geschrieben —
        Läufe mit allen Stufen bleiben byte-identisch zu vorher.
    """
    st = konfig.aktive_stufen(stufen)

    def _abschluss(art_sents, claims_json):
        result = ausgabe.assemble(article_text, transcript_text,
                                  art_sents, claims_json, model_label)
        if any(not v for v in st.values()):
            result["meta"]["stufen"] = dict(st)
        return result

    article_text = strip_html(article_text)
    transcript_text = strip_html(transcript_text)
    art_sents = segment(article_text, "article", "s")
    claims_raw = teilaussagen.waehle_claims(
        transcript_text, art_sents, aktiv=st["1.2_teilaussagen"])

    art_ents = [extract_entities(s.text) for s in art_sents]
    # Offsets der Satz-Entities auf Dokumentkoordinaten heben
    for s, es in zip(art_sents, art_ents):
        for e in es:
            e.start += s.start
            e.end += s.start
    claim_ents = [extract_entities(c.text) for c in claims_raw]
    for c, es in zip(claims_raw, claim_ents):
        for e in es:
            e.start += c.start
            e.end += c.start

    # Stufe 0.5: Personen getrennt von den Zahlen (spaCy o. Rückfall).
    # Abgeschaltet entfällt auch der NER-Aufruf selbst — leere Listen
    # lassen Anker-Namensbonus und Namensabgleich von allein leerlaufen.
    if st["0.5_personen"]:
        art_persons = [ner.persons(s.text) for s in art_sents]
        claim_persons = [ner.persons(c.text) for c in claims_raw]
    else:
        art_persons = [[] for _ in art_sents]
        claim_persons = [[] for _ in claims_raw]

    m, n = len(claims_raw), len(art_sents)
    if m == 0 or n == 0:
        return _abschluss(art_sents, [])

    # ---------------- Stufe 1: lexikalische Matrizen (nicht abschaltbar)
    lexi = abdeckung.berechne(art_sents, claims_raw)

    # ---------------- Stufe 2: Embeddings (optional)
    emb = None
    if embed_fn is not None and st["2_embeddings"]:
        emb = skalierung.berechne(embed_fn, art_sents, claims_raw)

    # ---------------- Stufe 0: Anker
    if st["0_anker"]:
        anchor, anchor_notes = anker.matrix(
            claim_ents, art_ents, claim_persons, art_persons,
            art_sents, m, n)
    else:
        anchor = [[0.0] * n for _ in range(m)]
        anchor_notes = [[] for _ in range(m)]

    # ---------------- Fusion
    fused, ist_frage = fusion.matrix(lexi.cov, lexi.lex, emb, anchor,
                                     art_sents, m, n)

    # ---------------- Entscheidungen pro Claim
    claims_json: list[dict] = []
    # (Index, Prämisse, Hypothese, Downgrade-Schutz, Quelltext)
    nli_jobs: list[tuple[int, str, str, bool, str]] = []
    for ci, c in enumerate(claims_raw):
        row = fused[ci]
        order = sorted(range(n), key=lambda si: -row[si])
        s1, si1 = row[order[0]], order[0]
        s2 = row[order[1]] if n > 1 else 0.0
        margin = round(max(s1 - s2, 0.0), 2)
        note_parts = list(anchor_notes[ci])
        flags: list[str] = []

        def _merke(neue_flags: list[str]) -> None:
            for f in neue_flags:
                if f not in flags:
                    flags.append(f)

        # ---------------- Primärzuordnung
        relation, srcs, redundant, conf, unter_schwelle, noten = \
            entscheidung.primaerzuordnung(row, order, art_sents)
        note_parts += noten

        # ---------------- Stufe 1.5: Restabdeckung (gierig)
        gains: list[tuple[int, float]] = []
        if st["1.5_restabdeckung"] and relation != "keine_quelle" \
                and len(c.text) >= CFG["agg_min_claim_len"]:
            gains = restabdeckung.verdichte(
                lexi, ci, c.text, art_sents, srcs, redundant, ist_frage,
                emb[ci] if emb else None)

        # ---------------- Stufe 0: komplementäre Zahlen-Anker
        anchor_extra: list[int] = []
        if st["0_anker"] and relation != "keine_quelle":
            anchor_extra = anker.komplementaere(claim_ents[ci], art_ents,
                                                srcs)
            for si in sorted(set(anchor_extra)):
                if si not in srcs:
                    srcs.append(si)

        if relation == "direkt" and len(srcs) > 1:
            relation = "aggregiert"
            teile = []
            if gains:
                teile.append(", ".join(
                    f"{art_sents[si].id} erklärt zusätzlich "
                    f"{g:.0%}".replace("%", " %") for si, g in gains))
            if anchor_extra:
                teile.append("Zahlen-Anker in " + ", ".join(
                    art_sents[si].id for si in sorted(set(anchor_extra))))
            note_parts.append(
                "Verdichtet aus " + " + ".join(art_sents[si].id for si in srcs)
                + (" (" + "; ".join(teile) + ")." if teile else "."))

        srcs = srcs + [si for si in redundant if si not in srcs]

        # ---------------- Margin NACH der Aggregation neu bestimmen
        if relation != "keine_quelle":
            margin = entscheidung.margin_nach_aggregation(row, srcs, n)

        # ---------------- Confidence aus zwei unabhängigen Signalen
        if relation != "keine_quelle":
            conf, _cov_total, cflags, cnoten = \
                entscheidung.confidence_und_notizen(
                    lexi.claim_cvecs[ci], lexi.art_cgrams,
                    emb[ci] if emb else None, srcs, margin, unter_schwelle)
            _merke(cflags)
            note_parts += cnoten

        # ---------------- Stufe 0: Entity-Verifikation gegen die Fundstellen
        ents_json: list[dict] = []
        if st["0_verifikation"]:
            src_sent_ids = set(srcs)
            near_ids = set(src_sent_ids)
            for si in src_sent_ids:
                near_ids |= {k for k in range(n)
                             if art_sents[k].paragraph == art_sents[si].paragraph}
            ez, zflags, znoten = verifikation.pruefe_zahlen(
                claim_ents[ci], art_ents, art_sents, srcs, near_ids)
            ents_json += ez
            _merke(zflags)
            note_parts += znoten

        # ---------------- Stufe 0.5: Namensabgleich
        if st["0.5_personen"]:
            ep, pflags, pnoten = verifikation.pruefe_personen(
                claim_persons[ci], art_persons, article_text)
            ents_json += ep
            _merke(pflags)
            note_parts += pnoten

        # ---------------- Stufe 0.6: Identifier (Orte, Organisationen, Kürzel)
        if st["0.6_identifier"]:
            ei, iflags, inoten = verifikation.pruefe_identifier(
                c.text, article_text)
            ents_json += ei
            _merke(iflags)
            note_parts += inoten

        # ---------------- Stufe 0.8: Wortlaut-Diff bei Fast-Wörtlichkeit
        wl = None
        if st["0.8_wortlaut"] and srcs:
            wl, wflags, wnoten = wortlaut.pruefe(
                c.text, art_sents[si1], lexi.lex[ci][si1])
            _merke(wflags)
            note_parts += wnoten

        # ---------------- Quellspannen (Anzeige, kein Mechanismus)
        sources_json = spannen.quellen_json(
            srcs, redundant, lexi.claim_grams[ci], claim_ents[ci],
            art_sents, art_ents)

        # ---------------- Stufe 3: NLI-Auftrag einsammeln (Lauf erst nach
        # der Schleife, damit alle Paare in EINEM Batch durchs Modell gehen)
        if nli_fn is not None and st["3_nli"] \
                and relation in ("direkt", "aggregiert"):
            nli_jobs.append(praemisse.auftrag(len(claims_json), c, srcs,
                                              art_sents))

        claims_json.append({
            "id": c.id, "start": c.start, "end": c.end, "text": c.text,
            "relation": relation, "sources": sources_json,
            "confidence": conf, "margin": margin,
            "entities": ents_json, "flags": flags,
            "wortlaut": wl,
            "note": " · ".join(note_parts),
            "scores": {"top": round(s1, 3),
                       "lex": round(lexi.lex[ci][si1], 3),
                       "emb": (round(emb[ci][si1], 3) if emb else None),
                       "anchor": round(anchor[ci][si1], 3),
                       "nli": None},
        })

    # ---------------- Stufe 3: NLI-Nachentscheidung
    if nli_fn is not None and st["3_nli"]:
        nachentscheidung.anwenden(claims_json, nli_jobs, nli_fn)

    return _abschluss(art_sents, claims_json)
