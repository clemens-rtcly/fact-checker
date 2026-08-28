"""
Zentrale Konfiguration — Import-Blatt ohne eigene Abhängigkeiten.

Drei Dinge liegen hier, und zwar genau hier, damit kein Zirkelimport
entsteht (jedes Stufen- und Kern-Modul darf konfig importieren, konfig
importiert nichts):

  CFG       Stellschrauben der Pipeline. Werden zur LAUFZEIT gelesen —
            `varianten.py` ändert das Dict in place für die Dauer eines
            Laufs. Deshalb nie Werte beim Import herauskopieren.

  STUFEN    Schalter je Mechanismus, zur Beitragsmessung einzeln
            abschaltbar (batch.py --ohne …). Stufe 1 (lexikalische
            Matrix) fehlt bewusst: Sie ist das Rückgrat — Fusion,
            Schwellen und Restabdeckung sind auf ihr kalibriert, ohne
            sie ist kein Wert mehr interpretierbar.

  VARIANTE  Aushänge für Experimente, siehe varianten.py. Standard ist
            überall None = unverändertes Verhalten.
"""
from __future__ import annotations

# ------------------------------------------------------------- Stellschrauben

CFG = {
    # Fusionsgewichte (werden ohne Embeddings automatisch renormalisiert)
    "w_emb": 0.40,
    "w_cov": 0.28,
    "w_lex": 0.20,
    "w_pos": 0.12,
    # Abdeckungsscore: A · B-Dämpfer + Wortfolgen-Bonus
    "cov_contig": 0.30,   # Gewicht der Ko-Lokalität im Abdeckungsscore
    "cov_b_floor": 0.75,  # stärkste Dämpfung bei sehr geringer Rückabdeckung
    "cov_b_ref": 0.30,    # ab dieser Rückabdeckung wird nicht mehr gedämpft
    # Confidence: Potenzmittel über Abdeckung und Embedding
    "conf_power": 3.0,    # 1 = Mittelwert, ∞ = Maximum
    "conf_margin_ref": 0.15,
    # Ab dieser gemeinsamen Abdeckung gilt eine Verdichtung als tragfähig,
    # auch wenn kein Einzelsatz die Direkt-Schwelle erreicht hat.
    "agg_cov_ok": 0.60,
    "dissens_delta": 0.45,  # ab hier gelten die Signale als uneinig
    # Anker-Boni (additiv, gedeckelt)
    "anchor_unique": 0.30,   # numerischer Anker, eindeutig im Artikel
    "anchor_multi": 0.12,    # numerischer Anker, 2–3 Fundstellen
    "anchor_name_unique": 0.20,  # Eigenname, genau ein Artikelsatz
    "anchor_name": 0.10,     # Eigenname, zwei Artikelsätze
                             # Ab drei Fundstellen kein Bonus: Ein Name,
                             # der über den Text verteilt ist, lokalisiert
                             # nichts. Die Stufen spiegeln die numerischen
                             # (`anchor_unique`/`anchor_multi`), bleiben
                             # aber darunter — Namen wiederholen sich in
                             # Nachrichtentexten von Natur aus, und der
                             # Abgleich ist heuristisch (`personen.matches`).
                             # Der Zweierwert ist unverändert, damit die
                             # Änderung rein additiv ist und keinen Claim
                             # schlechter stellen kann.
    "anchor_cap": 0.38,
    # Entscheidungsschwellen auf dem fusionierten Score.
    # Kalibriert an zwei Textpaaren (25 Claims mit bekannter Quelle,
    # 3 ohne). Die Trennung lag dort zwischen 0,431 und 0,460 — das ist
    # eine sehr dünne Datenbasis, besonders auf der Negativseite.
    "t_direct": 0.60,
    "t_none": 0.44,
    # Ab diesem Anteil von t_none gilt ein gescheiterter Kandidat als
    # knapp und wird in der Notiz genannt.
    "knapp_faktor": 0.60,
    # Aggregation über Restabdeckung (Stufe 1.5):
    # Ein weiterer Satz wird aufgenommen, wenn er einen Anteil des Claims
    # erklärt, den die bisherigen Fundstellen NICHT erklären.
    # Restabdeckung: nötiger Zusatzbeitrag, abhängig vom Abstand zur
    # nächsten schon gewählten Fundstelle (siehe restabdeckung.schwelle)
    "residual_nah_abstand": 2,   # bis hierhin gilt ein Satz als benachbart
    "residual_min_nah": 0.10,    # Nachbarschaft: niedrigere Hürde
    "residual_min_fern": 0.22,   # Ferne: höhere Hürde gegen Scheinbelege
    "residual_max_sources": 3,   # Obergrenze der Fundstellen je Claim
    "residual_min_carriers": 2,  # so viele Inhaltswörter müssen den
                                 # Zusatzbeitrag tragen (gegen Scheinbelege)
    "agg_min_claim_len": 55,     # sehr kurze Claims aggregieren nicht
    # Redundante Fundstellen
    "redundant_delta": 0.07,
    # Teilaussagen (Stufe 1.2): Schalter liegt in STUFEN["1.2_teilaussagen"]
    "split_min_lex": 0.16,   # darunter gilt ein Teil als "findet nichts";
                             # zurückgeführt wird er nur mit Rückverweis
    # NLI (Stufe 3): Entscheidung auf den Softmax-Wahrscheinlichkeiten.
    # Vorläufige Setzung — wie t_direct/t_none erst mit einem Gold-Set
    # seriös kalibrierbar. Herabgestuft zu `bedeutung_verschoben` wird nur,
    # wenn Entailment unter der Schwelle liegt UND Neutral die dominante
    # Klasse ist (Definition des dritten Link-Status: widerspricht nicht,
    # stützt aber auch nicht).
    # Fragesätze belegen nichts — Abschlag statt Ausschluss (siehe fusion)
    "frage_faktor": 0.55,
    "nli_entail_min": 0.60,   # darunter gilt der Claim als nicht gestützt
    "nli_contra_min": 0.55,   # darüber Flag `nli_widerspruch` …
    "nli_contra_margin": 0.25,  # … aber nur mit diesem Abstand zu
                                # entailment; sonst ist das Modell
                                # unentschieden und der Chip zu laut
    "nli_contra_support_max": 0.75,  # … und oberhalb dieser Stützung durch
                                # lex/emb nur noch bei Negationsasymmetrie:
                                # ein Claim mit sehr hoher Übereinstimmung,
                                # in dem nichts verneint wird, ist eher
                                # korrekt verdichtet als widersprüchlich
    # Widerspruch bei Wortgleichheit (Stufe 3, Zusatzmeldung).
    # Genau die Konstellation, die `nli_contra_support_max` entschärft,
    # ist oberhalb dieser Werte die aussagekräftigste überhaupt: Sind zwei
    # Sätze fast wortgleich und das Modell meldet Widerspruch, MUSS der
    # Widerspruch in dem Rest sitzen, der sich unterscheidet. Der
    # gemessene Fehlermodus (bildhafter Ausdruck über wechselnde
    # grammatische Form) setzt einen Formwechsel voraus — bei
    # Wortgleichheit gibt es keinen. Bewusst nur ein Flag: die Relation
    # bleibt unverändert, bis genug Fälle gezählt sind.
    "nli_wortgleich_contra": 0.90,
    "nli_wortgleich_lex": 0.92,
    # Wortlaut-Diff (Stufe 0.8): ab dieser lexikalischen Übereinstimmung
    # gilt ein Claim als nahezu wörtlich übernommen und wird Wort für Wort
    # gegen die Primärfundstelle gestellt.
    "diff_lex_min": 0.85,
    "diff_nah_min": 0.55,        # ab dieser Zeichenähnlichkeit gilt eine
                                 # Ersetzung als verdächtig nah
    "diff_max_worte": 5,         # längere Ersetzungen sind Umformulierung,
                                 # nicht Vertauschung
    "diff_max_meldungen": 6,
}

