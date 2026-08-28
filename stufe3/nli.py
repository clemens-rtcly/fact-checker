"""
NLI für das Alignment Lab — Stufe 3, lokal auf der CPU.

Ein Cross-Encoder prüft pro Claim: Folgt der Claim aus seinen Fundstellen
(entailment), widerspricht er ihnen (contradiction) oder keins von beidem
(neutral)? Der Neutral-Fall ist der dritte Link-Status „Bedeutung
verschoben": richtige Stelle gefunden, Aussage aber leicht verschoben
(„es könnte" -> „es kam"). In der Penn-Studie (Kambhamettu et al.) betraf
das 18 von 159 Links — gut jeder zehnte.

Warum ein Cross-Encoder und kein weiteres Embedding: Prämisse und
Hypothese gehen GEMEINSAM durch das Netz, jedes Token sieht jedes andere.
Bezüge wie „St. Barbara" <-> „Die Kirche in Pannesheide" werden damit zu
einer normalen Attention-Aufgabe — für einen Bi-Encoder liegen sie
außerhalb des Eingabefensters.

Modellauswahl (Stand der Recherche, Anfang 2026 — kein eindeutiger Sieger,
zwei ernsthafte Kandidaten plus eine Schnellstufe):

  nli-mdeberta-2mil7   MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7
                       279M, XNLI-de 82,4 %. Standard der Faktenprüfungs-
                       Literatur; als einziges der drei auch auf Fever-NLI-
                       und ANLI-Übersetzungen trainiert (evidenznahe Paare).
                       -> Voreinstellung.
  nli-gbert-large      svalabs/gbert-large-zeroshot-nli
                       337M, rein deutsch (GBERT-large), XNLI-de-Test 85,6 %
                       — bester deutscher Rohwert. Trainiert aber nur auf
                       maschinell übersetztem (M)NLI ohne Fever/ANLI.
  nli-minilm-l6        MoritzLaurer/multilingual-MiniLMv2-L6-mnli-xnli
                       ~110M, mehrfach schneller, spürbar schwächer —
                       für Massendurchläufe und Schnelltests.

Neuere Architekturen (ModernBERT/ModernCE, tasksource-NLI) sind bislang
rein englisch; für mmBERT/EuroBERT/ModernGBERT existiert noch kein
etabliertes 3-Klassen-NLI-Finetuning. Ehrliche Erwartung: ~80–85 %
XNLI-Genauigkeit heißt Hilfssignal, kein Orakel.

Einrichten (transformers + torch kommen mit sentence-transformers mit):

    pip install torch --index-url https://download.pytorch.org/whl/cpu
    pip install "sentence-transformers>=3.0" sentencepiece protobuf

sentencepiece/protobuf braucht nur der mDeBERTa-/MiniLM-Tokenizer;
nli-gbert-large läuft auch ohne.
"""
from __future__ import annotations

import os
import threading

# --------------------------------------------------------------- Modelle

# UI-Name -> HuggingFace-Repo
NLI_MODELS = {
    "nli-mdeberta-2mil7":
        "MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7",
    "nli-gbert-large":
        "svalabs/gbert-large-zeroshot-nli",
    "nli-minilm-l6":
        "MoritzLaurer/multilingual-MiniLMv2-L6-mnli-xnli",
}

_BATCH = 4            # Paare je Vorwärtsdurchlauf; RAM-schonend auf i5/16 GB
_MAX_LEN = 512


class NliError(RuntimeError):
    """Fehler im NLI-Backend."""


_cache: dict[str, tuple] = {}
_cache_lock = threading.Lock()


