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

_BATCH = 8            # Paare je Vorwärtsdurchlauf; RAM-schonend auf i5/16 GB
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
        torch.set_num_threads(max(1, (os.cpu_count() or 4) // 2))
        cache_dir = os.environ.get("ALIGNMENT_LAB_MODELS") or None
        print(f"[nli] lade {repo} … (beim ersten Mal wird das Modell "
              f"heruntergeladen)", flush=True)
        try:
            tok = AutoTokenizer.from_pretrained(repo, cache_dir=cache_dir)
            mdl = AutoModelForSequenceClassification.from_pretrained(
                repo, cache_dir=cache_dir)
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
    """
    if not pairs:
        return []
    tok, mdl, (ei, ni, ci) = load_nli(model)
    import torch
    out: list[dict] = []
    try:
        for k in range(0, len(pairs), _BATCH):
            chunk = pairs[k:k + _BATCH]
            enc = tok([p for p, _h in chunk], [h for _p, h in chunk],
                      return_tensors="pt", padding=True,
                      truncation="only_first", max_length=_MAX_LEN)
            with torch.no_grad():
                logits = mdl(**enc).logits
            probs = torch.softmax(logits, dim=-1)
            for row in probs:
                out.append({"entailment": float(row[ei]),
                            "neutral": float(row[ni]),
                            "contradiction": float(row[ci])})
    except NliError:
        raise
    except Exception as e:
        raise NliError(f"NLI-Berechnung fehlgeschlagen: {e}") from None
    return out


if __name__ == "__main__":          # Schnelltest:  python3 nli.py [modell]
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
