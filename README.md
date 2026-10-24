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

## Déclenchement planifié d'un flow Flowise (étape 5)

### Options comparées

| Option | Verdict |
|---|---|
| **Job Hermes `--no-agent --script`** : le planificateur de Hermes exécute un script qui appelle `POST /api/v1/prediction/<id>` ; la sortie est livrée (Telegram, Slack...) | **Retenue.** Sans LLM ni jeton consommé, déterministe, silencieux si le script n'affiche rien, alerte automatique en cas d'erreur. |
| Job Hermes avec prompt (l'agent appelle l'API) | Consomme des jetons à chaque tick, résultat non déterministe. |
| Planificateur natif de Flowise (nœud Start → « Schedule Input ») | L'option existe dans l'éditeur de la 3.1.3, mais je n'ai trouvé aucun code de planification côté serveur dans cette version : non fiable, non testé. |
| Cron de l'hôte | Un composant de plus à maintenir. |

### Mise en place

1. Dans Flowise, ouvrir le flow → `</>` : l'ID est dans l'URL `/api/v1/prediction/<ID>`.
2. Copier le modèle et le renseigner (ID du flow et question) :
   ```bash
   cp hermes/scripts/flowise_trigger.example.py hermes/scripts/digest_quotidien.py
   ```
3. Créer la tâche (le dossier `hermes/scripts` est monté dans Hermes en lecture seule) :
   ```bash
   docker compose exec hermes hermes cron create "daily at 7am" --no-agent \
       --script digest_quotidien.py --deliver telegram --name "Digest quotidien"
   ```
4. Tester tout de suite : `docker compose exec hermes hermes cron run "Digest quotidien"`.

Règles du script (`hermes/scripts/flowise_run.py`) : la réponse du flow est livrée telle quelle ;
si le flow répond **`NO_ALERT`** (ou vide), rien n'est envoyé ; une erreur (Flowise arrêté, clé refusée, flow inconnu)
donne un code de sortie 1 et Hermes livre une alerte. Variables : `FLOWISE_URL` (défaut `http://flowise:3000`),
`FLOWISE_API_KEY` (optionnelle, clé créée dans Flowise > API Keys).

**Limite :** l'API de Hermes (`/api/jobs`) ne permet pas de créer une tâche « script ». Elle se crée en CLI ;
le nœud **Hermes Schedule** peut ensuite la lister, la mettre en pause, la reprendre, l'exécuter ou la supprimer.

Tests du script : `python3 -I -m unittest discover -s hermes/tests`.

## Dépannage : données Flowise perdues après un `docker compose up --build`

L'image Flowise 3.1.3 tourne en **root** : ses données (base SQLite, clés API, credentials, flows) sont dans
`/root/.flowise`. Le volume `flowise_data` doit être monté **là** (c'est le cas dans `docker-compose.yml`).
Monté sur `/home/node/.flowise`, il restait vide et les données disparaissaient à chaque recréation du conteneur.

Sauvegarde manuelle :
```bash
docker compose stop flowise && docker cp flowise:/root/.flowise ./sauvegarde-flowise && docker compose start flowise
```
Garder `FLOWISE_SECRETKEY_OVERWRITE` identique d'une installation à l'autre, sinon les credentials ne se déchiffrent plus.

## Scénarios d'exemple (étape 6)

Les flows sont dans `examples/` (régénérables avec `python3 examples/build_examples.py`).

| Fichier | Principe | Question passée par le script cron |
|---|---|---|
| `01-digest-quotidien.json` | Start → **Hermes Task** (recherche web + résumé) → Direct Reply | le sujet : `intelligence artificielle` |
| `02-surveillance-bitcoin.json` | Start → **Hermes Task** (vérifie un critère) → Direct Reply | le critère : `le prix du Bitcoin dépasse 100000 USD` |

Dans les deux flows, `{{ question }}` est la question reçue ; le même flow sert donc à plusieurs sujets ou seuils.
La surveillance répond **`NO_ALERT`** quand le critère n'est pas rempli : le script cron n'envoie alors rien.

**Import :** Agentflows → nouvel Agentflow → ⚙ → *Load Agents* → choisir le JSON, puis sélectionner le credential « Hermes API »
sur le nœud Hermes Task et enregistrer. Si l'import échoue, recréer Start → Hermes Task → Direct Reply à la main :
le texte du champ « Tâche » et des « Instructions » est dans le JSON (clés `hermesPrompt` et `hermesInstructions`) ;
Direct Reply affiche `{{ hermesTaskAgentflow_0 }}`.

**Planification :** pour chaque flow, copier le modèle de script (ID du flow + question), puis :
```bash
docker compose exec hermes hermes cron create "daily at 7am" --no-agent \
    --script digest_quotidien.py --deliver telegram --name "Digest IA"
docker compose exec hermes hermes cron create "every 1h" --no-agent \
    --script surveillance_bitcoin.py --deliver telegram --name "Surveillance Bitcoin"
```
(`hermes/scripts/*.py` hors `flowise_run.py` et le modèle sont à créer par vous : ils contiennent l'ID de **votre** flow.)