# ------------------------------------------------------------------- Stufen

# Ein Schalter je MECHANISMUS, nicht je Hauptstufe — zur Beitragsmessung
# will man Anker und Zahl-Verifikation getrennt kippen können. True ist
# überall der bisherige Normalbetrieb; die früheren CFG-Schlüssel
# `ident_pruefen` und `split_claims` sind hierher gewandert.
#
# Stufe 2 und 3 haben zusätzlich die alte Abschaltung über die Aufrufer
# (batch.py --emb ohne / --nli ohne): Der Schalter hier greift auch dann,
# wenn eine embed_fn/nli_fn übergeben wurde — nützlich, um in EINEM
# Batch-Lauf mit geladenem Modell die Stufe stumm zu schalten.
STUFEN = {
    "0_anker": True,           # Zahl-/Namensanker als Score-Bonus
                               # + komplementäre Anker-Fundstellen
    "0_verifikation": True,    # Zahlen gegen die Fundstellen prüfen
                               # (zahlkonflikt / zahl_unbelegt)
    "0.5_personen": True,      # Personen-NER + Namensabgleich
    "0.6_identifier": True,    # Orte, Organisationen, Kürzel
    "0.8_wortlaut": True,      # Wort-für-Wort-Diff bei Fast-Wörtlichkeit
    "1.2_teilaussagen": True,  # Transkriptsätze an Konnektoren zerlegen
    "1.5_restabdeckung": True, # Verdichtung: weitere Quellen nach Restbeitrag
    "2_embeddings": True,      # nur wirksam, wenn eine embed_fn übergeben ist
    "3_nli": True,             # nur wirksam, wenn eine nli_fn übergeben ist
}

