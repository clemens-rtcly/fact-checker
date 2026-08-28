"""
Varianten durchrechnen, ohne in `pipeline.py` zu greifen.

Jede Variante ist ein benanntes Bündel aus geänderten `CFG`-Werten,
gesetzten `VARIANTE`-Aushängen (beides in konfig.py) und optional
umgestellten `STUFEN`-Schaltern. Sie gilt nur für die Dauer eines Laufs
und wird danach zurückgenommen — auch wenn unterwegs etwas schiefgeht.
Frühere Fassungen ersetzten dafür ganze Modulattribute (`pipeline.TfIdf`);
das übernimmt jetzt der benannte Aushang `tfidf_klasse`. Damit lassen sich
Alternativen gegeneinander messen, statt sie nacheinander in den Code zu
schreiben und hinterher zu vergessen.

    python3 varianten.py --liste
    python3 varianten.py laeufe/voll -o laeufe/exp --nur C_dichte
    python3 varianten.py laeufe/voll -o laeufe/exp        # alle Varianten
    python3 varianten.py laeufe/voll -o laeufe/exp --emb ohne --nli ohne

Schreibt je Variante einen Ordner `<-o>/<name>/`, darunter `basis/` als
unveränderten Vergleichspunkt. Ausgewertet wird alles mit einem Befehl:

    python3 eval.py "gold/*.json" --laeufe laeufe/exp

**Wichtig beim Auswerten:** Alle Varianten hier tauschen Präzision gegen
Recall. F1 versteckt genau diesen Tausch — CIP und CIR einzeln ansehen.
Und immer nur eine Änderung pro Lauf: Bei acht Paaren lässt sich
hinterher nicht mehr auseinanderrechnen, welche gewirkt hat.
"""
from __future__ import annotations

import contextlib
import os
import sys

import batch
import konfig
from kern import lexik


# --------------------------------------------------------------- Bausteine

def dichte_gewinn(faktor: float, boden: float, decke: float):
    """C — kurzer Satz, der viel beiträgt, zählt mehr.

    Der Restbeitrag misst bisher nur, wie viel vom **Claim** ein Satz
    erklärt. Ein kurzer Satz, der genau diesen Teil trägt („Es braucht
    Zeit, ihr Vertrauen wieder aufzubauen."), ist aber stärkere Evidenz
    als ein langer, der dasselbe nebenbei mitliefert — bei ihm ist der
    Beitrag der halbe Satzinhalt, beim langen ein Nebensatz.

    Formt den Beitrag mit dem Verhältnis einer Referenzlänge zur
    tatsächlichen Satzlänge, gedeckelt in beide Richtungen. Der Deckel ist
    nötig, weil sonst Überschriften und Fragmente („Content:", „Der fünfte
    Mann") beliebig leicht hereinkämen — die sind kurz und teilen mit fast
    jedem Claim ein Wort.
    """
    def f(gewinn: float, kandidat: str, claim: str) -> float:
        laenge = max(len(kandidat), 1)
        skala = faktor / laenge
        return gewinn * max(boden, min(decke, skala))
    return f


