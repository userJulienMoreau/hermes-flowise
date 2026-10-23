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
