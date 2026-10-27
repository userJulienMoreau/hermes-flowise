"""Diagnostic périodique de l'outil Flowise, à brancher sur une tâche planifiée Hermes.

Sortie vide quand tout va bien : aucun message n'est envoyé (convention watchdog de `flowise_run.py`).
En cas de problème — job en pause, en erreur ou en retard, flow cassé — le rapport part tel quel.

Le diagnostic lui-même vit dans l'outil `hermes-tool-flowise` (`server.py --doctor`), pas ici : il est
exposé à la fois en ligne de commande et comme outil MCP `flowise_doctor`, et le dupliquer le ferait diverger.
Ce script n'est qu'un branchement.

  hermes cron create "every monday 8am" "" --no-agent --script flowise_doctor.py \
      --deliver telegram --name "Diagnostic Flowise"

Le rapport peut signaler un job volontairement en pause à chaque passage : ajouter son nom à
FLOWISE_MCP_DOCTOR_IGNORE dans le `env:` du serveur MCP pour l'ignorer.
"""

import os
import subprocess
import sys

HERMES_HOME = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
SERVEUR = os.path.join(HERMES_HOME, "tools", "flowise-mcp", "server.py")


def main():
    """Lance le diagnostic et transmet son code de sortie (un watchdog ne doit pas échouer en silence)."""
    if not os.path.isfile(SERVEUR):
        print(f"Outil Flowise introuvable : {SERVEUR} (installer hermes-tool-flowise).", file=sys.stderr)
        return 1
    return subprocess.call([sys.executable, SERVEUR, "--doctor"])


if __name__ == "__main__":
    sys.exit(main())
