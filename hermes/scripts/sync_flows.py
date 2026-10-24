"""Synchronise les nœuds « Hermes Schedule » (Synchroniser) des flows Flowise avec les jobs cron de Hermes, dans les deux sens.

Lancé périodiquement par un job Hermes sans LLM (voir README) : la sortie est vide (silence) s'il n'y a rien à signaler,
sinon la liste des changements et conflits est livrée. En manuel :
  docker compose exec hermes python3 /opt/data/scripts/sync_flows.py [--prefer flow|hermes] [--dry-run]
"""

import argparse
import os
import sys

from flow_sync import FlowiseClient, HermesClient, SyncError, load_state, run_sync, save_state

parser = argparse.ArgumentParser()
parser.add_argument("--prefer", choices=("flow", "hermes"), help="qui fait foi en cas de conflit (et au premier lien)")
parser.add_argument("--dry-run", action="store_true", help="n'écrit rien, affiche seulement ce qui serait fait")
args = parser.parse_args()

state_path = os.path.join(os.environ.get("HERMES_HOME", "/opt/data"), "flowise_sync_state.json")
flowise_key = os.environ.get("FLOWISE_API_KEY", "")
if not flowise_key:
    print("Erreur de synchronisation : FLOWISE_API_KEY est vide (créer une clé dans Flowise > API Keys et l'ajouter au .env).", file=sys.stderr)
    sys.exit(1)

try:
    flowise = FlowiseClient(os.environ.get("FLOWISE_URL", "http://flowise:3000"), flowise_key)
    hermes = HermesClient(os.environ.get("HERMES_JOBS_API_URL", "http://127.0.0.1:8642"), os.environ.get("HERMES_JOBS_API_KEY", ""))
    if args.dry_run:
        class ReadOnly:
            def __init__(self, inner):
                self.inner = inner
            def __getattr__(self, name):
                if name in ("update_flow", "patch_job"):
                    return lambda *a, **k: {"id": a[0], "flowData": a[1]} if name == "update_flow" else self.inner.get_job(a[0])
                return getattr(self.inner, name)
        flowise, hermes = ReadOnly(flowise), ReadOnly(hermes)
    state = load_state(state_path)
    messages = run_sync(flowise, hermes, state, prefer=args.prefer)
    if not args.dry_run:
        save_state(state_path, state)
except SyncError as e:
    print(f"Erreur de synchronisation Flowise ↔ Hermes : {e}", file=sys.stderr)
    sys.exit(1)

if messages:
    print("Synchronisation Flowise ↔ Hermes" + (" (simulation)" if args.dry_run else "") + " :\n" + "\n".join(messages))
