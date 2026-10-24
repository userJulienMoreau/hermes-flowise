import copy
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import node_refresh as nr  # noqa: E402

OPS_NEW = [{"label": "Créer", "name": "create"}, {"label": "Synchroniser", "name": "sync"}, {"label": "Lister", "name": "list"}]
OPS_OLD = [{"label": "Créer", "name": "create"}, {"label": "Lister", "name": "list"}]

DEFINITION = {
    "name": "hermesScheduleAgentflow", "version": 1, "description": "nouvelle description", "color": "#6C4BD6",
    "credential": {"label": "Hermes API", "name": "credential", "type": "credential", "credentialNames": ["hermesApi"]},
    "inputs": [
        {"label": "Opération", "name": "hermesOperation", "type": "options", "options": OPS_NEW, "default": "create"},
        {"label": "Nom", "name": "hermesJobName", "type": "string", "show": {"hermesOperation": ["create", "sync"]}},
        {"label": "Tâche existante", "name": "hermesSyncRef", "type": "string", "show": {"hermesOperation": ["sync"]}, "default": ""},
        {"label": "Tâche", "name": "hermesJobRef", "type": "string", "show": {"hermesOperation": ["delete"]}},
    ],
}


def stale_node(node_id="hermesScheduleAgentflow_0", operation="create"):
    params = [
        {"label": "Hermes API", "name": "credential", "type": "credential", "credentialNames": ["hermesApi"], "id": f"{node_id}-input-credential-credential", "display": True},
        {"label": "Opération", "name": "hermesOperation", "type": "options", "options": OPS_OLD, "default": "create", "id": f"{node_id}-input-hermesOperation-options", "display": True},
        {"label": "Nom", "name": "hermesJobName", "type": "string", "show": {"hermesOperation": ["create"]}, "id": f"{node_id}-input-hermesJobName-string", "display": True},
        {"label": "Tâche", "name": "hermesJobRef", "type": "string", "show": {"hermesOperation": ["delete"]}, "id": f"{node_id}-input-hermesJobRef-string", "display": False},
    ]
    return {"id": node_id, "data": {"name": "hermesScheduleAgentflow", "label": "Hermes Schedule 0", "description": "ancienne", "credential": "cred-uuid",
            "inputs": {"hermesOperation": operation, "hermesJobName": "Limoges actu"}, "inputParams": params}}


class FakeFlowise:
    def __init__(self, *flows):
        self.flows = {f["id"]: f for f in flows}
        self.updates = []

    def list_flows(self):
        return [dict(f) for f in self.flows.values()]

    def get_flow(self, flow_id):
        return dict(self.flows[flow_id])

    def update_flow(self, flow_id, flowdata):
        self.updates.append(flow_id)
        self.flows[flow_id]["flowData"] = flowdata

    def get_node_definition(self, name):
        return copy.deepcopy(DEFINITION)


def flow(nodes, flow_id="f1", name="Limoges actus"):
    return {"id": flow_id, "name": name, "flowData": json.dumps({"nodes": nodes, "edges": []})}


def node_of(fw, flow_id="f1", index=0):
    return json.loads(fw.flows[flow_id]["flowData"])["nodes"][index]


class RefreshTest(unittest.TestCase):
    def test_ajoute_les_operations_et_champs_en_conservant_les_valeurs(self):
        fw = FakeFlowise(flow([stale_node()]))
        msgs = nr.run_refresh(fw)
        self.assertEqual(len(msgs), 1)
        self.assertIn("+hermesSyncRef", msgs[0])
        self.assertIn("options de hermesOperation", msgs[0])
        node = node_of(fw)["data"]
        op = next(p for p in node["inputParams"] if p["name"] == "hermesOperation")
        self.assertEqual([o["name"] for o in op["options"]], ["create", "sync", "list"])
        self.assertEqual(node["inputs"]["hermesJobName"], "Limoges actu")      # valeur conservée
        self.assertEqual(node["inputs"]["hermesOperation"], "create")          # opération choisie conservée
        self.assertEqual(node["credential"], "cred-uuid")                      # credential conservé
        self.assertEqual(node["label"], "Hermes Schedule 0")                   # libellé conservé
        self.assertEqual(node["description"], "nouvelle description")
        self.assertEqual(node["inputs"]["hermesSyncRef"], "")                  # défaut du nouveau champ

    def test_ids_et_affichage(self):
        fw = FakeFlowise(flow([stale_node(operation="sync")]))
        nr.run_refresh(fw)
        params = {p["name"]: p for p in node_of(fw)["data"]["inputParams"]}
        self.assertEqual(params["hermesSyncRef"]["id"], "hermesScheduleAgentflow_0-input-hermesSyncRef-string")
        self.assertTrue(params["hermesSyncRef"]["display"])        # visible en opération « sync »
        self.assertFalse(params["hermesJobRef"]["display"])        # réservé à « delete »

    def test_deja_a_jour_ne_reecrit_rien(self):
        fw = FakeFlowise(flow([stale_node()]))
        nr.run_refresh(fw)
        fw.updates.clear()
        self.assertEqual(nr.run_refresh(fw), [])
        self.assertEqual(fw.updates, [])

    def test_dry_run_n_ecrit_pas(self):
        fw = FakeFlowise(flow([stale_node()]))
        before = fw.flows["f1"]["flowData"]
        msgs = nr.run_refresh(fw, dry_run=True)
        self.assertEqual(len(msgs), 1)
        self.assertEqual((fw.updates, fw.flows["f1"]["flowData"]), ([], before))

    def test_ne_touche_pas_les_autres_noeuds_ni_les_flows_sans_nœud_hermes(self):
        other = {"id": "startAgentflow_0", "data": {"name": "startAgentflow", "inputs": {"a": 1}, "inputParams": [{"name": "a", "type": "string", "id": "x"}]}}
        fw = FakeFlowise(flow([other, stale_node()]), flow([other], flow_id="f2", name="autre"))
        nr.run_refresh(fw)
        self.assertEqual(node_of(fw, "f1", 0), other)
        self.assertEqual(fw.updates, ["f1"])

    def test_option_flow_limite_le_traitement(self):
        fw = FakeFlowise(flow([stale_node()]), flow([stale_node()], flow_id="f2", name="Autre"))
        nr.run_refresh(fw, only="autre")
        self.assertEqual(fw.updates, ["f2"])

    def test_flowdata_invalide_ignore(self):
        fw = FakeFlowise({"id": "x", "name": "cassé", "flowData": "pas du json"})
        self.assertEqual(nr.run_refresh(fw), [])


if __name__ == "__main__":
    unittest.main()
