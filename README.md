# Flowise × Hermes Agent

Éditeur visuel (Flowise) pour piloter Hermes Agent. README complet à venir (étape 6).

## Démarrage rapide (étape 1)

Prérequis : Docker Desktop.

```bash
cp .env.example .env            # puis renseigner les deux clés (openssl rand -hex 32)
docker compose run --rm -it hermes setup   # configuration initiale de Hermes (une fois)
docker compose up -d
curl http://localhost:8642/health          # Hermes
curl http://localhost:3000/api/v1/ping     # Flowise
```

## Connexion de base : Hermes comme modèle dans Flowise (étape 2)

1. Flowise → **Credentials → OpenAI API** : nom `Hermes API`, clé = `API_SERVER_KEY` du `.env`.
2. Nouveau chatflow : **ChatOpenAI Custom** + **Buffer Memory** → **Conversation Chain**.
   - Model Name : `hermes-agent` (le nœud ChatOpenAI standard impose une liste de modèles OpenAI).
   - BasePath : `http://hermes:8642/v1` (nom du service Compose, pas `localhost`).
3. Test dans le chat : « Réponds uniquement : pong » → `pong`.

Hermes configure son fournisseur LLM via `docker compose run --rm -it hermes setup` (ou `... hermes model`).

## Nœud Hermes Task (étape 3)

Les nœuds personnalisés sont dans `nodes/` (TypeScript strict). Flowise ne charge les nœuds que depuis
`flowise-components/dist` : l'image `docker/flowise/Dockerfile` compile `nodes/` et les y copie.

```bash
docker compose up -d --build     # reconstruit l'image Flowise avec les nœuds
cd nodes && npm install && npm test   # tests unitaires (HTTP mocké)
```

Dans Flowise : **Credentials → Hermes API** (URL `http://hermes:8642`, clé = `API_SERVER_KEY`),
puis dans un **Agentflow** : nœud **Hermes Task** (catégorie « Agent Flows »).
Le texte de la réponse est disponible dans `{{ hermesTaskAgentflow_0.output.content }}`.

## Nœud Hermes Schedule (étape 4)

Pilote les tâches planifiées de Hermes via son API (`/api/jobs`). Opérations : **Créer, Lister, Mettre en pause,
Reprendre, Exécuter maintenant, Supprimer**. Une tâche existante se désigne par son identifiant (12 caractères
hexadécimaux) ou par son nom.

| Champ (création) | Exemple |
|---|---|
| Nom (200 car. max) | `Digest quotidien` |
| Planning | `daily at 7am`, `every 1h`, `0 9 * * MON-FRI`, `in 30m`, `2026-03-15T09:00:00` |
| Prompt (5000 car. max) | instruction autonome exécutée par Hermes à chaque déclenchement |
| Livraison | `local` (défaut), `telegram`, `telegram:<chat_id>`, `slack`, `all` |

Sortie : `{{ hermesScheduleAgentflow_0.output.content }}` (texte), `.output.job` / `.output.jobs` (objets).
Les dates affichées par Hermes sont en UTC.
