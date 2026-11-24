"""Étape 0 du chantier IA (docs/ai/PLAN_IA.md §8) : faisabilité de l'inférence locale.

Hors de l'application : interroge un llama-server déjà lancé (API compatible OpenAI) avec
deux outils factices, et vérifie que le modèle répond par des `tool_calls` structurés, puis
qu'il rédige une réponse à partir du résultat des outils. Mesure les temps.

    python scripts/ia/etape0_faisabilite.py [--url http://127.0.0.1:8085] [--label gpu]

Bibliothèque standard seulement. Code de sortie 0 si chaque question a reçu l'appel d'outil
attendu, 1 sinon.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request

TOOLS = [
    {"type": "function", "function": {
        "name": "prix_terminal",
        "description": "Prix d'achat et de vente des commodités d'un terminal Star Citizen.",
        "parameters": {"type": "object", "properties": {
            "terminal": {"type": "string", "description": "Nom ou référence du terminal"},
            "commodite": {"type": "string", "description": "Commodité (facultatif)"}},
            "required": ["terminal"]}}},
    {"type": "function", "function": {
        "name": "itineraire",
        "description": "Itinéraire et distance en Gm entre deux lieux de Star Citizen.",
        "parameters": {"type": "object", "properties": {
            "de": {"type": "string"}, "vers": {"type": "string"}},
            "required": ["de", "vers"]}}},
]

SYSTEM = ("Tu es l'assistant de commerce de uexinfo pour Star Citizen. N'invente jamais un prix, "
          "une quantité ou un lieu : utilise les outils. Réponds court, en français, en citant "
          "la source et l'âge des prix.")

# Question → outil attendu ; résultat factice renvoyé par l'outil
CASES = [
    ("Combien se vend le Laranite à Port Tressler ?", "prix_terminal",
     {"terminal": "terminal:88 Admin - Port Tressler", "commodite": "Laranite",
      "vente": {"v": 3012, "source": "scan", "age_s": 1800}, "achat": None}),
    ("Quelle distance entre Lorville et Area 18 ?", "itineraire",
     {"de": "Lorville", "vers": "Area 18", "distance_gm": 41.2, "etapes": ["Lorville", "ARC-L1", "Area 18"]}),
    ("Je suis à Everus Harbor, quel est le prix de l'Agricium ?", "prix_terminal",
     {"terminal": "terminal:12 Everus Harbor", "commodite": "Agricium",
      "vente": {"v": 2650, "source": "uex", "age_s": 7200}, "achat": {"v": 2420, "source": "uex", "age_s": 7200}}),
]


def chat(url: str, messages: list, tools: list | None, timeout: float = 300) -> tuple[dict, float]:
    """Une requête /v1/chat/completions ; renvoie (réponse JSON, durée en s)."""
    body = {"model": "local", "messages": messages, "temperature": 0.1}
    if tools:
        body["tools"] = tools
    req = urllib.request.Request(f"{url}/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.load(r)
    return data, time.perf_counter() - t0


def arguments(call: dict) -> dict:
    """`function.arguments` : chaîne JSON en principe, parfois déjà un objet (bug connu)."""
    a = call["function"].get("arguments") or {}
    return a if isinstance(a, dict) else json.loads(a)


def speed(data: dict) -> str:
    t = data.get("timings") or {}
    if not t:
        return ""
    return (f"prompt {t.get('prompt_n', 0)} tok à {t.get('prompt_per_second', 0):.0f} tok/s, "
            f"génération {t.get('predicted_n', 0)} tok à {t.get('predicted_per_second', 0):.1f} tok/s")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8085")
    ap.add_argument("--label", default="")
    args = ap.parse_args()

    with urllib.request.urlopen(f"{args.url}/health", timeout=10) as r:
        print(f"[{args.label}] /health : {r.status} {r.read().decode().strip()}")

    ok = 0
    for question, expected, result in CASES:
        messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": question}]
        data, dt = chat(args.url, messages, TOOLS)
        msg = data["choices"][0]["message"]
        calls = msg.get("tool_calls") or []
        print(f"\n[{args.label}] Q : {question}")
        print(f"  1er tour : {dt:.2f} s  {speed(data)}")
        if not calls:
            print(f"  ✗ pas de tool_calls — contenu : {(msg.get('content') or '')[:200]!r}")
            continue
        call = calls[0]
        name, a = call["function"]["name"], arguments(call)
        good = name == expected
        ok += good
        print(f"  {'✓' if good else '✗'} appel : {name}({json.dumps(a, ensure_ascii=False)})"
              f"  [arguments reçus en {type(call['function'].get('arguments')).__name__}]")

        # Second tour : résultat de l'outil → réponse rédigée
        messages += [msg, {"role": "tool", "tool_call_id": call.get("id", "0"),
                           "content": json.dumps(result, ensure_ascii=False)}]
        data, dt = chat(args.url, messages, TOOLS)
        answer = data["choices"][0]["message"].get("content") or ""
        print(f"  2e tour : {dt:.2f} s  {speed(data)}")
        print(f"  réponse : {answer.strip()[:300]}")

    print(f"\n[{args.label}] {ok}/{len(CASES)} appels d'outil attendus")
    return 0 if ok == len(CASES) else 1


if __name__ == "__main__":
    sys.exit(main())
