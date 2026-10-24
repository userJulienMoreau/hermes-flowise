"""Synchronisation bidirectionnelle entre les nœuds « Hermes Schedule » (opération Synchroniser) des flows Flowise
et les jobs cron de Hermes. Bibliothèque standard uniquement ; exécutée par sync_flows.py.

Principe : fusion à trois voies. Pour chaque nœud lié à un job, on compare le nœud (F) et le job (H) à l'instantané
de la dernière synchronisation (S) :
    F seul a changé  -> le job est mis à jour       (flow -> Hermes)
    H seul a changé  -> le nœud est mis à jour      (Hermes -> flow)
    les deux         -> conflit : rien n'est écrit, sauf si une préférence est donnée (« flow » ou « hermes »)
Premier passage (pas d'instantané) : Hermes fait foi, car c'est lui qui exécute réellement le job.
Jamais de création ni de suppression : un nœud sans job reste « non lié » (le créer = exécuter le flow).
Champs synchronisés : nom, planning, prompt, livraison.
"""

import html
import json
import os
import re
import urllib.error
import urllib.request

NODE_NAME = "hermesScheduleAgentflow"
FIELDS = ("name", "schedule", "prompt", "deliver")
# champ synchronisé -> clé dans data.inputs du nœud
INPUT_KEYS = {"name": "hermesJobName", "schedule": "hermesJobSchedule", "prompt": "hermesJobPrompt", "deliver": "hermesJobDeliver"}
REF_KEY = "hermesSyncRef"


class SyncError(Exception):
    pass


def plain(value):
    """Texte brut d'un champ Flowise (qui stocke parfois du HTML : <p>…</p>)."""
    if value is None:
        return ""
    text = re.sub(r"</p>\s*<p>|<br\s*/?>", "\n", str(value))
    return html.unescape(re.sub(r"<[^>]+>", "", text)).strip()


def node_values(inputs):
    values = {f: plain(inputs.get(INPUT_KEYS[f])) for f in FIELDS}
    values["deliver"] = values["deliver"] or "local"
    return values


def job_values(job):
    schedule = job.get("schedule")
    if isinstance(schedule, dict):
        schedule = schedule.get("display") or schedule.get("expr") or ""
    return {"name": job.get("name") or "", "schedule": schedule or "", "prompt": job.get("prompt") or "", "deliver": job.get("deliver") or "local"}


def decide(flow, hermes, snapshot, prefer=None):
    """Action à mener : 'none' | 'to_hermes' | 'to_flow' | 'conflict' | 'adopt_hermes' | 'adopt_flow'."""
    if snapshot is None:
        if flow == hermes:
            return "none"
        return "adopt_flow" if prefer == "flow" else "adopt_hermes"
    f_changed, h_changed = flow != snapshot["flow"], hermes != snapshot["hermes"]
    if f_changed and h_changed:
        if prefer == "flow":
            return "to_hermes"
        if prefer == "hermes":
            return "to_flow"
        return "none" if flow == hermes else "conflict"
    if f_changed:
        return "to_hermes"
    if h_changed:
        return "to_flow"
    return "none"


def diff_text(old, new):
    return ", ".join(f"{k} : « {old[k]} » → « {new[k]} »" for k in FIELDS if old[k] != new[k]) or "aucune différence"


def find_nodes(flow):
    """Nœuds Hermes Schedule en opération « Synchroniser » d'un flow (objet Flowise avec flowData en JSON)."""
    try:
        data = json.loads(flow.get("flowData") or "{}")
    except ValueError:
        return None, []
    nodes = [n for n in data.get("nodes", []) if n.get("data", {}).get("name") == NODE_NAME and n["data"].get("inputs", {}).get("hermesOperation") == "sync"]
    return data, nodes


def match_job(jobs, node_inputs, link):
    """Job lié à un nœud : lien mémorisé, puis « Tâche existante » (ID ou nom), puis nom du nœud."""
    if link and link.get("job_id"):
        return next((j for j in jobs if j["id"] == link["job_id"]), None), None
    ref = plain(node_inputs.get(REF_KEY)) or plain(node_inputs.get(INPUT_KEYS["name"]))
    if not ref:
        return None, "nom du job vide"
    found = [j for j in jobs if j["id"] == ref or (j.get("name") or "").lower() == ref.lower()]
    if len(found) > 1:
        return None, f"plusieurs jobs correspondent à « {ref} »"
    return (found[0] if found else None), (None if found else f"aucun job Hermes « {ref} »")


