"""
Ablation: Trägt die NLI-Rückrichtung Signal für `inferiert`?

Hintergrund. `inferiert` ist im Schema vorgesehen und wird nie vergeben.
Die naheliegende Ableitung — „entailt bei niedriger lexikalischer
Überlappung" — misst vor allem Kürze: Das Entailment-Signal dieses
Modells klebt bei 0,00 und 0,99, und `lex` bricht bei jeder normalen
Verdichtung ein. Beides zusammen labelt korrekte Zusammenfassungen.

Der theoretisch richtige Diskriminator ist die **Richtungsasymmetrie**:

    Direkte Wiedergabe   Quelle -> Claim entailt UND Claim -> Quelle entailt
                         (gleicher Inhalt, andere Worte — wechselseitig)
    Ableitung            Quelle -> Claim entailt, Claim -> Quelle NICHT
                         (der Claim ist schwächer/abgeleitet — einseitig)

Zwei Fragen, zwei Betriebsarten dieses Skripts:

  1. **Trennt die Rückrichtung überhaupt?** (`--kontrolle`, handgeschrieben)
     Wenn die Rückrichtung ebenso binär ausfällt wie die Vorwärtsrichtung,
     gibt es keinen nutzbaren Gradienten und der Ansatz ist tot. Ebenso
     zu prüfen: **Materialüberschuss** — ein langer Artikelsatz wird von
     einem kurzen Claim praktisch nie entailt, allein weil er mehr
     Material enthält, nicht weil etwas abgeleitet wurde. Deshalb läuft
     die Rückrichtung zusätzlich gegen die **Evidenz-Spans** (`R_span`)
     statt nur gegen den ganzen Satz (`R_satz`).

  2. **Wie viele echte Kandidaten erreicht sie überhaupt?** (`--reichweite`,
     echte Läufe) Der Kontrollsatz zeigt nur, ob das Modell den
     Unterschied *sehen kann*. Er sagt nichts darüber, wie oft die
     Vorwärtsrichtung bei echten, unsicheren Claims überhaupt trägt.
     Reicht ein Zwischenschritt vom Diskriminator nicht heran — etwa weil
     ein Claim eine Zahl in ein Werturteil übersetzt („150 Megawatt" ->
     „besonders groß") statt sie nur einzubetten — scheitert schon `V`,
     und die Richtungsasymmetrie wird nie geprüft. `--reichweite` misst
     diesen Anteil auf allen `bedeutung_verschoben`-Claims aus echten
     Läufen: dem Bereich, aus dem `inferiert` seine Fälle holen müsste.

Das Skript ändert nichts an der Pipeline. Es liest exportierte Läufe
(die JSON-Dateien aus dem Viewer) und misst darauf.

    python3 inferiert_ablation.py --kontrolle           # Kann das Modell trennen?
    python3 inferiert_ablation.py --reichweite lauf.json # Wie oft trägt V?
    python3 inferiert_ablation.py lauf1.json lauf2.json  # normaler Modus
    python3 inferiert_ablation.py lauf.json --alle       # ohne Vorfilter
    python3 inferiert_ablation.py lauf.json --modell nli-gbert-large

Empfohlene Reihenfolge: erst `--kontrolle` (trennt das Modell überhaupt?),
dann `--reichweite` (wie oft kommt es in echten Daten zum Einsatz?). Nur
wenn beides positiv ausfällt, lohnt der Einbau in die Pipeline.
"""
from __future__ import annotations

import json
import sys

from kern import lexik
from stufe3 import nli

# --------------------------------------------------------------- Vorfilter
# Methode C als billiger Vorfilter: Nur Claims doppelt testen, bei denen
# eine Ableitung überhaupt plausibel ist. Erklären die Fundstellen fast
# den ganzen Claim, ist es eine Übernahme; stützt das NLI ihn gar nicht,
# ist es `bedeutung_verschoben` und nicht `inferiert`.
FILTER = {
    "cov_max": 0.80,      # darüber: der Claim steht praktisch im Artikel
    "entail_min": 0.50,   # darunter: nicht gestützt, also kein Kandidat
}

# Als „gesättigt" gilt ein Wert in den äußeren Bändern. Der Anteil dieser
# Werte ist die eigentliche Kennzahl dieser Ablation.
SATT_UNTEN, SATT_OBEN = 0.05, 0.95

# Gate auf die Vorwärtsrichtung: Ist V selbst schon niedrig, hat das
# Modell den Claim nicht mal aus der Quelle für gestützt gehalten — dann
# sagt ein niedriges `delta` nichts über Ableitung, sondern nur, dass
# beide Richtungen bei praktisch keinem Entailment nah beieinander liegen.
# Ohne dieses Gate zieht ein einzelner Fall mit gescheitertem V die ganze
# Lückenmessung nach unten, ohne dass er zur Frage etwas beiträgt.
V_MIN = 0.70