def max_quellen_nach_laenge(pro_zeichen: int, obergrenze: int):
    """E — lange Claims dürfen mehr Fundstellen haben.

    Ein Vorspann, der den ganzen Artikel zusammenfasst, braucht fünf
    Quellen; drei sind die feste Obergrenze. Kurze Claims behalten die
    drei, damit die Lockerung nicht überall greift.
    """
    def f(claim: str, standard: int) -> int:
        return max(standard, min(obergrenze, len(claim) // pro_zeichen))
    return f


def tfidf_mit_boden(boden: float):
    """D — IDF entwertet wiederholte Eigennamen.

    „Kiel" steht im U-Boot-Artikel viermal, also niedriges IDF-Gewicht,
    also niedriger Restbeitrag für den Satz, der Kiel als Bauort belegt.
    Je häufiger der zentrale Ort eines Textes genannt wird, desto weniger
    kann er eine Fundstelle stützen — für Nachrichtentexte verkehrt herum.

    Hebt die IDF-Werte auf einen Mindestwert an, statt sie gegen null
    laufen zu lassen. Läuft über den Aushang `tfidf_klasse`, weil die
    Gewichtung in der Klasse selbst entsteht — konstruiert wird überall
    nur über `kern.lexik.erzeuge_tfidf`, deshalb greift der Tausch in
    Stufe 1, in der Teilaussagen-Probe und in `_abdeckung` gleichermaßen.
    """
    class TfIdfBoden(lexik.TfIdf):                   # type: ignore[misc]
        def __init__(self, docs):
            super().__init__(docs)
            if hasattr(self, "idf"):
                self.idf = {g: max(boden, v) for g, v in self.idf.items()}

    return TfIdfBoden


def _abdeckung(claim: str, quell_texte: list[str], alle: list[str]) -> float:
    """Anteil des Claims, den die bisherigen Quellen erklären."""
    if not quell_texte:
        return 0.0
    tf = lexik.erzeuge_tfidf(alle + [claim])
    ct = lexik._content_tokens(claim)
    cg = lexik._content_grams(ct)
    cv = {g: w for g, w in tf.vec(claim).items() if g in cg}
    if not cv:
        return 1.0
    gramme: set[str] = set()
    for t in quell_texte:
        gramme |= lexik._content_grams(lexik._content_tokens(t))
    return lexik._covered_weight(cv, gramme)


def identifier_saat(max_je_claim: int = 2, cov_max: float = 1.01):
    """A — unbelegte Identifier ziehen genau eine Fundstelle nach.

    Steht ein Identifier im Claim, aber in keiner der bisherigen Quellen,
    fehlt genau das Stück Beleg, das ihn trägt: „von der SPD" (Munition/t3,
    Restbeitrag 0,031 — ein einziges Trägerwort, unter jeder Schwelle) oder
    „Viktor Contzen" (Zaun/t14, nur in s32 belegt). Beide sind über den
    Wortbeitrag nicht erreichbar und werden es auch nie sein.

    Zwei Begrenzungen, die den Preis klein halten:

    **Eine Quelle je Identifier.** Ein Name, der in acht Sätzen steht,
    darf nicht acht Kandidaten stellen und schon gar nicht alle freien
    Plätze belegen. Gewählt wird unter den Sätzen, die ihn enthalten,
    derjenige mit der höchsten Embedding-Ähnlichkeit zum **ganzen**
    Claim — also der, der thematisch dazugehört, nicht bloß der erste
    Treffer.

    **Höchstens `max_je_claim` Nachzügler.** Sonst kippt ein Claim mit
    vielen Namen die Fundstellenliste.

    Ohne Embeddings (Modus „ohne") fällt die Auswahl auf den Satz mit dem
    geringsten Abstand zu den bestehenden Quellen zurück — schlechter,
    aber nachvollziehbar, und der Vergleich bleibt lauffähig.
    """
    from stufe0 import identifier as ident
    from stufe0 import personen as ner

    def kennungen(text: str) -> list[str]:
        raus = list(ident._codes(text))
        raus += [w for s, _a, _b in ner.persons(text)
                 for w in s.split() if len(w) > 3]
        if ner.backend() == "spacy":
            raus += [s for s, _a, _b, _l in ner.entities(text, ("LOC", "ORG"))]
        # Reihenfolge stabil halten, Dubletten raus
        gesehen, ordentlich = set(), []
        for k in raus:
            if k.lower() not in gesehen:
                gesehen.add(k.lower())
                ordentlich.append(k)
        return ordentlich

    def f(claim, art_texte, srcs, emb_zeile, frei):
        if frei <= 0:
            return []
        # Auslöser: Nur nachziehen, wenn der Claim überhaupt unvollständig
        # belegt ist. Ohne diese Bedingung feuert die Saat auch dort, wo
        # nichts fehlt — der Identifier steht dann zwar nicht wörtlich in
        # der Quelle („der Bundestrainer" statt „Becker"), der Claim ist
        # aber trotzdem vollständig erklärt. Im ersten Messlauf waren
        # genau das acht von neun Zusatzquellen: `direkt -> aggregiert`
        # stieg von 9 auf 17, CIP fiel um 0,097.
        if _abdeckung(claim, [art_texte[si] for si in srcs],
                      art_texte) > cov_max:
            return []
        belegt = " ".join(art_texte[si] for si in srcs).lower()
        neu_dazu: list[int] = []
        for k in kennungen(claim):
            if len(neu_dazu) >= min(frei, max_je_claim):
                break
            kl = k.lower()
            if kl in belegt:
                continue                       # schon durch eine Quelle gedeckt
            treffer = [si for si, t in enumerate(art_texte)
                       if kl in t.lower() and si not in srcs
                       and si not in neu_dazu]
            if not treffer:
                continue
            if emb_zeile:
                bester = max(treffer, key=lambda si: emb_zeile[si])
            else:
                bester = min(treffer,
                             key=lambda si: min((abs(si - x) for x in srcs),
                                                default=si))
            neu_dazu.append(bester)
        return neu_dazu
    return f


# --------------------------------------------------------------- Varianten

VARIANTEN: dict[str, dict] = {
    # Der Basislauf ohne jede Änderung. Läuft absichtlich mit, damit alle
    # Varianten unter identischen Bedingungen entstehen (gleiche
    # Codeversion, gleicher Lauf) und `eval.py --laeufe` einen sauberen
    # Vergleichspunkt im selben Ordnerbaum vorfindet.
    "basis": {
        "was": "unverändert — Vergleichspunkt für alle anderen",
    },
    "C_fern018": {
        "was": "residual_min_fern 0,22 -> 0,18. Fängt Beinahe-Treffer wie "
               "CHIO/t9 (Beitrag 0,195).",
        "cfg": {"residual_min_fern": 0.18},
    },
    # ------------------------------------------------ Positionsprior
    # `w_pos` (0,12) ist die einzige Fusionskomponente ohne Messung: Sie
    # unterstellt, dass Zusammenfassungen der Artikelreihenfolge folgen
    # (pos = 1 - |si/(n-1) - ci/(m-1)|, siehe kern/fusion.py). Wo das
    # Transkript umsortiert, bestraft der Prior systematisch die richtige
    # ferne Quelle zugunsten einer nahen falschen — dieselbe Signatur wie
    # die bekannten Retrieval-Lücken.
    #
    # Die 0,12 werden auf die anderen drei Gewichte verteilt, statt sie
    # ersatzlos zu streichen: Sonst summierte die Fusion nur noch auf
    # 0,88, alle Scores sänken um denselben Faktor und `t_direct`/`t_none`
    # bedeuteten etwas anderes als im Basislauf — die Messung wäre nicht
    # mehr die des Priors, sondern die einer verschobenen Schwelle.
    # (Im Offline-Modus ist die Verteilung folgenlos: dort renormalisiert
    # `fusion.matrix` ohnehin auf die Restsumme.)
    "P_pos_null": {
        "was": "Positionsprior aus (w_pos 0,12 -> 0), Gewicht auf emb/cov/lex "
               "verteilt. Misst erstmals, was der Prior überhaupt trägt.",
        "cfg": {"w_emb": 0.4545, "w_cov": 0.3182, "w_lex": 0.2273,
                "w_pos": 0.0},
    },
    "P_pos_halb": {
        "was": "Positionsprior halbiert (0,12 -> 0,06). Zeigt, ob der Effekt "
               "monoton ist — nur mit P_pos_null zusammen aussagekräftig.",
        "cfg": {"w_emb": 0.4255, "w_cov": 0.2979, "w_lex": 0.2128,
                "w_pos": 0.0638},
    },
    "C_dichte": {
        "was": "Restbeitrag mit der Satzlänge gewichtet: kurze Sätze, die "
               "viel beitragen, zählen mehr (Deckel 0,7–1,6).",
        "hooks": {"gewinn": dichte_gewinn(120.0, 0.7, 1.6)},
    },
    "C_beides": {
        "was": "C_fern018 und C_dichte zusammen — nur laufen lassen, wenn "
               "beide einzeln überzeugt haben.",
        "cfg": {"residual_min_fern": 0.18},
        "hooks": {"gewinn": dichte_gewinn(120.0, 0.7, 1.6)},
    },
    "D_idf_boden": {
        "was": "IDF-Bodenwert 0,8: wiederholte Eigennamen behalten "
               "Belegkraft (Kanada/t14, „Kiel“ viermal im Text).",
        "hooks": {"tfidf_klasse": tfidf_mit_boden(0.8)},
    },
    "D_idf_boden_stark": {
        "was": "IDF-Bodenwert 1,5 — dieselbe Idee, deutlich kräftiger. "
               "Zeigt, ob der Effekt monoton ist oder kippt.",
        "hooks": {"tfidf_klasse": tfidf_mit_boden(1.5)},
    },
    "E_max_quellen": {
        "was": "Fundstellen-Obergrenze nach Claimlänge (ab ~180 Zeichen "
               "vier, ab ~225 fünf). Für Vorspannsätze wie Zaun/t1.",
        "hooks": {"max_quellen": max_quellen_nach_laenge(45, 5)},
    },
    "A_ident_saat": {
        "was": "Unbelegte Identifier ziehen je eine Fundstelle nach, "
               "ausgewählt nach Embedding-Nähe zum Claim (max. 2).",
        "hooks": {"zusatzquellen": identifier_saat(2)},
    },
    "A2_saat_gefiltert": {
        "was": "wie A, aber nur bei Claims mit Abdeckung <= 0,75 — "
               "dort, wo wirklich etwas fehlt.",
        "hooks": {"zusatzquellen": identifier_saat(2, 0.75)},
    },
    "A3_saat_streng": {
        "was": "wie A2, Abdeckung <= 0,60 und nur ein Nachzügler. "
               "Zeigt, ob der Präzisionsverlust mit dem Filter skaliert.",
        "hooks": {"zusatzquellen": identifier_saat(1, 0.60)},
    },
    "K_kandidat": {
        "was": "t_none 0,40 + residual_min_fern 0,18 — die beiden "
               "Varianten, die im dev-Lauf überzeugt haben. Für --test.",
        "cfg": {"t_none": 0.40, "residual_min_fern": 0.18},
    },
    "T_none_040": {
        "was": "t_none 0,44 -> 0,40. Gegenprobe zur Unbelegt-Präzision "
               "von 0,20 — misst, was die Lockerung kostet.",
        "cfg": {"t_none": 0.40},
    },
    "N_entail_035": {
        "was": "nli_entail_min höher/niedriger setzen. ERST laufen lassen, "
               "wenn CIR steht — sonst kompensiert die Schwelle eine "
               "Retrieval-Lücke.",
        "cfg": {"nli_entail_min": 0.35},
    },
}


# ----------------------------------------------------- Raster (generiert)
#
# `residual_min_fern` (0,22) ist an EINEM Paar kalibriert: Dort lagen die
# fehlenden zweiten Quellen im Abstand 1-2, die fälschlich aufgenommenen
# im Abstand 8-20. Der Wert ist plausibel, aber nie über einen Bereich
# gemessen worden — und er sitzt genau vor der Stelle, an der unvollständige
# Verdichtungen später zu `bedeutung_verschoben`-Fehlalarmen werden (die
# NLI-Prämisse enthält dann nicht alle tragenden Sätze).
#
# Erwartung: sinkendes `fern` hebt CIR und senkt CIP. Interessant ist der
# Punkt, an dem CIP schneller fällt als CIR steigt. Faustregel aus
# BEFEHLE.md: gut, solange ΔCIP weniger als ein Drittel von ΔCIR beträgt.
# 0,22 läuft als `basis` mit und wird deshalb hier nicht wiederholt.
for _wert in (0.10, 0.14, 0.18, 0.26, 0.30):
    VARIANTEN[f"R_fern{int(round(_wert * 100)):03d}"] = {
        "was": f"residual_min_fern {_wert:.2f} (Basis 0,22) — Rasterpunkt".replace(".", ","),
        "cfg": {"residual_min_fern": _wert},
    }

# Gegenprobe auf der anderen Seite der Dichotomie: Ist die harte Stufe
# überhaupt gerechtfertigt? Bei `nah` = `fern` verschwindet sie.
VARIANTEN["R_kein_abstand"] = {
    "was": "residual_min_nah auf residual_min_fern gezogen (0,22/0,22) — "
           "prüft, ob die Abstandsdichotomie überhaupt etwas bringt.",
    "cfg": {"residual_min_nah": 0.22},
}
VARIANTEN["R_nah_streng"] = {
    "was": "residual_min_nah 0,10 -> 0,14 bei unverändertem fern. Zeigt, ob "
           "die niedrige Nachbarschaftshürde Scheinbelege einträgt.",
    "cfg": {"residual_min_nah": 0.14},
}


@contextlib.contextmanager
def angewandt(variante: dict):
    """Variante setzen und garantiert wieder zurücknehmen.

    Gepatcht wird ausschließlich in konfig (CFG, VARIANTE, STUFEN) und
    stets in place — pipeline und die Stufenmodule lesen die Dicts zur
    Laufzeit, deshalb wirkt die Änderung überall, ohne dass irgendwo ein
    Modulattribut ersetzt werden müsste.
    """
    cfg_alt = {k: konfig.CFG[k] for k in variante.get("cfg", {})
               if k in konfig.CFG}
    unbekannt = [k for k in variante.get("cfg", {}) if k not in konfig.CFG]
    if unbekannt:
        raise KeyError(f"Unbekannte CFG-Schlüssel: {unbekannt}")
    stufen_alt = {k: konfig.STUFEN[k] for k in variante.get("stufen", {})
                  if k in konfig.STUFEN}
    unbekannt = [k for k in variante.get("stufen", {})
                 if k not in konfig.STUFEN]
    if unbekannt:
        raise KeyError(f"Unbekannte Stufen-Schalter: {unbekannt}")
    hooks_alt = dict(konfig.VARIANTE)
    try:
        konfig.CFG.update(variante.get("cfg", {}))
        konfig.STUFEN.update(variante.get("stufen", {}))
        konfig.VARIANTE.update(variante.get("hooks", {}))
        yield
    finally:
        konfig.CFG.update(cfg_alt)
        konfig.STUFEN.update(stufen_alt)
        konfig.VARIANTE.clear()
        konfig.VARIANTE.update(hooks_alt)


def main(argv: list[str]) -> int:
    if "--liste" in argv:
        print(f"{'Variante':<22}Wirkung")
        for name, v in VARIANTEN.items():
            print(f"{name:<22}{v['was']}")
        return 0

    ziel = None
    nur: list[str] = []
    durchreichen: list[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "-o":
            ziel = argv[i + 1]; i += 2
        elif a == "--nur":
            nur.append(argv[i + 1]); i += 2
        elif a in ("--emb", "--nli"):
            durchreichen += [a, argv[i + 1]]; i += 2
        elif a in ("--neu", "--still"):
            durchreichen.append(a); i += 1
        else:
            i += 1
    quellen = [a for a in argv if not a.startswith("-")
               and a not in (ziel or "",)
               and a not in nur
               and a not in durchreichen]
    if not quellen or not ziel:
        print(__doc__.strip())
        return 1

    namen = nur or list(VARIANTEN)
    unbekannt = [x for x in namen if x not in VARIANTEN]
    if unbekannt:
        print(f"Unbekannte Variante(n): {unbekannt}\nVerfügbar: "
              f"{list(VARIANTEN)}", file=sys.stderr)
        return 1

    fehler = 0
    for name in namen:
        v = VARIANTEN[name]
        ordner = os.path.join(ziel, name)
        print(f"\n=== {name} — {v['was']}\n    -> {ordner}", flush=True)
        try:
            with angewandt(v):
                code = batch.main(quellen + ["-o", ordner] + durchreichen)
            if code:
                fehler += 1
        except Exception as e:                       # noqa: BLE001
            print(f"[!] {name}: {type(e).__name__}: {e}", file=sys.stderr)
            fehler += 1

    print("\nJetzt vergleichen — ein Befehl für alle Ordner:")
    print(f'    python3 eval.py "gold/*.json" --laeufe {ziel}')
    print("\nCIP und CIR getrennt lesen: Alle Varianten tauschen "
          "Präzision gegen Recall,\nund F1 versteckt genau diesen Tausch. "
          "Zweite Kennzahl ist die Fehlalarmzahl\nbei "
          "`bedeutung_verschoben` — sie sollte mit steigendem CIR von "
          "allein sinken.")
    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
