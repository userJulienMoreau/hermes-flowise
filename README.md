# Flowise × Hermes Agent

Éditeur visuel de scénarios (Flowise) qui pilote [Hermes Agent](https://hermes-agent.nousresearch.com/docs) :
Hermes comme modèle, deux nœuds Flowise dédiés (**Hermes Task**, **Hermes Schedule**) et le déclenchement planifié
de flows Flowise par le planificateur de Hermes, avec livraison Telegram.

```
Planificateur Hermes ──(script, sans LLM)──▶ Flowise (flow) ──▶ nœud Hermes Task ──▶ Hermes (agent + recherche web)
        │                                                                                      │
        └──────────────── livre la sortie (Telegram, Slack…) ◀──────────────────────────────────┘
```

## Installation

Prérequis : Docker Desktop.

```bash
cp .env.example .env     # renseigner API_SERVER_KEY et FLOWISE_SECRETKEY_OVERWRITE (openssl rand -hex 32)
docker compose run --rm -it hermes setup      # une seule fois : fournisseur LLM, etc.
docker compose up -d --build
curl http://localhost:8642/health             # Hermes     -> {"status": "ok", …}
curl http://localhost:3000/api/v1/ping        # Flowise    -> pong
```

- **Flowise** : <http://localhost:3000> (créer le compte administrateur à la première visite).
- **Tableau de bord Hermes** : <http://localhost:9119> — identifiant `HERMES_DASHBOARD_USERNAME` (défaut `admin`) et mot de passe `HERMES_DASHBOARD_PASSWORD` du `.env`.
- API de Hermes : `http://localhost:8642` (sans page web ; `/health` pour tester).

Les ports ne sont exposés que sur `127.0.0.1`.

## Configuration

| Variable (`.env`) | Rôle |
|---|---|
| `HERMES_DASHBOARD_USERNAME` / `HERMES_DASHBOARD_PASSWORD` | Connexion au tableau de bord web de Hermes (mot de passe obligatoire). |
| `API_SERVER_KEY` | Clé Bearer de l'API de Hermes (obligatoire). |
| `FLOWISE_SECRETKEY_OVERWRITE` | Clé de chiffrement des credentials Flowise (obligatoire ; la garder identique d'une installation à l'autre). |
| `FLOWISE_API_KEY` | Optionnelle : clé Flowise utilisée par les scripts cron si vos flows sont protégés. |
| `HERMES_IMAGE_TAG`, `FLOWISE_IMAGE_TAG` | Versions des images. Flowise est épinglé en **3.1.3** : la 3.1.4 (`latest`) plante au démarrage (`this.db.exec is not a function`, module `connect-sqlite3`). |

**Telegram** (pour la livraison) : créer un bot avec @BotFather, relever votre identifiant avec @userinfobot, puis
`docker compose run --rm -it hermes gateway setup` (token, utilisateur autorisé, canal d'accueil) et `docker compose restart hermes`.
N'autorisez que votre propre identifiant : l'agent exécute des commandes dans son conteneur.

**Credential Flowise** : *Credentials → Hermes API* — URL `http://hermes:8642` (nom du service Compose, pas `localhost`),
clé = `API_SERVER_KEY`.

## Utilisation

### Hermes comme modèle (Chatflow)
**ChatOpenAI Custom** (credential *OpenAI API* contenant `API_SERVER_KEY`) : Model Name `hermes-agent`,
BasePath `http://hermes:8642/v1`, puis Buffer Memory → Conversation Chain. Le nœud ChatOpenAI standard impose une liste de modèles OpenAI.

### Nœud Hermes Task (Agentflow)
Envoie une tâche à Hermes et renvoie sa réponse. Champs : Tâche, Instructions, ID de session, Délai (300 s par défaut).
Sortie : `{{ hermesTaskAgentflow_0 }}` (texte) ; le raisonnement et la consommation sont dans `output.reasoning` et `output.usage`.
Un flow Agentflow doit être de la forme **Start → … → Direct Reply** : un nœud isolé donne « Multiple starting nodes are not allowed ».

### Nœud Hermes Schedule (Agentflow)
Pilote les tâches planifiées de Hermes via `/api/jobs` : **Créer, Lister, Mettre en pause, Reprendre, Exécuter maintenant, Supprimer**.
Une tâche existante se désigne par son identifiant (12 caractères hexadécimaux) ou son nom.

| Champ (création) | Exemple |
|---|---|
| Nom (200 car. max) | `Digest quotidien` |
| Planning | `daily at 7am`, `every 1h`, `0 9 * * MON-FRI`, `in 30m`, `2026-03-15T09:00:00` |
| Prompt (5000 car. max) | instruction autonome exécutée par Hermes à chaque déclenchement |
| Livraison | `local` (défaut), `telegram`, `telegram:<chat_id>`, `slack`, `all` |

Opérations de définition :
- **Créer** : refuse si une tâche porte déjà ce nom (pas de doublon en rejouant le flow).
- **Synchroniser** : met à jour la tâche existante (même nom, ou celle désignée par « Tâche existante à mettre à jour » pour un renommage), ou la crée.
  Rejouable sans risque ; **le flow fait alors foi** et écrase les modifications faites côté Hermes (Telegram, tableau de bord).
- **Lire** : renvoie la définition *actuelle* dans Hermes (planning, prompt, livraison, statut) pour l'afficher ou l'utiliser dans le flow :
  c'est l'option où **Hermes fait foi**.

Un nœud ne peut pas être mis à jour automatiquement depuis Hermes : choisir donc, par job, qui fait foi (Synchroniser = le flow, Lire = Hermes).

Hermes planifie en **UTC** : `daily at 7am` = 9 h en heure d'été de Paris.

### Déclencher un flow Flowise à heure fixe
Option retenue : un job Hermes **`--no-agent --script`** (sans LLM, sans jeton) dont le script appelle
`POST /api/v1/prediction/<ID>`. Écartées : job avec prompt (jetons, non déterministe), planificateur natif de Flowise
(l'option « Schedule Input » existe dans le nœud Start de la 3.1.3 mais je n'ai trouvé aucun code de planification côté serveur), cron de l'hôte.

1. Copier `hermes/scripts/flowise_trigger.example.py` sous un autre nom et y mettre l'ID du flow (Flowise → flow → `</>`).
2. Créer le job, dont le **prompt est la question envoyée au flow** (le dossier `hermes/scripts` est monté en lecture seule dans Hermes) :
   ```bash
   docker compose exec hermes hermes cron create "daily at 5am" "intelligence artificielle" --no-agent \
       --script digest_quotidien.py --deliver telegram --name "Digest IA"
   ```
3. Tester : `docker compose exec hermes hermes cron run "Digest IA"`.

**Une seule source de vérité** (rien à synchroniser entre Hermes et Flowise) :

| Élément | Défini à un seul endroit |
|---|---|
| Logique, consignes, mise en forme de la réponse | le **flow** Flowise |
| Planning, livraison, activation, pause | le **job** Hermes |
| Sujet / critère (question envoyée au flow) | le **prompt du job** Hermes |

Le script retrouve son job par son nom de fichier (un script = un job) et lit son prompt via l'API de Hermes : changer le sujet
par Telegram (« change le sujet du Digest IA en robotique »), dans le tableau de bord, en CLI (`hermes cron edit`) ou avec le nœud
Hermes Schedule est pris en compte à la prochaine exécution. Modifier le flow dans Flowise l'est aussi, sans toucher au job.

Règles de `flowise_run.py` : la réponse du flow est livrée telle quelle ; si elle est vide ou **commence par `NO_ALERT`**
(guillemets et ponctuation ignorés), rien n'est envoyé ; toute erreur (Flowise arrêté, clé refusée, flow inconnu, délai)
donne le code de sortie 1 et Hermes livre une alerte.
**Limite :** `/api/jobs` ne sait pas créer de tâche « script » (pas de champ `script`) ; elle se crée en CLI. Le nœud
Hermes Schedule peut ensuite la lister, la suspendre, la relancer ou la supprimer. Vos scripts contenant des ID de flows sont ignorés par Git.

## Scénarios d'exemple

Dans `examples/` (régénérables : `python3 examples/build_examples.py`). Import : Agentflows → nouvel Agentflow → ⚙ → *Load Agents*,
puis sélectionner le credential « Hermes API » sur le nœud Hermes Task.

| Fichier | Principe | Prompt du job Hermes (= `{{ question }}`) |
|---|---|---|
| `01-digest-quotidien.json` | Start → **Hermes Task** (recherche web + résumé) → Direct Reply | le sujet : `intelligence artificielle` |
| `02-surveillance-bitcoin.json` | Start → **Hermes Task** (vérifie un critère) → Direct Reply | le critère : `le prix du Bitcoin dépasse 100000 USD` |

La surveillance répond `NO_ALERT` quand le critère n'est pas rempli : rien n'est envoyé. `{{ question }}` étant la question reçue,
un même flow sert à plusieurs sujets ou seuils.

Si l'import échoue : recréer Start → Hermes Task → Direct Reply (message `{{ hermesTaskAgentflow_0 }}`) en copiant les
textes `hermesPrompt` et `hermesInstructions` du JSON.

## Développement et tests

```bash
cd nodes && npm install && npm test          # 65 tests TypeScript (HTTP mocké), compilation stricte : npm run typecheck
python3 -I -m unittest discover -s hermes/tests   # 21 tests du script de déclenchement
```

Structure : `nodes/` (nœuds et credential en TypeScript strict ; `src/nodes/shared/` = client HTTP sans dépendance à Flowise),
`docker/flowise/Dockerfile` (compile les nœuds et les copie dans `flowise-components/dist`), `hermes/scripts/`, `examples/`.

**Pourquoi une image dérivée plutôt qu'un fork :** Flowise ne charge les nœuds que depuis `flowise-components/dist/nodes`
et `dist/credentials` (`NodesPool.ts`, aucune variable pour un autre chemin). Le dépôt reste léger et on met Flowise à jour en changeant le tag.

## Dépannage

| Symptôme | Cause / remède |
|---|---|
| Données Flowise perdues après `up --build` | L'image 3.1.3 tourne en **root** : ses données sont dans `/root/.flowise`, où le volume `flowise_data` est monté. Sauvegarde : `docker compose stop flowise && docker cp flowise:/root/.flowise ./sauvegarde-flowise && docker compose start flowise`. |
| « Credentials could not be decrypted » | `FLOWISE_SECRETKEY_OVERWRITE` a changé. |
| Flowise redémarre en boucle (`this.db.exec is not a function`) | Version 3.1.4 / `latest` : rester sur 3.1.3. |
| « Clé API refusée par Hermes (HTTP 401) » | La clé du credential ≠ `API_SERVER_KEY`. |
| « Hermes est injoignable » | `docker compose ps` ; URL du credential = `http://hermes:8642`. |
| « Multiple starting nodes are not allowed » | Il manque Start (ou un lien) dans l'Agentflow. |
| Une tâche planifiée ne livre rien | Vérifier `last_status` / `last_delivery_error` : `curl -H "Authorization: Bearer $API_SERVER_KEY" localhost:8642/api/jobs`. Sortie vide ou `NO_ALERT` = silence voulu. |
| Script cron « Script not found » juste après sa création | Attendre quelques secondes (synchronisation du dossier monté) et relancer. |
| Le nouveau nœud n'apparaît pas | `docker compose up -d --build` puis recharger la page. |

## Limites connues
- Chaque appel à Hermes consomme ~12 000 tokens de prompt (prompt système et outils) : une surveillance horaire pèse ~290 000 tokens/jour.
- Le paramètre `X-Hermes-Session-Id` (ID de session du nœud Hermes Task) est envoyé mais son effet n'a pas été vérifié.
- L'opération « Exécuter maintenant » de Hermes Schedule et l'import des JSON d'exemple dans l'interface n'ont pas été testés par l'auteur dans l'interface Flowise (les appels sous-jacents l'ont été).