# ------------------------------------------------------------- Kontrollsatz
# Handgeschriebene Paare (Quelle, Claim, erwartet). „direkt" heißt: gleicher
# Inhalt, andere Worte — die Rückrichtung sollte hoch sein. „inferiert"
# heißt: aus der Quelle ableitbar, aber schwächer/abstrahierend — die
# Rückrichtung sollte einbrechen. Bewusst gleich lang gehalten, damit der
# Unterschied nicht bloß Längenunterschied ist.
KONTROLLE = [
    ("Der Ausschuss entschied sich einstimmig dafür, das Projekt "
     "weiterzuverfolgen.",
     "Das Projekt wird vom Ausschuss einstimmig weiterverfolgt.", "direkt"),
    ("Die Firma Uniq Land GmbH aus München möchte das Rechenzentrum im "
     "Ortsteil Mönkebüll realisieren.",
     "Das Rechenzentrum soll von der Uniq Land GmbH aus München in "
     "Mönkebüll realisiert werden.", "direkt"),
    ("Richard Vogel, Europameister 2025 und Sieger im Großen Preis von "
     "Aachen 2026, wird als Topfavorit gehandelt.",
     "Besondere Aufmerksamkeit gilt Richard Vogel.", "inferiert"),
    ("Bei einer Erweiterung kämen noch einmal zwei Gebäude hinzu.",
     "Die Anlage könnte später vergrößert werden.", "inferiert"),
    # Diese beiden Paare übersetzen eine Zahl in ein Werturteil, statt sie
    # nur umzuformulieren. Beim ersten Testlauf scheiterte bei genau
    # dieser Art Fall schon `V` (0,02 bzw. 0,11) — die Richtungsprüfung
    # kam nie zum Zug. Absichtlich im Kontrollsatz belassen, nicht
    # ausgetauscht: Sie zeigen die Grenze des Diskriminators, nicht nur
    # seine Trennschärfe. Siehe `--reichweite` für die Häufigkeit dieses
    # Musters in echten Daten.
    ("Die Anlage wäre mit einer Leistung von 150 Megawatt eine der größten "
     "in Deutschland.",
     "Es handelt sich um ein besonders großes Rechenzentrum.", "inferiert"),
    ("Rund 170 Reiter aus 55 Nationen haben sich für die WM qualifiziert "
     "– so viele wie nie zuvor.",
     "Die Weltmeisterschaft ist so groß wie noch keine zuvor.",
     "inferiert"),
    ("Aber Lippstadt hielt die Null.",
     "Der SV Lippstadt kassierte kein Gegentor.", "direkt"),
    ("Preußen Münster II erreichte gegen den SV Lippstadt ein torloses "
     "0:0-Unentschieden.",
     "Preußen Münster II und der SV Lippstadt trennten sich 0:0.",
     "direkt"),
]


# ------------------------------------------------------------------ Laden

def _lade(pfad: str) -> dict:
    with open(pfad, encoding="utf-8") as f:
        return json.load(f)


def _abdeckung(claim_text: str, quell_texte: list[str],
               alle_saetze: list[str]) -> float:
    """Anteil des Claims, den die Fundstellen erklären.

    Bewusst mit den Pipeline-Funktionen gerechnet, damit die Zahl
    dieselbe Größe misst wie die Notiz im Viewer — asymmetrisch, also
    „wie viel vom Claim", nicht Kosinus.
    """
    tf = lexik.erzeuge_tfidf(alle_saetze + [claim_text])
    ct = lexik._content_tokens(claim_text)
    cg = lexik._content_grams(ct)
    cv = {g: w for g, w in tf.vec(claim_text).items() if g in cg}
    if not cv:
        return 0.0
    quell_gramme: set[str] = set()
    for t in quell_texte:
        quell_gramme |= lexik._content_grams(lexik._content_tokens(t))
    return lexik._covered_weight(cv, quell_gramme)


def _spantext(artikel: str, quelle: dict) -> str:
    """Nur die markierten Evidenzstellen, zu einem Text verkettet."""
    stuecke = [artikel[a:b] for a, b in quelle.get("spans") or []]
    stuecke = [s.strip() for s in stuecke if s.strip()]
    return " ".join(stuecke)


