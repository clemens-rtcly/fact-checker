"""
Alignment Lab — lokaler Server, nur Python-Standardbibliothek.

Start:      python3 app.py            (Standard: http://127.0.0.1:8765)
Optionen:   python3 app.py 8080       anderer Port
            python3 app.py 8080 0.0.0.0   im Netz erreichbar (Vorsicht)

API-Key: im Formular eintragen (bleibt im Browser/localStorage) oder
         export SAIA_API_KEY=...  vor dem Start.
"""
from __future__ import annotations

import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import saia
from pipeline import align

ROOT = Path(__file__).resolve().parent
INDEX = ROOT / "index.html"


class Handler(BaseHTTPRequestHandler):
    server_version = "AlignmentLab/0.1"

    # ------------------------------------------------------------ Helpers
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def log_message(self, fmt, *args):  # keine Keys/Bodies loggen
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    # ------------------------------------------------------------- Routen
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, INDEX.read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/api/health":
            self._json(200, {"ok": True})
        elif self.path == "/favicon.ico":
            self._send(204, b"", "image/x-icon")
        else:
            self._json(404, {"error": "Nicht gefunden"})

    def _handle_ratelimit(self):
        """Kontingentstand prüfen, ohne eine echte Analyse zu starten.

        SAIA hat keinen eigenen Kontingent-Endpunkt — Verbrauch und Limit
        stehen in den Response-Headern jeder Anfrage. Der Check ist daher
        selbst eine minimale, echte Embedding-Anfrage (ein kurzes Wort);
        ihr Ergebnis wird verworfen, nur die Header zählen.
        """
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, json.JSONDecodeError):
            self._json(400, {"error": "Ungültiger JSON-Body"})
            return
        model = (body.get("model") or "").strip()
        api_key = (body.get("api_key") or "").strip()
        if not model or model in saia.LOCAL_MODELS:
            self._json(400, {"error": "Kontingent gilt nur für SAIA-Modelle."})
            return
        try:
            saia.embed(["Test"], model=model, api_key=api_key, is_query=False)
        except saia.EmbedError as e:
            rl = saia.last_ratelimit()
            if rl:  # z.B. bei 429: Fehler UND Kontingentstand mitgeben
                self._json(200, {"ratelimit": rl, "warning": str(e)})
            else:
                self._json(502, {"error": str(e)})
            return
        self._json(200, {"ratelimit": saia.last_ratelimit()})

    def do_POST(self):
        if self.path == "/api/ratelimit":
            self._handle_ratelimit()
            return
        if self.path != "/api/align":
            self._json(404, {"error": "Nicht gefunden"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, json.JSONDecodeError):
            self._json(400, {"error": "Ungültiger JSON-Body"})
            return

        article = (body.get("article") or "").strip()
        transcript = (body.get("transcript") or "").strip()
        model = (body.get("model") or "").strip()
        api_key = (body.get("api_key") or "").strip()

        if not article or not transcript:
            self._json(400, {"error": "article und transcript werden benötigt"})
            return
        if len(article) > 200_000 or len(transcript) > 200_000:
            self._json(400, {"error": "Eingabe zu groß (max. 200k Zeichen)"})
            return

        counter = {"n": 0}
        embed_fn = None
        if model:
            def embed_fn(texts, is_query):
                counter["n"] += len(texts)
                return saia.embed(texts, model=model, api_key=api_key,
                                  is_query=is_query)

        t0 = time.time()
        try:
            result = align(article, transcript, embed_fn=embed_fn,
                           model_label=model or "ohne Embeddings")
        except saia.EmbedError as e:
            prefix = "Lokales Modell: " if model in saia.LOCAL_MODELS else ""
            self._json(502, {"error": f"{prefix}{e}"})
            return
        except Exception as e:  # Pipelinefehler sichtbar machen
            self._json(500, {"error": f"Pipeline-Fehler: {e!r}"})
            return

        result["meta"]["statistik"] = {
            "saetze": len(result["article"]["sentences"]),
            "claims": len(result["transcript"]["claims"]),
            "embeddings": counter["n"],
            "dauer_s": round(time.time() - t0, 1),
        }
        if model and model not in saia.LOCAL_MODELS:
            result["meta"]["ratelimit"] = saia.last_ratelimit()
        self._json(200, result)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    host = sys.argv[2] if len(sys.argv) > 2 else "127.0.0.1"
    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"Alignment Lab läuft auf http://{host}:{port}  (Strg+C beendet)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
