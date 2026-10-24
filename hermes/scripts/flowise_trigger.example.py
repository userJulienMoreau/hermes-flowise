"""Modèle de script cron : copier vers un autre nom (ex. digest_quotidien.py) puis renseigner l'ID du flow.

La question envoyée au flow (sujet, critère...) est le PROMPT du job Hermes : on la fixe à la création et on la modifie
côté Hermes (Telegram, tableau de bord, CLI). Un script = un job.

  docker compose exec hermes hermes cron create "daily at 5am" "intelligence artificielle" --no-agent \\
      --script digest_quotidien.py --deliver telegram --name "Digest IA"
"""

from flowise_run import main

FLOW_ID = "COLLER-L-ID-DU-FLOW"  # Flowise > flow > </> (API) : l'ID est dans l'URL /prediction/<ID>

main(FLOW_ID)
