#!/usr/bin/env python3
"""Génère les flows d'exemple (JSON importables dans Flowise > Agentflows > Load).

Les nœuds Start et Direct Reply viennent d'un export réel de Flowise 3.1.3 (examples/templates/).
Le nœud Hermes Task est décrit ici d'après nodes/src/nodes/agentflow/HermesTask/HermesTask.ts.
Usage : python3 examples/build_examples.py
"""

import copy
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
COLOR_START, COLOR_TASK, COLOR_REPLY = "#7EE787", "#6C4BD6", "#4DDBBB"
TASK_ID = "hermesTaskAgentflow_0"
NODE_DIR = "/usr/local/lib/node_modules/flowise/node_modules/flowise-components/dist/nodes/agentflow"


def template(name):
    with open(os.path.join(HERE, "templates", name + ".json"), encoding="utf-8") as f:
        return json.load(f)


def task_node(prompt, instructions, x, y):
    def param(label, name, type_, **extra):
        return {"label": label, "name": name, "type": type_, **extra, "id": f"{TASK_ID}-input-{name}-{type_}", "display": True}

    params = [
        {"label": "Hermes API", "name": "credential", "type": "credential", "credentialNames": ["hermesApi"], "id": f"{TASK_ID}-input-credential-credential", "display": True},
        param("Tâche", "hermesPrompt", "string", rows=4, acceptVariable=True, placeholder="Résume les actualités du jour sur {{ question }}"),
        param("Instructions (système)", "hermesInstructions", "string", rows=3, acceptVariable=True, optional=True, additionalParams=True),
        param("ID de session", "hermesSessionId", "string", acceptVariable=True, optional=True, additionalParams=True,
              description="Envoyé dans X-Hermes-Session-Id pour réutiliser une session Hermes."),
        param("Délai maximal (secondes)", "hermesTimeout", "number", default=300, optional=True, additionalParams=True),
    ]
    return {
        "id": TASK_ID, "position": {"x": x, "y": y}, "type": "agentFlow", "width": 200, "height": 66, "selected": False,
        "positionAbsolute": {"x": x, "y": y},
        "data": {
            "label": "Hermes Task 0", "name": "hermesTaskAgentflow", "version": 1, "type": "HermesTask",
            "icon": f"{NODE_DIR}/HermesTask/hermes.svg", "category": "Agent Flows",
            "description": "Envoie une tâche à Hermes Agent et renvoie sa réponse", "baseClasses": ["HermesTask"], "color": COLOR_TASK,
            "credential": "",  # à sélectionner après l'import
            "inputs": {"hermesPrompt": prompt, "hermesInstructions": instructions, "hermesSessionId": "", "hermesTimeout": 300},
            "filePath": f"{NODE_DIR}/HermesTask/HermesTask.js", "inputAnchors": [], "inputParams": params, "outputs": {},
            "outputAnchors": [{"id": f"{TASK_ID}-output-hermesTaskAgentflow", "label": "Hermes Task", "name": "hermesTaskAgentflow"}],
            "id": TASK_ID, "selected": False,
        },
    }


def edge(source, target, source_color, target_color):
    return {
        "source": source, "sourceHandle": f"{source}-output-{source.rsplit('_', 1)[0]}", "target": target, "targetHandle": target,
        "data": {"sourceColor": source_color, "targetColor": target_color, "isHumanInput": False}, "type": "agentFlow",
        "id": f"{source}-{source}-output-{source.rsplit('_', 1)[0]}-{target}-{target}",
    }


def build(prompt, instructions):
    start, reply = template("start"), template("direct-reply")
    start["position"] = start["positionAbsolute"] = {"x": -204.5, "y": 49.125}
    reply["position"] = reply["positionAbsolute"] = {"x": 330, "y": 49.125}
    reply = copy.deepcopy(reply)
    reply["data"]["inputs"]["directReplyMessage"] = "{{ " + TASK_ID + " }}"
    return {
        "nodes": [start, task_node(prompt, instructions, 40, 49.125), reply],
        "edges": [edge("startAgentflow_0", TASK_ID, COLOR_START, COLOR_TASK), edge(TASK_ID, "directReplyAgentflow_0", COLOR_TASK, COLOR_REPLY)],
        "viewport": {"x": 300, "y": 250, "zoom": 1.2},
    }


DIGEST = build(
    prompt=(
        "Sujet du digest : {{ question }}\n\n"
        "Recherche sur le web les informations les plus importantes des dernières 24 heures sur ce sujet. "
        "Sélectionne 5 à 8 sujets. Pour chacun : un titre court, une phrase de résumé, la source (nom du site). "
        "Termine par une section « À retenir » de deux lignes."
    ),
    instructions=(
        "Tu rédiges un digest quotidien en français, en texte simple (pas de tableau, pas de HTML), "
        "lisible dans Telegram, 3500 caractères maximum. N'invente jamais une information : "
        "si tu n'as pas pu vérifier un fait, ne le mentionne pas."
    ),
)

SURVEILLANCE = build(
    prompt=(
        "Critère à surveiller : {{ question }}\n\n"
        "Vérifie ce critère maintenant, avec une source fiable et récente.\n"
        "- Si le critère est rempli : réponds par une alerte courte (2 à 3 lignes) avec la valeur constatée, le seuil et la source.\n"
        "- Sinon, ou si tu ne peux pas vérifier : réponds exactement NO_ALERT et rien d'autre."
    ),
    instructions=(
        "Tu es un agent de surveillance. Ta réponse est envoyée telle quelle sur Telegram, en français. "
        "Quand le critère n'est pas rempli, ta réponse entière doit être le mot NO_ALERT, sans phrase ni ponctuation."
    ),
)

if __name__ == "__main__":
    for filename, flow in (("01-digest-quotidien.json", DIGEST), ("02-surveillance-bitcoin.json", SURVEILLANCE)):
        with open(os.path.join(HERE, filename), "w", encoding="utf-8") as f:
            json.dump(flow, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print("écrit", filename)