# Kurzformen für die Kommandozeile: Nummer ODER Name, beides erlaubt.
# "0" trifft beide 0er-Mechanismen.
_KUERZEL = {
    "0": ["0_anker", "0_verifikation"],
    "0_anker": ["0_anker"], "anker": ["0_anker"],
    "0_verifikation": ["0_verifikation"], "verifikation": ["0_verifikation"],
    "0.5": ["0.5_personen"], "personen": ["0.5_personen"],
    "0.6": ["0.6_identifier"], "identifier": ["0.6_identifier"],
    "0.8": ["0.8_wortlaut"], "wortlaut": ["0.8_wortlaut"],
    "1.2": ["1.2_teilaussagen"], "teilaussagen": ["1.2_teilaussagen"],
    "1.5": ["1.5_restabdeckung"], "restabdeckung": ["1.5_restabdeckung"],
    "2": ["2_embeddings"], "embeddings": ["2_embeddings"],
    "3": ["3_nli"], "nli": ["3_nli"],
}


def stufen_aus_kuerzeln(kuerzel: list[str]) -> dict[str, bool]:
    """Kommandozeilen-Kürzel („0.5", „wortlaut") in Schalter übersetzen.

    Liefert NUR die abgeschalteten Einträge — das Ergebnis wird über die
    Standardwerte gelegt (`aktive_stufen`). Unbekannte Kürzel sind ein
    Fehler, kein stilles Ignorieren: Ein Tippfehler in `--ohne` würde
    sonst einen Lauf erzeugen, der etwas anderes misst als beschriftet.
    """
    aus: dict[str, bool] = {}
    for k in kuerzel:
        k = k.strip()
        if not k:
            continue
        if k not in _KUERZEL:
            raise KeyError(
                f"Unbekannte Stufe: {k!r} — erlaubt sind "
                f"{sorted(set(_KUERZEL))}")
        for name in _KUERZEL[k]:
            aus[name] = False
    return aus


def aktive_stufen(overrides: dict[str, bool] | None = None) -> dict[str, bool]:
    """STUFEN mit Überschreibungen zusammenführen (Kopie, nie in place)."""
    st = dict(STUFEN)
    if overrides:
        unbekannt = [k for k in overrides if k not in STUFEN]
        if unbekannt:
            raise KeyError(f"Unbekannte Stufen-Schalter: {unbekannt}")
        st.update(overrides)
    return st


# ------------------------------------------------------------------ Aushänge

# Aushänge für Experimente. Standard ist überall None = unverändertes
# Verhalten; `varianten.py` setzt sie für die Dauer eines Laufs und nimmt
# sie danach zurück. So lassen sich Alternativen gegen das Gold-Set
# messen, ohne dass jemand für jeden Versuch in den Code greift und
# hinterher vergisst, ihn zurückzudrehen.
#
#   gewinn(g, kandidat_text, claim_text) -> float
#       Formt den Restbeitrag, bevor er gegen die Abstandsschwelle läuft.
#   max_quellen(claim_text, standard) -> int
#       Obergrenze der Fundstellen, claimabhängig statt fest.
#   zusatzquellen(claim_text, art_texte, srcs, emb_zeile, frei) -> list[int]
#       Ergänzt Fundstellen nach der gierigen Restabdeckung, etwa für
#       Identifier, die im Claim stehen und in keiner der bisherigen
#       Quellen vorkommen. `emb_zeile` ist die Embedding-Ähnlichkeit des
#       Claims zu jedem Artikelsatz oder None, `frei` die Zahl der noch
#       offenen Plätze.
#   tfidf_klasse
#       Ersatzklasse für kern.lexik.TfIdf (Schnittstelle: __init__(docs),
#       vec(text)). Ersetzt das frühere Monkeypatching von pipeline.TfIdf
#       durch einen benannten Hook; konstruiert wird ausschließlich über
#       kern.lexik.erzeuge_tfidf, damit der Hook überall greift.
VARIANTE: dict = {"gewinn": None, "max_quellen": None,
                  "zusatzquellen": None, "tfidf_klasse": None}
