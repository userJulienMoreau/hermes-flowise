"""Met à jour, dans les flows Flowise existants, la définition des nœuds Hermes (champs, opérations, aide).

Flowise copie la définition d'un nœud dans le flow au moment où on l'ajoute : après une évolution du nœud
(nouvelle opération, nouveau champ), les flows existants gardent l'ancienne définition. Ce module remplace cette copie par la
définition actuelle du serveur, en **conservant les valeurs saisies**. Bibliothèque standard uniquement.
"""

import json

REFRESHED_NODES = ("hermesTaskAgentflow", "hermesScheduleAgentflow")


def _visible(param, inputs):
    """Réplique simple de show/hide de Flowise : la valeur courante du champ pilote l'affichage."""
    def matches(rule):
        for key, wanted in rule.items():
            current = inputs.get(key)
            wanted = wanted if isinstance(wanted, list) else [wanted]
            if current not in wanted:
                return False
        return True

    show, hide = param.get("show"), param.get("hide")
    if show and not matches(show):
        return False
    if hide and matches(hide):
        return False
    return True


def build_input_params(node_id, definition, inputs):
    params = []
    credential = definition.get("credential")
    if credential:
        params.append({**credential, "id": f"{node_id}-input-credential-credential", "display": True})
    for p in definition.get("inputs", []):
        params.append({**p, "id": f"{node_id}-input-{p['name']}-{p['type']}", "display": _visible(p, inputs)})
    return params


def _strip_display(params):
    return [{k: v for k, v in p.items() if k != "display"} for p in params]


def refresh_node(node, definition):
    """Remplace la définition d'un nœud ; renvoie la liste des champs ajoutés ou retirés (vide = déjà à jour)."""
    data = node["data"]
    inputs = data.setdefault("inputs", {})
    new_params = build_input_params(node["id"], definition, inputs)
    old_names = {p["name"] for p in data.get("inputParams", [])}
    new_names = {p["name"] for p in new_params}

    # valeurs par défaut pour les nouveaux champs, sans toucher aux valeurs existantes
    for p in definition.get("inputs", []):
        if p["name"] not in inputs and "default" in p:
            inputs[p["name"]] = p["default"]

    old_options = {p["name"]: [o["name"] for o in p.get("options", [])] for p in data.get("inputParams", [])}
    new_options = {p["name"]: [o["name"] for o in p.get("options", [])] for p in new_params}
    changes = [f"+{n}" for n in sorted(new_names - old_names)] + [f"-{n}" for n in sorted(old_names - new_names)]
    changes += [f"options de {n}" for n in sorted(new_names & old_names) if old_options.get(n) != new_options.get(n)]

    if _strip_display(data.get("inputParams", [])) != _strip_display(new_params):
        data["inputParams"] = new_params
        changes = changes or ["définition des champs"]
    else:
        for p_old, p_new in zip(data.get("inputParams", []), new_params):  # simple recalcul de l'affichage
            p_old["display"] = p_new["display"]

    for key in ("description", "icon", "filePath", "color", "baseClasses", "version", "category"):
        if key in definition and data.get(key) != definition[key]:
            data[key] = definition[key]
    return changes


def refresh_flow(flow_data, definitions):
    """flow_data : dict du flowData. Renvoie [(id du nœud, [changements])] pour les nœuds modifiés."""
    out = []
    for node in flow_data.get("nodes", []):
        name = node.get("data", {}).get("name")
        if name in definitions:
            changes = refresh_node(node, definitions[name])
            if changes:
                out.append((node["id"], changes))
    return out


def run_refresh(flowise, dry_run=False, only=None):
    """`flowise` : list_flows(), get_flow(id), update_flow(id, flowdata_json), get_node_definition(name)."""
    messages, definitions = [], {}
    for listed in flowise.list_flows():
        if only and only.lower() not in (listed["id"].lower(), listed["name"].lower()):
            continue
        try:
            data = json.loads(listed.get("flowData") or "{}")
        except ValueError:
            continue
        wanted = {n["data"]["name"] for n in data.get("nodes", []) if n.get("data", {}).get("name") in REFRESHED_NODES}
        for name in wanted - definitions.keys():
            definitions[name] = flowise.get_node_definition(name)
        if not wanted:
            continue
        changed = refresh_flow(data, definitions)
        if not changed:
            continue
        if not dry_run:  # relecture juste avant l'écriture, puis application sur la version fraîche
            fresh = flowise.get_flow(listed["id"])
            fresh_data = json.loads(fresh["flowData"])
            changed = refresh_flow(fresh_data, definitions)
            if changed:
                flowise.update_flow(listed["id"], json.dumps(fresh_data, ensure_ascii=False))
        for node_id, changes in changed:
            messages.append(f"flow « {listed['name']} », nœud {node_id} : {', '.join(changes)}")
    return messages