def faelle_aus_lauf(daten: dict, alle: bool,
                    nur_relationen: set[str] | None = None) -> list[dict]:
    """Kandidaten aus einem exportierten Lauf extrahieren.

    `nur_relationen` filtert vor dem Methode-C-Vorfilter auf bestimmte
    Relationen — genutzt von `--reichweite`, das ausschließlich
    `bedeutung_verschoben` sehen will, unabhängig davon, ob Abdeckung
    oder gespeichertes NLI diese Claims sonst durchließen.
    """
    artikel = daten["article"]["text"]
    saetze = {s["id"]: s["text"] for s in daten["article"]["sentences"]}
    alle_texte = list(saetze.values())
    raus: list[dict] = []
    for c in daten["transcript"]["claims"]:
        if nur_relationen is not None and c["relation"] not in nur_relationen:
            continue
        if not c.get("sources"):
            continue
        quell_texte = [saetze[q["sentence"]] for q in c["sources"]
                       if q["sentence"] in saetze]
        if not quell_texte:
            continue
        spans = " ".join(t for t in (_spantext(artikel, q)
                                     for q in c["sources"]) if t)
        cov = _abdeckung(c["text"], quell_texte, alle_texte)
        entail = (c.get("scores") or {}).get("nli")
        if not alle and nur_relationen is None:
            if cov > FILTER["cov_max"]:
                continue
            if entail is None or entail < FILTER["entail_min"]:
                continue
        raus.append({
            "id": c["id"],
            "relation": c["relation"],
            "claim": c["text"],
            "quelle": " ".join(quell_texte),
            "spans": spans or " ".join(quell_texte),
            "spans_echt": bool(spans),
            "lex": (c.get("scores") or {}).get("lex"),
            "cov": cov,
            "entail_lauf": entail,
        })
    return raus


# ------------------------------------------------------------------ Messen

def messen(faelle: list[dict], modell: str, nur_v: bool = False) -> list[dict]:
    """NLI-Richtungen berechnen.

    `nur_v=True` spart zwei Drittel der Aufrufe: Für die Reichweitenfrage
    zählt nur, ob die Vorwärtsrichtung überhaupt trägt — `R_satz`/`R_span`
    wären hier reine Rechenzeit ohne Erkenntnisgewinn.
    """
    if nur_v:
        paare = [(f["quelle"], f["claim"]) for f in faelle]
        for f, v in zip(faelle, nli.classify(paare, modell)):
            f["V"] = v["entailment"]
            f["R_satz"] = f["R_span"] = f["delta"] = None
        return faelle

    paare: list[tuple[str, str]] = []
    for f in faelle:
        paare.append((f["quelle"], f["claim"]))    # V     Quelle -> Claim
        paare.append((f["claim"], f["quelle"]))    # R_satz Claim -> Satz
        paare.append((f["claim"], f["spans"]))     # R_span Claim -> Spans
    ergebnisse = nli.classify(paare, modell)
    for k, f in enumerate(faelle):
        v, rs, rp = ergebnisse[3 * k:3 * k + 3]
        f["V"] = v["entailment"]
        f["R_satz"] = rs["entailment"]
        f["R_span"] = rp["entailment"]
        f["delta"] = f["V"] - f["R_span"]
    return faelle


# ------------------------------------------------------------------ Bericht

