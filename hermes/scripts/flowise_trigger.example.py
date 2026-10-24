"""Modèle de script cron : copier vers un autre nom (ex. digest_quotidien.py) puis renseigner les deux valeurs.

Création de la tâche (voir README) :
  docker compose exec hermes hermes cron create "daily at 7am" --no-agent \
      --script digest_quotidien.py --deliver telegram --name "Digest quotidien"
"""

from flowise_run import main

FLOW_ID = "COLLER-L-ID-DU-FLOW"  # Flowise > flow > </> (API) : l'ID est dans l'URL /prediction/<ID>
QUESTION = "Donne-moi le digest du jour."

main(FLOW_ID, QUESTION)
