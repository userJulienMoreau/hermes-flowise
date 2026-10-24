"""Met à jour les nœuds Hermes déjà posés dans les flows Flowise avec la définition actuelle (nouvelles opérations, champs).
À lancer après `docker compose up -d --build` si les nœuds ont évolué, **flows fermés dans l'éditeur** :
  docker compose exec hermes python3 /opt/data/scripts/refresh_nodes.py [--dry-run] [--flow NOM]
Les valeurs saisies sont conservées.
"""

import argparse
import os
import sys

from flow_sync import FlowiseClient, SyncError, _http
from node_refresh import run_refresh


class RefreshClient(FlowiseClient):
    def get_node_definition(self, name):
        return _http("GET", f"{self.base}/api/v1/nodes/{name}", self.key)


parser = argparse.ArgumentParser()
parser.add_argument("--dry-run", action="store_true", help="liste ce qui serait modifié sans rien écrire")
parser.add_argument("--flow", help="ne traiter que ce flow (nom ou identifiant)")
args = parser.parse_args()

key = os.environ.get("FLOWISE_API_KEY", "")
if not key:
    print("Erreur : FLOWISE_API_KEY est vide (Flowise > API Keys, puis .env).", file=sys.stderr)
    sys.exit(1)
try:
    messages = run_refresh(RefreshClient(os.environ.get("FLOWISE_URL", "http://flowise:3000"), key), dry_run=args.dry_run, only=args.flow)
except SyncError as e:
    print(f"Erreur : {e}", file=sys.stderr)
    sys.exit(1)

if messages:
    print(("Simulation — nœuds à mettre à jour" if args.dry_run else "Nœuds mis à jour") + " :\n" + "\n".join(messages))
else:
    print("Tous les nœuds Hermes sont à jour.")
