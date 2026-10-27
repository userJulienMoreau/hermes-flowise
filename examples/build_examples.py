#!/usr/bin/env python3
"""Génère les flows d'exemple (JSON importables dans Flowise > Agentflows > Load).

Les nœuds Start et Direct Reply viennent d'un export réel de Flowise 3.1.3 (examples/templates/).
Les gabarits Custom Function, HTTP, Condition et Sticky Note viennent d'un export réel de Flowise 3.1.2
(le flow « veille crypto » de ce dépôt, construit et exécuté). Le nœud Hermes Task est décrit ici
d'après nodes/src/nodes/agentflow/HermesTask/HermesTask.ts.
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


# --------------------------------------------------------------------------- exemple à logique complète

def node_from_template(name, node_id, values, x, y):
    """Instancie un gabarit de examples/templates/ sous un nouvel identifiant de nœud.

    Les identifiants internes (paramètres, ancres) portent l'identifiant du nœud : il faut les
    réécrire, sinon deux instances d'un même type partageraient leurs ancres et le graphe serait ambigu.
    """
    node = copy.deepcopy(template(name))
    old = node["id"]
    node["id"] = node["data"]["id"] = node_id
    node["position"] = node["positionAbsolute"] = {"x": x, "y": y}
    node["data"]["inputs"].update(values)
    for key in ("inputParams", "outputAnchors"):
        for item in node["data"].get(key, []):
            item["id"] = item["id"].replace(old + "-", node_id + "-", 1)
    return node


def reply_node(node_id, message, x, y):
    return node_from_template("direct-reply", node_id, {"directReplyMessage": message}, x, y)


def note_node(node_id, texte, x, y, largeur=420, hauteur=260):
    node = node_from_template("sticky-note", node_id, {"note": texte}, x, y)
    node["width"], node["height"] = largeur, hauteur
    return node


def link(source, target, anchor=None):
    """Liaison entre deux nœuds ; `anchor` nomme la sortie (« 0 » ou « 1 » pour une Condition)."""
    handle = f"{source['id']}-output-{anchor or source['data']['name']}"
    return {"source": source["id"], "sourceHandle": handle, "target": target["id"], "targetHandle": target["id"],
            "data": {"sourceColor": source["data"]["color"], "targetColor": target["data"]["color"], "isHumanInput": False},
            "type": "agentFlow", "id": f"{source['id']}-{handle}-{target['id']}-{target['id']}"}


CODE_PREPARE = """/*
 * Étape 1 — Prépare le critère de veille.
 * Entrée : $question (saisie de départ du flow, variable « question » du nœud Start).
 * Doit renvoyer une chaîne de caractères (ici du JSON).
 */
const brut = ($question == null ? '' : String($question)).trim();
const trouve = brut.match(/(\\d+(?:[.,]\\d+)?)/);
const seuil = trouve ? Number(trouve[1].replace(',', '.')) : 5;
const critere = brut || 'variation sur 24 h des principales cryptomonnaies';
return JSON.stringify({ critere: critere, seuil: seuil });
"""

CODE_ANALYSE = """/*
 * Étape 3 — Analyse la réponse HTTP.
 * Entrées : $reponse (sortie du nœud HTTP), $prep (sortie de l'étape 1).
 * Renvoie un texte lisible, ou '' si rien n'est exploitable (déclenche la branche d'erreur).
 */
let seuil = 5;
try { seuil = Number(JSON.parse(String($prep)).seuil) || 5; } catch (e) {}

let data = null;
const texte = ($reponse == null ? '' : String($reponse)).trim();
try { data = JSON.parse(texte); } catch (e) {
  const i = texte.indexOf('{');
  if (i >= 0) { try { data = JSON.parse(texte.slice(i)); } catch (e2) { data = null; } }
}
if (!data || typeof data !== 'object' || Array.isArray(data)) return '';

const lignes = [];
let forts = 0;
for (const cle of Object.keys(data)) {
  const v = data[cle];
  if (!v || typeof v !== 'object' || v.usd == null) continue;
  const c = Number(v.usd_24h_change);
  if (Math.abs(c) >= seuil) forts += 1;
  lignes.push(cle + ' : ' + v.usd + ' USD (' + (c >= 0 ? '+' : '') + c.toFixed(2) + ' % / 24 h)');
}
if (!lignes.length) return '';
return 'Seuil de veille : ' + seuil + ' %\\nActifs suivis : ' + lignes.length
     + '\\nAu-dessus du seuil : ' + forts + '\\n' + lignes.join('\\n');
