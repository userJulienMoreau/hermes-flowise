"""Déclenche un flow Flowise depuis une tâche cron Hermes sans LLM (« hermes cron create --no-agent --script »).

Hermes exécute le script à l'heure prévue et livre sa sortie standard (Telegram, Slack...). Règles de Hermes :
  - sortie vide        -> exécution silencieuse (rien n'est envoyé) ;
  - code de sortie != 0 -> alerte d'erreur livrée.
Ce module ajoute : si la réponse du flow commence par « NO_ALERT » (ou est vide), la sortie est vide -> pas de message.
Les guillemets, astérisques et ponctuation autour du mot sont ignorés (les petits modèles en ajoutent souvent).
Bibliothèque standard uniquement (le script tourne dans l'environnement Python de Hermes).

Utilisation : copier flowise_trigger.example.py sous un autre nom et y mettre l'ID du flow.
La question envoyée au flow (sujet, critère...) est le **prompt du job Hermes** qui lance le script : une seule source de
vérité, modifiable depuis Telegram, le tableau de bord ou la CLI sans toucher au fichier. Le script retrouve son job
par son nom de fichier via l'API de Hermes (HERMES_JOBS_API_URL, HERMES_JOBS_API_KEY).
"""

import json
import os
import sys
import urllib.error
import urllib.request

SILENT_MARKER = "NO_ALERT"
DEFAULT_URL = "http://flowise:3000"
DEFAULT_TIMEOUT_S = 300
DEFAULT_HERMES_URL = "http://127.0.0.1:8642"


def is_silent(text):
    """Vrai si le texte est vide ou commence par NO_ALERT (hors guillemets, étoiles, ponctuation)."""
    return text.lstrip(" \t\r\n\"'`*_#>-.:").upper().startswith(SILENT_MARKER) or not text.strip()


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
    return "" if is_silent(text) else text


def job_question(script_path, *, base_url=None, api_key=None, timeout=10, opener=None):
    """Prompt du job Hermes qui exécute ce script (retrouvé par le nom du fichier)."""
    base_url = (base_url or os.environ.get("HERMES_JOBS_API_URL") or DEFAULT_HERMES_URL).rstrip("/")
    api_key = api_key if api_key is not None else os.environ.get("HERMES_JOBS_API_KEY", "")
    script = os.path.basename(script_path)
    request = urllib.request.Request(f"{base_url}/api/jobs?include_disabled=true", headers={"Authorization": f"Bearer {api_key}"})
    try:
        with (opener or urllib.request.urlopen)(request, timeout=timeout) as response:
            jobs = json.loads(response.read().decode("utf-8", errors="replace")).get("jobs", [])
    except urllib.error.HTTPError as e:
        raise FlowiseError(f"Impossible de lire les jobs Hermes (HTTP {e.code}) : vérifiez HERMES_JOBS_API_KEY.")
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        raise FlowiseError(f"Impossible de lire les jobs Hermes à {base_url} : {getattr(e, 'reason', e)}")

    mine = [j for j in jobs if os.path.basename(j.get("script") or "") == script]
    if not mine:
        raise FlowiseError(f"Aucun job Hermes n'utilise le script « {script} ».")
    if len(mine) > 1:
        raise FlowiseError(f"Plusieurs jobs utilisent « {script} » ({', '.join(j.get('name', j['id']) for j in mine)}) : un script par job.")
    question = (mine[0].get("prompt") or "").strip()
    if not question:
        raise FlowiseError(f"Le job « {mine[0].get('name')} » n'a pas de prompt : il contient la question envoyée au flow (sujet, critère...).")
    return question


def main(flow_id, question=None, **kwargs):
    """Point d'entrée d'un script cron : texte sur stdout, erreur sur stderr avec code 1.

    Sans `question`, elle est lue dans le prompt du job Hermes qui exécute le script.
    """
    try:
        if question is None:
            question = job_question(sys.argv[0])
        text = run_flow(flow_id, question, **kwargs)
    except FlowiseError as e:
        print(f"Erreur Flowise : {e}", file=sys.stderr)
        sys.exit(1)
    if text:
        print(text)
