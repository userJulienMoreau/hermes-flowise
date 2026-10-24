import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import flow_sync as fs  # noqa: E402


def node(node_id="hermesScheduleAgentflow_0", op="sync", **inputs):
    base = {"hermesOperation": op, "hermesJobName": "<p>Limoges actus</p>", "hermesJobSchedule": "<p>every 1h</p>",
            "hermesJobPrompt": "Infos Limoges", "hermesJobDeliver": "local", "hermesSyncRef": ""}
    base.update(inputs)
    return {"id": node_id, "data": {"name": fs.NODE_NAME, "inputs": base}}


def flow(flow_id="f1", nodes=None, name="Limoges actus"):
    return {"id": flow_id, "name": name, "flowData": json.dumps({"nodes": nodes if nodes is not None else [node()], "edges": []})}


def job(job_id="2fe480e1937a", name="Limoges actus", schedule="every 60m", prompt="Infos Limoges", deliver="local"):
    return {"id": job_id, "name": name, "schedule": {"kind": "interval", "display": schedule}, "prompt": prompt, "deliver": deliver}


class FakeFlowise:
    def __init__(self, *flows):
        self.flows = {f["id"]: f for f in flows}
        self.updates = []

    def list_flows(self):
        return [dict(f) for f in self.flows.values()]

    def get_flow(self, flow_id):
        return dict(self.flows[flow_id])

    def update_flow(self, flow_id, flowdata):
        self.updates.append((flow_id, json.loads(flowdata)))
        self.flows[flow_id] = {**self.flows[flow_id], "flowData": flowdata}


class FakeHermes:
    def __init__(self, *jobs):
        self.jobs = {j["id"]: j for j in jobs}
        self.patches = []

    def list_jobs(self):
        return [dict(j) for j in self.jobs.values()]

    def get_job(self, job_id):
        return dict(self.jobs[job_id])

    def patch_job(self, job_id, fields):
        self.patches.append((job_id, fields))
        j = self.jobs[job_id]
        j.update({k: v for k, v in fields.items() if k in ("name", "prompt", "deliver")})
        if "schedule" in fields:
            j["schedule"] = {"display": fields["schedule"]}  # Hermes renvoie parfois une forme canonique
        return dict(j)


def inputs_of(fl, node_id="hermesScheduleAgentflow_0"):
    data = json.loads(fl["flowData"])
    return next(n for n in data["nodes"] if n["id"] == node_id)["data"]["inputs"]


class PlainTest(unittest.TestCase):
    def test_html_entites_et_paragraphes(self):
        self.assertEqual(fs.plain("<p>Limoges &amp; co</p>"), "Limoges & co")
        self.assertEqual(fs.plain("<p>a</p><p>b</p>"), "a\nb")
        self.assertEqual(fs.plain(None), "")
        self.assertEqual(fs.plain("  texte  "), "texte")


class DecideTest(unittest.TestCase):
    A = {"name": "n", "schedule": "s", "prompt": "p", "deliver": "local"}

    def with_(self, **kw):
        return {**self.A, **kw}

    def test_table(self):
        S = {"flow": self.A, "hermes": self.A}
        cases = [
            (self.A, self.A, S, None, "none"),
            (self.with_(prompt="x"), self.A, S, None, "to_hermes"),
            (self.A, self.with_(prompt="x"), S, None, "to_flow"),
            (self.with_(prompt="x"), self.with_(schedule="y"), S, None, "conflict"),
            (self.with_(prompt="x"), self.with_(prompt="x"), S, None, "none"),  # même valeur des deux côtés
            (self.with_(prompt="x"), self.with_(schedule="y"), S, "flow", "to_hermes"),
            (self.with_(prompt="x"), self.with_(schedule="y"), S, "hermes", "to_flow"),
            (self.with_(prompt="x"), self.A, None, None, "adopt_hermes"),
            (self.with_(prompt="x"), self.A, None, "flow", "adopt_flow"),
            (self.A, self.A, None, None, "none"),
        ]
        for f, h, s, prefer, expected in cases:
            with self.subTest(expected=expected, prefer=prefer):
                self.assertEqual(fs.decide(f, h, s, prefer), expected)


