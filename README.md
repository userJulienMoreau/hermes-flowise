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