def _label_order(model, tokenizer) -> tuple[int, int, int]:
    """Indizes (entailment, neutral, contradiction) im Logit-Vektor.

    Die Reihenfolge variiert je Checkpoint (roberta-large-mnli:
    [contradiction, neutral, entailment]; mDeBERTa: [entailment, neutral,
    contradiction]). Primär wird deshalb `config.id2label` über die
    Klassennamen gelesen. Tragen die Labels nur „LABEL_0"-Namen, wird
    kalibriert wie in der StepGap-Literatur: eine Identitätsprämisse
    bestimmt die Entailment-Dimension, ein Negationspaar die
    Contradiction-Dimension — der Rest ist neutral.
    """
    id2label = getattr(model.config, "id2label", None) or {}
    by_name: dict[str, int] = {}
    for i, name in id2label.items():
        low = str(name).lower()
        if "entail" in low:
            by_name["e"] = int(i)
        elif "neutral" in low:
            by_name["n"] = int(i)
        elif "contra" in low:
            by_name["c"] = int(i)
    if set(by_name) == {"e", "n", "c"}:
        return by_name["e"], by_name["n"], by_name["c"]

    import torch
    def probe(premise, hypothesis):
        enc = tokenizer(premise, hypothesis, return_tensors="pt",
                        truncation=True, max_length=_MAX_LEN)
        with torch.no_grad():
            return model(**enc).logits[0]

    ent = int(probe("Eine Katze ist ein Tier.",
                    "Eine Katze ist ein Tier.").argmax())
    logits = probe("Der Turm wird verkleidet.",
                   "Der Turm wird nicht verkleidet.")
    rest = [i for i in range(int(logits.shape[-1])) if i != ent]
    con = max(rest, key=lambda i: float(logits[i]))
    neu = next(i for i in rest if i != con)
    return ent, neu, con