class RunSyncTest(unittest.TestCase):
    def test_premier_lien_hermes_fait_foi_et_ecrit_le_noeud(self):
        fw, hm, state = FakeFlowise(flow()), FakeHermes(job(schedule="0 9 * * 1")), {}
        msgs = fs.run_sync(fw, hm, state)
        self.assertEqual(len(fw.updates), 1)
        inp = inputs_of(fw.flows["f1"])
        self.assertEqual(inp["hermesJobSchedule"], "0 9 * * 1")
        self.assertEqual(inp["hermesSyncRef"], "2fe480e1937a")  # lien stable, survit à un renommage
        self.assertEqual(inp["hermesOperation"], "sync")
        self.assertTrue(any("premier lien" in m and "every 1h" in m and "0 9 * * 1" in m for m in msgs))
        self.assertEqual(hm.patches, [])

    def test_etat_stable_ne_fait_rien_et_ne_dit_rien(self):
        fw, hm, state = FakeFlowise(flow()), FakeHermes(job(schedule="every 1h")), {}
        fs.run_sync(fw, hm, state)  # premier passage : aligne le nœud (planning identique -> peut ne rien écrire)
        fw.updates.clear()
        self.assertEqual(fs.run_sync(fw, hm, state), [])
        self.assertEqual((fw.updates, hm.patches), ([], []))

    def test_modification_cote_flow_met_a_jour_hermes(self):
        fw, hm, state = FakeFlowise(flow()), FakeHermes(job(schedule="every 60m")), {}
        fs.run_sync(fw, hm, state)
        # l'utilisateur édite le nœud dans Flowise
        data = json.loads(fw.flows["f1"]["flowData"])
        data["nodes"][0]["data"]["inputs"]["hermesJobPrompt"] = "<p>Nouveau prompt</p>"
        fw.flows["f1"]["flowData"] = json.dumps(data)
        msgs = fs.run_sync(fw, hm, state)
        self.assertEqual(hm.patches[0][0], "2fe480e1937a")
        self.assertEqual(hm.patches[0][1]["prompt"], "Nouveau prompt")  # HTML retiré
        self.assertTrue(any("modifié dans le flow" in m for m in msgs))
        self.assertEqual(fs.run_sync(fw, hm, state), [])  # stabilisé

    def test_modification_cote_hermes_met_a_jour_le_noeud(self):
        fw, hm, state = FakeFlowise(flow()), FakeHermes(job()), {}
        fs.run_sync(fw, hm, state)
        fw.updates.clear()
        hm.jobs["2fe480e1937a"].update(schedule={"display": "0 9 * * 1"}, name="Limoges hebdo")
        msgs = fs.run_sync(fw, hm, state)
        inp = inputs_of(fw.flows["f1"])
        self.assertEqual((inp["hermesJobSchedule"], inp["hermesJobName"]), ("0 9 * * 1", "Limoges hebdo"))
        self.assertTrue(any("modifié dans Hermes" in m for m in msgs))
        self.assertEqual(fs.run_sync(fw, hm, state), [])

    def test_renommage_cote_hermes_conserve_le_lien(self):
        fw, hm, state = FakeFlowise(flow()), FakeHermes(job()), {}
        fs.run_sync(fw, hm, state)
        hm.jobs["2fe480e1937a"]["name"] = "Autre nom"
        fs.run_sync(fw, hm, state)
        self.assertEqual(inputs_of(fw.flows["f1"])["hermesJobName"], "Autre nom")
        self.assertEqual(len(hm.jobs), 1)  # aucun doublon créé

    def test_conflit_n_ecrit_rien_et_n_est_signale_qu_une_fois(self):
        fw, hm, state = FakeFlowise(flow()), FakeHermes(job()), {}
        fs.run_sync(fw, hm, state)
        data = json.loads(fw.flows["f1"]["flowData"])
        data["nodes"][0]["data"]["inputs"]["hermesJobPrompt"] = "côté flow"
        fw.flows["f1"]["flowData"] = json.dumps(data)
        hm.jobs["2fe480e1937a"]["prompt"] = "côté hermes"
        fw.updates.clear()
        first = fs.run_sync(fw, hm, state)
        self.assertTrue(any("Conflit" in m for m in first))
        self.assertEqual((fw.updates, hm.patches), ([], []))
        self.assertEqual(fs.run_sync(fw, hm, state), [])  # pas de spam toutes les 5 minutes

    def test_conflit_tranche_par_prefer(self):
        for prefer, expect_patch in (("flow", True), ("hermes", False)):
            with self.subTest(prefer=prefer):
                fw, hm, state = FakeFlowise(flow()), FakeHermes(job()), {}
                fs.run_sync(fw, hm, state)
                data = json.loads(fw.flows["f1"]["flowData"])
                data["nodes"][0]["data"]["inputs"]["hermesJobPrompt"] = "côté flow"
                fw.flows["f1"]["flowData"] = json.dumps(data)
                hm.jobs["2fe480e1937a"]["prompt"] = "côté hermes"
                fs.run_sync(fw, hm, state, prefer=prefer)
                self.assertEqual(bool(hm.patches), expect_patch)
                final = "côté flow" if prefer == "flow" else "côté hermes"
                self.assertEqual(hm.jobs["2fe480e1937a"]["prompt"], final)
                self.assertEqual(inputs_of(fw.flows["f1"])["hermesJobPrompt"], final)

    def test_noeud_sans_job_est_signale_une_fois_sans_rien_creer(self):
        fw, hm, state = FakeFlowise(flow(nodes=[node(hermesJobName="Limoges actu")])), FakeHermes(job()), {}
        msgs = fs.run_sync(fw, hm, state)
        self.assertTrue(any("non lié" in m and "Limoges actu" in m for m in msgs))
        self.assertEqual((fw.updates, hm.patches, len(hm.jobs)), ([], [], 1))
        self.assertEqual(fs.run_sync(fw, hm, state), [])

    def test_ref_explicite_relie_un_noeud_a_un_job_de_nom_different(self):
        fw = FakeFlowise(flow(nodes=[node(hermesJobName="Limoges actu", hermesSyncRef="2fe480e1937a")]))
        hm = FakeHermes(job())
        fs.run_sync(fw, hm, {})
        self.assertEqual(inputs_of(fw.flows["f1"])["hermesJobName"], "Limoges actus")

    def test_job_supprime_dans_hermes_est_signale(self):
        fw, hm, state = FakeFlowise(flow()), FakeHermes(job()), {}
        fs.run_sync(fw, hm, state)
        hm.jobs.clear()
        msgs = fs.run_sync(fw, hm, state)
        self.assertTrue(any("n'existe plus" in m for m in msgs))

    def test_seules_les_operations_sync_sont_concernees(self):
        fw = FakeFlowise(flow(nodes=[node(op="create"), node("autre_1", op="list")]))
        hm = FakeHermes(job(schedule="0 9 * * 1"))
        self.assertEqual(fs.run_sync(fw, hm, {}), [])
        self.assertEqual(fw.updates, [])

    def test_plusieurs_noeuds_d_un_meme_flow_donnent_une_seule_ecriture(self):
        n1 = node("n_1", hermesJobName="Job A")
        n2 = node("n_2", hermesJobName="Job B")
        fw = FakeFlowise(flow(nodes=[n1, n2]))
        hm = FakeHermes(job("aaaaaaaaaaaa", name="Job A", schedule="0 1 * * *"), job("bbbbbbbbbbbb", name="Job B", schedule="0 2 * * *"))
        fs.run_sync(fw, hm, {})
        self.assertEqual(len(fw.updates), 1)
        self.assertEqual((inputs_of(fw.flows["f1"], "n_1")["hermesJobSchedule"], inputs_of(fw.flows["f1"], "n_2")["hermesJobSchedule"]), ("0 1 * * *", "0 2 * * *"))

    def test_flowdata_invalide_ignore(self):
        fw = FakeFlowise({"id": "x", "name": "cassé", "flowData": "pas du json"})
        self.assertEqual(fs.run_sync(fw, FakeHermes(job()), {}), [])


class StateTest(unittest.TestCase):
    def test_aller_retour(self):
        import tempfile
        path = os.path.join(tempfile.mkdtemp(), "s.json")
        self.assertEqual(fs.load_state(path), {})
        fs.save_state(path, {"links": {"a": 1}})
        self.assertEqual(fs.load_state(path), {"links": {"a": 1}})


if __name__ == "__main__":
    unittest.main()