"""


def build_veille_crypto():
    """Exemple complet : appel HTTP, deux fonctions JavaScript, deux conditions imbriquées, branche d'erreur.

    Graphe : Start -> préparer -> HTTP (CoinGecko) -> analyser -> « données exploitables ? »
             oui -> Hermes Task (verdict) -> « verdict = ALERTE ? » -> rapport, ou NO_ALERT
             non -> source indisponible
    """
    start = copy.deepcopy(template("start"))
    start["position"] = start["positionAbsolute"] = {"x": 0, "y": 340}

    prepare = node_from_template("custom-function", "customFunctionAgentflow_0", {
        "customFunctionInputVariables": [{"variableName": "question", "variableValue": "{{question}}"}],
        "customFunctionJavascriptFunction": CODE_PREPARE,
    }, 220, 340)
    prepare["data"]["label"] = "1. Préparer le critère"

    http = node_from_template("http", "httpAgentflow_0", {
        "method": "GET", "url": "https://api.coingecko.com/api/v3/simple/price",
        "headers": [{"key": "Accept", "value": "application/json"},
                    {"key": "User-Agent", "value": "flowise-hermes-exemple/1.0"}],
        "queryParams": [{"key": "ids", "value": "bitcoin,ethereum,solana,cardano"},
                        {"key": "vs_currencies", "value": "usd"},
                        {"key": "include_24hr_change", "value": "true"}],
        "bodyType": "json", "body": "", "responseType": "text",
    }, 440, 340)
    http["data"]["label"] = "2. Interroger CoinGecko"

    analyse = node_from_template("custom-function", "customFunctionAgentflow_1", {
        "customFunctionInputVariables": [{"variableName": "reponse", "variableValue": "{{ httpAgentflow_0 }}"},
                                         {"variableName": "prep", "variableValue": "{{ customFunctionAgentflow_0 }}"}],
        "customFunctionJavascriptFunction": CODE_ANALYSE,
    }, 660, 340)
    analyse["data"]["label"] = "3. Analyser la réponse"

    donnees_ok = node_from_template("condition", "conditionAgentflow_0", {
        "conditions": [{"type": "string", "value1": "{{ customFunctionAgentflow_1 }}",
                        "operation": "notEmpty", "value2": ""}],
    }, 880, 340)
    donnees_ok["data"]["label"] = "4. Données exploitables ?"

    verdict = task_node(
        prompt=("Critère de veille demandé : {{question}}\n\n"
                "Données de marché relevées à l'instant :\n{{ customFunctionAgentflow_1 }}\n\n"
                "Analyse ces données au regard du critère.\n"
                "- Si le critère est rempli : commence ta réponse par ALERTE, puis 2 à 3 lignes "
                "avec la valeur constatée, le seuil et la tendance.\n"
                "- Sinon : réponds exactement NO_ALERT et rien d'autre."),
        instructions=("Tu es un agent de veille de marché. Ta réponse part telle quelle sur Telegram, "
                      "en français, en texte simple (pas de tableau, pas de HTML). "
                      "Le mot ALERTE doit être en majuscules et en tête de réponse quand le critère est rempli. "
                      "N'invente aucun chiffre : n'utilise que les données fournies."),
        x=1100, y=200)
    verdict["data"]["label"] = "5. Verdict Hermes"

    alerte = node_from_template("condition", "conditionAgentflow_1", {
        "conditions": [{"type": "string", "value1": "{{ hermesTaskAgentflow_0 }}",
                        "operation": "contains", "value2": "ALERTE"}],
    }, 1320, 200)
    alerte["data"]["label"] = "6. Verdict = ALERTE ?"

    rapport = reply_node("directReplyAgentflow_0", "{{ hermesTaskAgentflow_0 }}", 1540, 80)
    rapport["data"]["label"] = "7a. Alerte"
    silence = reply_node("directReplyAgentflow_1", "NO_ALERT", 1540, 260)
    silence["data"]["label"] = "7b. Silence (NO_ALERT)"
    erreur = reply_node("directReplyAgentflow_2",
                        "Source indisponible : aucune donnée exploitable n'a pu être extraite de la réponse "
                        "HTTP (API CoinGecko injoignable ou réponse inattendue). Vérifier la connectivité "
                        "sortante du conteneur Flowise, puis relancer.", 1100, 520)
    erreur["data"]["label"] = "7c. Source indisponible"

    note_1 = note_node("stickyNoteAgentflow_0",
                       "EXEMPLE — veille de marché à seuil\n\n"
                       "1. « Préparer » lit la saisie et en extrait un seuil en % (défaut 5).\n"
                       "2. « HTTP » interroge l'API publique CoinGecko (aucune clé nécessaire).\n"
                       "3. « Analyser » (Custom Function) parse le JSON et compte les actifs au-dessus du seuil.\n"
                       "4. Si rien d'exploitable -> réponse d'erreur (branche basse).\n"
                       "5. Sinon Hermes analyse les chiffres ; 6. la réponse est testée sur le mot ALERTE.\n"
                       "7. Alerte rédigée, ou « NO_ALERT » (silence, convention de flowise_run.py).",
                       0, 20, hauteur=260)
    note_2 = note_node("stickyNoteAgentflow_1",
                       "À retenir : le nœud « Hermes Task » délègue le raisonnement à Hermes. "
                       "Aucune clé LLM n'est stockée dans Flowise : le seul identifiant est « Hermes API ». "
                       "Un flow qui contient ce nœud est signalé par flowise_list_flows — ne pas le rappeler "
                       "depuis le flow lui-même (boucle).",
                       460, 560, hauteur=150)

    return {
        "nodes": [start, prepare, http, analyse, donnees_ok, verdict, alerte, rapport, silence, erreur, note_1, note_2],
        "edges": [
            link(start, prepare),
            link(prepare, http),
            link(http, analyse),
            link(analyse, donnees_ok),
            link(donnees_ok, verdict, "0"),      # données exploitables
            link(donnees_ok, erreur, "1"),       # rien d'exploitable
            link(verdict, alerte),
            link(alerte, rapport, "0"),          # contient ALERTE
            link(alerte, silence, "1"),          # sinon
        ],
        "viewport": {"x": 200, "y": 200, "zoom": 0.7},
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
    for filename, flow in (("01-digest-quotidien.json", DIGEST),
                           ("02-surveillance-bitcoin.json", SURVEILLANCE),
                           ("03-veille-crypto.json", build_veille_crypto())):
        with open(os.path.join(HERE, filename), "w", encoding="utf-8") as f:
            json.dump(flow, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print("écrit", filename)
