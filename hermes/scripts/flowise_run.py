"""Déclenche un flow Flowise depuis une tâche cron Hermes sans LLM (« hermes cron create --no-agent --script »).

Hermes exécute le script à l'heure prévue et livre sa sortie standard (Telegram, Slack...). Règles de Hermes :
  - sortie vide        -> exécution silencieuse (rien n'est envoyé) ;
  - code de sortie != 0 -> alerte d'erreur livrée.
Ce module ajoute : si le flow répond « NO_ALERT » (ou rien), la sortie est vide -> pas de message.
Bibliothèque standard uniquement (le script tourne dans l'environnement Python de Hermes).

Utilisation : copier flowise_trigger.example.py sous un autre nom, y mettre l'ID du flow et la question.
"""

import json
import os
import sys
import urllib.error
import urllib.request

SILENT_MARKER = "NO_ALERT"
DEFAULT_URL = "http://flowise:3000"
DEFAULT_TIMEOUT_S = 300


class FlowiseError(Exception):
    """Erreur lisible, affichée dans l'alerte envoyée par Hermes."""


def run_flow(flow_id, question, *, base_url=None, api_key=None, override_config=None, timeout=DEFAULT_TIMEOUT_S, opener=None):
    """Appelle POST /api/v1/prediction/<flow_id> et renvoie le texte de la réponse ('' = silence)."""
    base_url = (base_url or os.environ.get("FLOWISE_URL") or DEFAULT_URL).rstrip("/")
    api_key = api_key if api_key is not None else os.environ.get("FLOWISE_API_KEY", "")
    if not flow_id or flow_id.startswith("COLLER"):
        raise FlowiseError("ID du flow manquant : renseignez-le dans le script (Flowise > flow > </> > URL de l'API).")

    payload = {"question": question, "streaming": False}
    if override_config:
        payload["overrideConfig"] = override_config
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(
        f"{base_url}/api/v1/prediction/{flow_id}", data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
    )

    try:
        with (opener or urllib.request.urlopen)(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:300]
        if e.code in (401, 403):
            raise FlowiseError(f"Flowise a refusé l'accès (HTTP {e.code}) : vérifiez FLOWISE_API_KEY. {detail}")
        if e.code == 404:
            raise FlowiseError(f"Flow introuvable (HTTP 404) : vérifiez l'ID « {flow_id} ». {detail}")
        raise FlowiseError(f"Flowise a répondu HTTP {e.code} : {detail}")
    except urllib.error.URLError as e:
        raise FlowiseError(f"Flowise injoignable à {base_url} ({e.reason}). Le service tourne-t-il ?")
    except TimeoutError:
        raise FlowiseError(f"Flowise n'a pas répondu en {timeout} s.")

    try:
        data = json.loads(body)
    except ValueError:
        raise FlowiseError(f"Réponse de Flowise non JSON : {body[:200]}")
    text = data.get("text") if isinstance(data, dict) else None
    if not isinstance(text, str):
        raise FlowiseError(f"Réponse de Flowise sans champ « text » : {body[:200]}")

    text = text.strip()
    return "" if text.upper() == SILENT_MARKER else text


def main(flow_id, question, **kwargs):
    """Point d'entrée d'un script cron : texte sur stdout, erreur sur stderr avec code 1."""
    try:
        text = run_flow(flow_id, question, **kwargs)
    except FlowiseError as e:
        print(f"Erreur Flowise : {e}", file=sys.stderr)
        sys.exit(1)
    if text:
        print(text)
