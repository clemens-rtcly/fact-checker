"""
Stufe 0 / 0.5 / 0.6 — Verifikation der Claim-Entitäten gegen den Artikel.

Drei Prüfungen, drei Funktionen, gemeinsames Rückgabeformat
(`ents`, `flags`, `notes`): Der Orchestrator hängt die Ergebnisse in
dieser Reihenfolge an den Claim — Zahlen, dann Personen, dann
Identifier — damit die JSON-Ausgabe deckungsgleich zur bisherigen bleibt.

  pruefe_zahlen      Stufe 0: match / konflikt / unbelegt je numerischer
                     Entität, Konflikt nur gegen VERGLEICHBARE Werte.
  pruefe_personen    Stufe 0.5: Namensabgleich tokenbasiert (personen.py).
  pruefe_identifier  Stufe 0.6: Orte, Organisationen, Kürzel — eigener
                     Kanal mit umgekehrter Logik, Fast-Identität ist
                     Verdacht (identifier.py).
"""
from __future__ import annotations

from kern.segmentierung import Sent
from stufe0 import identifier, personen as ner
from stufe0.anker import _numeric, _values_equal
from stufe0.zahlen import Entity


def pruefe_zahlen(claim_ents_ci: list[Entity],
                  art_ents: list[list[Entity]],
                  art_sents: list[Sent],
                  srcs: list[int],
                  near_ids: set[int]) -> tuple[list[dict], list[str], list[str]]:
    """Numerische Entitäten des Claims gegen den Artikel stellen.

    Exakter Treffer irgendwo im Artikel -> `match`. Sonst wird der
    nächstliegende VERGLEICHBARE Wert gesucht — bevorzugt in den
    Fundstellen und ihren Absätzen (`near_ids`) — und als `konflikt`
    gemeldet; ohne vergleichbaren Kandidaten bleibt `unbelegt`.
    """
    ents: list[dict] = []
    flags: list[str] = []
    notes: list[str] = []
    all_art_numeric = [(si, e) for si, es in enumerate(art_ents)
                       for e in _numeric(es)]

    for e in _numeric(claim_ents_ci):
        exact = [si for si, ae in all_art_numeric if _values_equal(e, ae)]
        if exact:
            ents.append({"type": e.type, "surface": e.surface,
                         "norm": str(e.norm), "status": "match"})
            continue
        same_type_near = [(si, ae) for si, ae in all_art_numeric
                          if ae.type == e.type and si in near_ids]
        if not same_type_near:
            same_type_near = [(si, ae) for si, ae in all_art_numeric
                              if ae.type == e.type]
        # Vergleichbarkeit ist Voraussetzung für „weicht ab". Ein
        # Verhältnis (Wert `"0:0"`) und ein Skalar (Wert `0.0`) tragen
        # beide den Typ `zahl`, sind aber nicht auf einer Skala
        # vergleichbar. Ohne diese Prüfung war jeder Abstand `inf`,
        # `min` nahm den erstbesten Kandidaten und meldete
        # „0:0 weicht ab — Artikel nennt 0".
        def _dist(pair):
            _si, ae = pair
            a, b = ae.value, e.value
            # Strukturierte Werte (Verhältnis `0:0`, Spanne `8-10`)
            # sind untereinander vergleichbar, wenn sie dieselbe Form
            # haben: komponentenweiser Abstand. Damit meldet die
            # Prüfung „8-12 weicht ab — Artikel nennt 8-10" statt nur
            # „unbelegt". Gegen einen Skalar bleiben sie unvergleichbar.
            if isinstance(a, str) and isinstance(b, str):
                for sep in (":", "-"):
                    if sep in a and sep in b:
                        ta, tb = a.split(sep), b.split(sep)
                        if len(ta) != len(tb):
                            return float("inf")
                        try:
                            return sum(abs(float(x) - float(y))
                                       for x, y in zip(ta, tb))
                        except ValueError:
                            return float("inf")
                return float("inf")
            try:
                return abs(float(a) - float(b))
            except (TypeError, ValueError):
                return float("inf")
        vergleichbar = [pair for pair in same_type_near
                        if _dist(pair) != float("inf")]
        if vergleichbar and srcs:
            si, ae = min(vergleichbar, key=_dist)
            ents.append({
                "type": e.type, "surface": e.surface, "norm": str(e.norm),
                "status": "konflikt",
                "quelle_surface": ae.surface, "quelle_norm": str(ae.norm),
            })
            if "zahlkonflikt" not in flags:
                flags.append("zahlkonflikt")
            notes.append(
                f"{e.norm} weicht ab — Artikel nennt {ae.norm} "
                f"({art_sents[si].id}).")
        else:
            ents.append({"type": e.type, "surface": e.surface,
                         "norm": str(e.norm), "status": "unbelegt"})
            if "zahl_unbelegt" not in flags:
                flags.append("zahl_unbelegt")
            notes.append(f"{e.norm} im Artikel nicht auffindbar.")
    return ents, flags, notes


def pruefe_personen(claim_persons_ci: list[tuple[str, int, int]],
                    art_persons: list[list[tuple[str, int, int]]],
                    article_text: str) -> tuple[list[dict], list[str], list[str]]:
    """Stufe 0.5: Personennamen des Claims gegen die Artikel-Namen."""
    ents: list[dict] = []
    notes: list[str] = []
    art_person_names = [nm for names in art_persons for nm, _a, _b in names]
    for surface, _s, _e in claim_persons_ci:
        found = ner.matches(surface, art_person_names, article_text)
        ents.append({"type": "person", "surface": surface,
                     "norm": surface.lower(),
                     "status": "match" if found else "unbelegt"})
        if not found:
            notes.append(
                "Name \u201e" + surface + "\u201c nicht im Artikel belegt.")
    return ents, [], notes


def pruefe_identifier(claim_text: str, article_text: str
                      ) -> tuple[list[dict], list[str], list[str]]:
    """Stufe 0.6: Orte, Organisationen, Kürzel (identifier.py).

    Eigener Kanal mit umgekehrter Logik: Die Stufen 1/2 lesen
    Ähnlichkeit als Belegtheit, hier ist Fast-Identität ein Verdacht.
    Ohne diesen Kanal ist „XL-Rechenzentrum in Langenharm" gegen
    „XXL-Rechenzentrum in Langenhorn" nicht auffindbar — gemessen
    Abdeckung 1,00 bei lex 0,90, die Verfälschung *erhöht* den Score.
    """
    ents: list[dict] = []
    flags: list[str] = []
    notes: list[str] = []
    for b in identifier.pruefe(claim_text, article_text):
        marke = "ort_konflikt" if b["art"] == "ort" else "kuerzel_konflikt"
        if b["status"] == "konflikt":
            ents.append({
                "type": b["art"], "surface": b["surface"],
                "norm": b["surface"].lower(), "status": "konflikt",
                "quelle_surface": b["quelle_surface"],
                "quelle_norm": b["quelle_surface"].lower()})
            if marke not in flags:
                flags.append(marke)
            notes.append(
                "\u201e" + b["surface"] + "\u201c steht so nicht im "
                "Artikel \u2014 dort \u201e" + b["quelle_surface"]
                + "\u201c.")
        else:
            ents.append({
                "type": b["art"], "surface": b["surface"],
                "norm": b["surface"].lower(), "status": "unbelegt"})
            if "ident_unbelegt" not in flags:
                flags.append("ident_unbelegt")
            notes.append(
                "\u201e" + b["surface"] + "\u201c im Artikel nicht "
                "auffindbar.")
    return ents, flags, notes