def _band(werte: list[float]) -> str:
    if not werte:
        return "—"
    s = sorted(werte)
    med = s[len(s) // 2]
    satt = sum(1 for v in s if v <= SATT_UNTEN or v >= SATT_OBEN)
    return (f"min {s[0]:.2f}  med {med:.2f}  max {s[-1]:.2f}  "
            f"gesättigt {satt}/{len(s)}")


def bericht(faelle: list[dict], kontrolle: bool) -> None:
    if not faelle:
        print("Keine Kandidaten. Mit --alle ohne Vorfilter laufen lassen.")
        return

    kopf = f"{'id':<6}{'relation':<22}{'lex':>6}{'cov':>7}" \
           f"{'V':>7}{'R_satz':>8}{'R_span':>8}{'delta':>8}   Claim"
    print(kopf)
    print("-" * len(kopf))
    for f in faelle:
        lex = f"{f['lex']:.2f}" if f["lex"] is not None else "  — "
        stern = "" if f["spans_echt"] else " *"
        v_flag = "  (V<%.2f, nicht auswertbar)" % V_MIN if f["V"] < V_MIN else ""
        print(f"{f['id']:<6}{f['relation']:<22}{lex:>6}{f['cov']:>7.2f}"
              f"{f['V']:>7.2f}{f['R_satz']:>8.2f}{f['R_span']:>8.2f}"
              f"{f['delta']:>8.2f}   {f['claim'][:46]}{stern}{v_flag}")
    if any(not f["spans_echt"] for f in faelle):
        print("\n* keine Evidenz-Spans vorhanden — R_span gegen den ganzen "
              "Satz gerechnet, der Wert ist dort nicht aussagekräftig.")

    print("\nVerteilung (die eigentliche Frage: sättigt die Rückrichtung?)")
    for name in ("V", "R_satz", "R_span"):
        print(f"  {name:<7} {_band([f[name] for f in faelle])}")

    hoch = [f for f in faelle if f["R_span"] >= SATT_OBEN]
    tief = [f for f in faelle if f["R_span"] <= SATT_UNTEN]
    mitte = len(faelle) - len(hoch) - len(tief)
    print(f"\n  R_span: {len(hoch)} hoch, {mitte} in der Mitte, "
          f"{len(tief)} tief")
    print("  Lesart: Ist die Mitte leer UND fallen die Fälle nicht mit der\n"
          "  Erwartung zusammen, trägt die Rückrichtung kein Signal —\n"
          "  dann auf Methode C zurückfallen (Abdeckung + Entailment).")

    span_besser = sum(1 for f in faelle if f["R_span"] > f["R_satz"] + 0.10)
    print(f"\n  R_span deutlich über R_satz: {span_besser}/{len(faelle)} "
          "— Maß für den Materialüberschuss des ganzen Satzes.")

    auswertbar = [f for f in faelle if f["V"] >= V_MIN]
    verworfen = len(faelle) - len(auswertbar)
    if verworfen:
        print(f"\n  {verworfen} Fall/Fälle mit V < {V_MIN} aus der "
              "Lückenmessung ausgeschlossen: Bei gescheiterter "
              "Vorwärtsrichtung sagt ein niedriges delta nichts über\n"
              "  Ableitung, sondern nur, dass beide Richtungen bei fast "
              "keinem Entailment nah beieinander liegen.")

    if kontrolle:
        print("\nTrennschärfe auf dem Kontrollsatz (nur V >= %.2f)" % V_MIN)
        for erwartet in ("direkt", "inferiert"):
            grp = [f for f in auswertbar if f["relation"] == erwartet]
            verworfen_grp = [f for f in faelle if f["relation"] == erwartet
                             and f["V"] < V_MIN]
            if grp:
                print(f"  {erwartet:<10} R_span {_band([f['R_span'] for f in grp])}"
                      f"  (n={len(grp)})")
                print(f"  {'':<10} delta  {_band([f['delta'] for f in grp])}")
            if verworfen_grp:
                print(f"  {'':<10} + {len(verworfen_grp)} verworfen "
                      f"(V<{V_MIN}): {[f['id'] for f in verworfen_grp]}")
        d_dir = [f["delta"] for f in auswertbar if f["relation"] == "direkt"]
        d_inf = [f["delta"] for f in auswertbar if f["relation"] == "inferiert"]
        if d_dir and d_inf:
            luecke = min(d_inf) - max(d_dir)
            print(f"\n  Lücke zwischen den Gruppen im delta: {luecke:+.2f}"
                  f"  (n={len(d_dir)} direkt, n={len(d_inf)} inferiert)")
            print("  Positiv heißt trennbar — der Schwellenwert läge "
                  "dazwischen.\n  Negativ oder nahe null heißt: nicht "
                  "trennbar, Methode E fällt aus.")
            if min(len(d_dir), len(d_inf)) < 4:
                print("  Bei so kleiner Gruppengröße kann ein einzelner "
                      "Fall die Lücke kippen — als Richtung lesen, nicht\n"
                      "  als Schwellenwert übernehmen.")
        else:
            print("\n  Zu wenige auswertbare Fälle für eine Lückenmessung "
                  "— Kontrollsatz erweitern oder V_MIN senken.")


def bericht_reichweite(faelle: list[dict]) -> None:
    """Wie viele echte `bedeutung_verschoben`-Claims erreicht Methode E?

    Der Kontrollsatz zeigt nur, ob das Modell trennen KANN. Diese
    Auswertung zeigt, wie oft es überhaupt zur Trennung kommt: Nur Claims
    mit V >= V_MIN erreichen die Richtungsprüfung. Alles darunter bleibt
    `bedeutung_verschoben`, ganz gleich, was die Rückrichtung ergeben
    hätte — die Vorwärtsrichtung ist bereits das Nadelöhr.
    """
    if not faelle:
        print("Keine `bedeutung_verschoben`-Claims mit Fundstellen "
              "gefunden — nichts zu messen.")
        return

    kopf = f"{'id':<6}{'V':>6}{'cov':>7}   Claim"
    print(kopf)
    print("-" * len(kopf))
    for f in sorted(faelle, key=lambda f: -f["V"]):
        markiert = "  <- erreicht Stufe E" if f["V"] >= V_MIN else ""
        print(f"{f['id']:<6}{f['V']:>6.2f}{f['cov']:>7.2f}   "
              f"{f['claim'][:50]}{markiert}")

    erreicht = [f for f in faelle if f["V"] >= V_MIN]
    anteil = len(erreicht) / len(faelle)
    print(f"\n  V-Verteilung: {_band([f['V'] for f in faelle])}")
    print(f"  Erreichen Stufe E (V >= {V_MIN}): {len(erreicht)}/{len(faelle)} "
          f"({anteil:.0%})")

    print()
    if anteil >= 0.5:
        print("  Über die Hälfte der Kandidaten erreicht die Richtungs-\n"
              "  prüfung — der Zusatzaufwand deckt einen brauchbaren Teil\n"
              "  der `bedeutung_verschoben`-Fälle ab. Mit dem Ergebnis aus\n"
              "  --kontrolle zusammen lesen: Nur wenn dort die Lücke auch\n"
              "  positiv war, lohnt sich der Einbau.")
    elif anteil >= 0.15:
        print("  Ein kleinerer, aber nicht vernachlässigbarer Teil erreicht\n"
              "  die Prüfung. Methode E würde nur diesen Rand abdecken —\n"
              "  für den Rest bleibt `bedeutung_verschoben` das treffendere\n"
              "  Label, kein Fehler des Diskriminators.")
    else:
        print("  Fast alle Kandidaten scheitern schon an V. Der Grund ist\n"
              "  meist erkennbar an den Claims mit niedrigstem V oben:\n"
              "  Wird dort wiederholt eine Zahl in ein Werturteil übersetzt\n"
              "  (\"150 Megawatt\" -> \"besonders groß\"), ist das ein eigenes\n"
              "  Muster, kein Ausreißer. Methode E lohnt sich hier kaum —\n"
              "  entweder bei Methode C bleiben oder gezielt ein Signal für\n"
              "  Zahl-zu-Werturteil bauen, analog zur Identifier-Prüfung,\n"
              "  nur für Quantität statt Namen.")


# --------------------------------------------------------------------- CLI

def main(argv: list[str]) -> int:
    modell = "nli-mdeberta-2mil7"
    if "--modell" in argv:
        k = argv.index("--modell")
        modell = argv[k + 1]
        del argv[k:k + 2]
    alle = "--alle" in argv
    kontrolle = "--kontrolle" in argv
    reichweite = "--reichweite" in argv
    pfade = [a for a in argv if not a.startswith("--")]

    if reichweite:
        if not pfade:
            print("--reichweite braucht mindestens einen echten Lauf "
                  "(exportierte JSON-Datei) als Argument.")
            return 1
        faelle: list[dict] = []
        for pfad in pfade:
            try:
                neu = faelle_aus_lauf(_lade(pfad), alle=True,
                                      nur_relationen={"bedeutung_verschoben"})
            except (OSError, KeyError, ValueError) as e:
                print(f"[!] {pfad}: {e}", file=sys.stderr)
                continue
            print(f"[{pfad}] {len(neu)} bedeutung_verschoben-Claims mit "
                  "Fundstelle", file=sys.stderr)
            faelle += neu
        if not faelle:
            print("Keine passenden Claims gefunden.")
            return 1
        try:
            messen(faelle, modell, nur_v=True)
        except nli.NliError as e:
            print(f"[!] {e}", file=sys.stderr)
            return 2
        bericht_reichweite(faelle)
        return 0

    faelle = []
    if kontrolle:
        for i, (q, c, erwartet) in enumerate(KONTROLLE, 1):
            faelle.append({"id": f"k{i}", "relation": erwartet, "claim": c,
                           "quelle": q, "spans": q, "spans_echt": True,
                           "lex": None, "cov": 0.0, "entail_lauf": None})
    for pfad in pfade:
        try:
            neu = faelle_aus_lauf(_lade(pfad), alle)
        except (OSError, KeyError, ValueError) as e:
            print(f"[!] {pfad}: {e}", file=sys.stderr)
            continue
        print(f"[{pfad}] {len(neu)} Kandidaten", file=sys.stderr)
        faelle += neu

    if not faelle:
        print(__doc__.strip().split("\n\n")[-1])
        return 1
    try:
        messen(faelle, modell)
    except nli.NliError as e:
        print(f"[!] {e}", file=sys.stderr)
        return 2
    bericht(faelle, kontrolle)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