def run_sync(flowise, hermes, state, prefer=None):
    """Passe de synchronisation. Renvoie la liste des messages (vide = rien à signaler) ; `state` est modifié sur place.

    `flowise` : list_flows(), get_flow(id), update_flow(id, flowdata_json)
    `hermes`  : list_jobs(), get_job(id), patch_job(id, fields)
    """
    messages = []
    links = state.setdefault("links", {})
    jobs = hermes.list_jobs()

    for listed in flowise.list_flows():
        data, nodes = find_nodes(listed)
        if not nodes:
            continue
        pending = []  # (node_id, values à écrire dans le nœud, id du job)
        for node in nodes:
            key = f"{listed['id']}:{node['id']}"
            inputs = node["data"]["inputs"]
            where = f"flow « {listed['name']} »"
            link = links.get(key)
            job, problem = match_job(jobs, inputs, link)
            if job is None:
                reason = problem or f"le job lié {link['job_id']} n'existe plus dans Hermes"
                sig = "unlinked:" + reason
                if (link or {}).get("notice") != sig:
                    messages.append(f"⚠ {where} : nœud non lié ({reason}). Renseignez « Tâche existante » ou exécutez le flow pour créer le job.")
                    links[key] = {**(link or {}), "notice": sig}
                continue

            flow_v, hermes_v = node_values(inputs), job_values(job)
            snapshot = link if link and "flow" in link and "hermes" in link else None
            action = decide(flow_v, hermes_v, snapshot, prefer)

            if action == "none":
                links[key] = {"job_id": job["id"], "flow": flow_v, "hermes": hermes_v}
            elif action in ("adopt_hermes", "to_flow"):
                pending.append((node["id"], hermes_v, job["id"], key))
                label = "premier lien, Hermes fait foi" if action == "adopt_hermes" else "modifié dans Hermes"
                messages.append(f"↩ {where}, job « {hermes_v['name']} » ({label}) : {diff_text(flow_v, hermes_v)}")
            elif action in ("adopt_flow", "to_hermes"):
                fields = {f: flow_v[f] for f in FIELDS}
                hermes.patch_job(job["id"], fields)
                fresh = job_values(hermes.get_job(job["id"]))
                links[key] = {"job_id": job["id"], "flow": flow_v, "hermes": fresh}
                label = "premier lien, le flow fait foi" if action == "adopt_flow" else "modifié dans le flow"
                messages.append(f"↪ {where} → job « {flow_v['name']} » ({label}) : {diff_text(hermes_v, flow_v)}")
            else:  # conflit
                sig = "conflict:" + json.dumps([flow_v, hermes_v], sort_keys=True)
                if (link or {}).get("notice") != sig:
                    messages.append(
                        f"⚠ Conflit {where}, job « {hermes_v['name']} » : modifié des deux côtés depuis la dernière synchronisation "
                        f"({diff_text(flow_v, hermes_v)}). Rien n'a été écrit ; relancer avec --prefer flow ou --prefer hermes pour trancher."
                    )
                    links[key] = {**link, "notice": sig}

        if pending:
            # relecture juste avant l'écriture : limite le risque d'écraser une modification faite entre-temps
            fresh_flow = flowise.get_flow(listed["id"])
            fresh_data, fresh_nodes = find_nodes(fresh_flow)
            by_id = {n["id"]: n for n in fresh_nodes}
            for node_id, values, job_id, key in pending:
                node = by_id.get(node_id)
                if node is None:
                    continue
                for f in FIELDS:
                    node["data"]["inputs"][INPUT_KEYS[f]] = values[f]
                node["data"]["inputs"][REF_KEY] = job_id
                links[key] = {"job_id": job_id, "flow": values, "hermes": values_for_snapshot(jobs, job_id, values)}
            flowise.update_flow(listed["id"], json.dumps(fresh_data, ensure_ascii=False))
    return messages


def values_for_snapshot(jobs, job_id, fallback):
    job = next((j for j in jobs if j["id"] == job_id), None)
    return job_values(job) if job else fallback


# --- accès HTTP (stdlib) -------------------------------------------------------------------------------------------------

def _http(method, url, key, body=None, timeout=30):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(url, data=data, method=method, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8", errors="replace") or "null")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:200]
        raise SyncError(f"{method} {url} -> HTTP {e.code} {detail}")
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        raise SyncError(f"{method} {url} impossible : {getattr(e, 'reason', e)}")


class FlowiseClient:
    def __init__(self, base_url, api_key):
        self.base, self.key = base_url.rstrip("/"), api_key

    def list_flows(self):
        return _http("GET", f"{self.base}/api/v1/chatflows", self.key)

    def get_flow(self, flow_id):
        return _http("GET", f"{self.base}/api/v1/chatflows/{flow_id}", self.key)

    def update_flow(self, flow_id, flowdata_json):
        return _http("PUT", f"{self.base}/api/v1/chatflows/{flow_id}", self.key, {"flowData": flowdata_json})


class HermesClient:
    def __init__(self, base_url, api_key):
        self.base, self.key = base_url.rstrip("/"), api_key

    def list_jobs(self):
        return _http("GET", f"{self.base}/api/jobs?include_disabled=true", self.key)["jobs"]

    def get_job(self, job_id):
        return _http("GET", f"{self.base}/api/jobs/{job_id}", self.key)["job"]

    def patch_job(self, job_id, fields):
        return _http("PATCH", f"{self.base}/api/jobs/{job_id}", self.key, fields)["job"]


# --- état ----------------------------------------------------------------------------------------------------------------

def load_state(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(path, state):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)