def load_nli(model: str):
    """Lädt ein NLI-Modell einmalig und hält es im Prozessspeicher."""
    repo = NLI_MODELS.get(model)
    if repo is None:
        raise NliError(f"Unbekanntes NLI-Modell: {model!r}")
    with _cache_lock:
        if repo in _cache:
            return _cache[repo]
        try:
            import torch
            from transformers import (AutoModelForSequenceClassification,
                                      AutoTokenizer)
        except ImportError:
            raise NliError(
                "transformers/torch fehlen. Installieren mit:\n"
                "  pip install torch --index-url https://download.pytorch.org/whl/cpu\n"
                '  pip install "sentence-transformers>=3.0" sentencepiece protobuf'
            ) from None
        # Wie in stufe2/saia.py: nur die physischen Kerne. Mit 8 statt
        # 4 Threads auf dem i5 gemessen 4898 ms vs. 4565 ms.
        torch.set_num_threads(max(1, (os.cpu_count() or 4) // 2))
        cache_dir = os.environ.get("ALIGNMENT_LAB_MODELS") or None
        print(f"[nli] lade {repo} … (beim ersten Mal wird das Modell "
              f"heruntergeladen)", flush=True)
        try:
            tok = AutoTokenizer.from_pretrained(repo, cache_dir=cache_dir)
            mdl = AutoModelForSequenceClassification.from_pretrained(
                repo, cache_dir=cache_dir)
            # Die Checkpoints liegen als float16 auf der Platte, und
            # transformers behält diesen dtype bei. Auf der CPU gibt es
            # für float16 aber keine Recheneinheit — jedes Matmul laeuft
            # in einer Emulationsschleife (gemessen: ~1 GFLOPS statt ~240).
            # Das kostet hier Faktor 12. float32 rechnet identisch (die
            # Gewichte kommen ohnehin aus float16) und nutzt AVX-512/MKL.
            mdl = mdl.float()
        except ImportError as e:      # meist fehlendes sentencepiece
            raise NliError(
                f"Tokenizer für {repo} braucht ein Zusatzpaket: {e}. "
                "Meist hilft:  pip install sentencepiece protobuf"
            ) from None
        except Exception as e:
            raise NliError(
                f"NLI-Modell {repo} konnte nicht geladen werden: {e}. "
                "Bei fehlendem Netz vorher einmal online laden, danach "
                "läuft es aus dem lokalen Cache."
            ) from None
        mdl.eval()
        order = _label_order(mdl, tok)
        _cache[repo] = (tok, mdl, order)
        print(f"[nli] {repo} bereit (Labelreihenfolge e/n/c = {order})",
              flush=True)
        return _cache[repo]


def classify(pairs: list[tuple[str, str]], model: str) -> list[dict]:
    """NLI-Wahrscheinlichkeiten je (Prämisse, Hypothese)-Paar.

    Rückgabe in Eingabereihenfolge:
        {"entailment": p, "neutral": p, "contradiction": p}

    Gekürzt wird nur die Prämisse (`only_first`) — die Hypothese ist der
    Claim und muss vollständig im Fenster bleiben, sonst beurteilt das
    Modell einen anderen Satz als den, der geprüft werden soll.

    **Gerechnet wird längensortiert.** `padding=True` füllt jeden Batch auf
    sein längstes Paar auf; ein unsortierter Batch rechnet für die kurzen
    Paare also überwiegend Füllzeichen. Auf echten Läufen sind die Paare
    median 131 Token lang, das längste 293.

    Für sich genommen ändert das Sortieren wenig: Ein Dokument liefert
    5-19 Paare, bei `_BATCH = 16` ist das genau ein Batch, und innerhalb
    eines Batches bleibt die Padding-Länge dieselbe (gemessen 1 % auf
    einem i5-1135G7). Die Sortierung ist die *Voraussetzung* dafür, dass
    `_BATCH` kleiner werden kann, ohne dass willkürlich lange und kurze
    Paare zusammenfallen — 16 Paare bei Batch 4 statt Batch 16 kosteten
    gemessen 36-39 % weniger Zeit. Wer `_BATCH` senkt, handelt sich
    allerdings Fließkomma-Rundung in der Größenordnung 1e-6 ein: Läufe
    sind dann nicht mehr byte-identisch zu früheren (die Labels waren in
    allen Messungen gleich).

    Bei unverändertem `_BATCH` sind die Werte exakt dieselben wie ohne
    Sortierung (geprüft: Abweichung 0,0e+00 über 32 reale Paare). Die
    Rückgabe steht wieder in Eingabereihenfolge — darauf verlässt sich
    die Auftragsstelle in stufe3/nachentscheidung.py.

    `sentence-transformers` macht dasselbe beim Einbetten von sich aus
    (`encode` sortiert und dreht zurück); hier fehlt es, weil der
    Tokenizer direkt aufgerufen wird.
    """
    if not pairs:
        return []
    tok, mdl, (ei, ni, ci) = load_nli(model)
    import torch
    # Zeichenlänge als Näherung für die Tokenzahl — billig und für die
    # Sortierung genau genug; auf die exakte Länge kommt es nicht an.
    reihe = sorted(range(len(pairs)),
                   key=lambda i: len(pairs[i][0]) + len(pairs[i][1]))
    out: list[dict] = [None] * len(pairs)          # type: ignore[list-item]
    try:
        for k in range(0, len(reihe), _BATCH):
            idx = reihe[k:k + _BATCH]
            chunk = [pairs[i] for i in idx]
            enc = tok([p for p, _h in chunk], [h for _p, h in chunk],
                      return_tensors="pt", padding=True,
                      truncation="only_first", max_length=_MAX_LEN)
            with torch.inference_mode():
                logits = mdl(**enc).logits
            probs = torch.softmax(logits, dim=-1)
            for i, row in zip(idx, probs):
                out[i] = {"entailment": float(row[ei]),
                          "neutral": float(row[ni]),
                          "contradiction": float(row[ci])}
    except NliError:
        raise
    except Exception as e:
        raise NliError(f"NLI-Berechnung fehlgeschlagen: {e}") from None
    return out

def _geraet() -> str:
    v = os.environ.get("ALIGNMENT_LAB_DEVICE")
    if v:
        return v
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


if __name__ == "__main__":          # Schnelltest:  python nli.py [modell]
    import sys
    name = sys.argv[1] if len(sys.argv) > 1 else "nli-mdeberta-2mil7"
    faelle = [
        # entailment: wörtlich gestützt
        ("Die Stadt investiert 5,3 Millionen Euro in die Sanierung ihrer "
         "Schulen.", "Die Stadt investiert 5,3 Millionen Euro in ihre "
         "Schulen."),
        # neutral: Modalverschiebung — der Fall „Bedeutung verschoben"
        ("Laut Feuerwehr könnte es zu einer Geruchsbelästigung kommen.",
         "Es kam zu einer Geruchsbelästigung."),
        # contradiction
        ("Der Turm wird nicht verkleidet.", "Der Turm wird verkleidet."),
        # test
        ("„Das ist ein wunder Punkt für mich und meine Kollegen aus dem Kreis\", sagt Wolfgang Wahl, Vorsitzender des Dehoga-Kreisverbands Heinsberg. Wolfgang Wahl selbst betreibt das Hotel am Weiher in Erkelenz.", 
         "Wolfgang Wahl, Vorsitzender des Dehoga-Kreisverbands Heinsberg und Betreiber des Hotels am Weiher in Erkelenz, spricht von einem wunden Punkt für sich und seine Kollegen im Kreis.")
    ]
    for probs, (p, h) in zip(classify(faelle, name), faelle):
        lbl = max(probs, key=probs.get)
        print(f"  {lbl:<13} e={probs['entailment']:.2f} "
              f"n={probs['neutral']:.2f} c={probs['contradiction']:.2f}"
              f"  | {h[:56]}")
