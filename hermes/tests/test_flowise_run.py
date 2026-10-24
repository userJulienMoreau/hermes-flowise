import io
import json
import os
import sys
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import flowise_run  # noqa: E402


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def opener_returning(payload, capture=None):
    def opener(request, timeout=None):
        if capture is not None:
            capture.update(url=request.full_url, headers=dict(request.header_items()), body=json.loads(request.data), timeout=timeout)
        return FakeResponse(payload if isinstance(payload, bytes) else json.dumps(payload).encode())

    return opener


def opener_raising(exc):
    def opener(request, timeout=None):
        raise exc

    return opener


class RunFlowTest(unittest.TestCase):
    def test_renvoie_le_texte_et_envoie_la_bonne_requete(self):
        seen = {}
        text = flowise_run.run_flow("abc", "Bonjour", base_url="http://f:3000/", api_key="k", timeout=7, opener=opener_returning({"text": " Salut \n"}, seen))
        self.assertEqual(text, "Salut")
        self.assertEqual(seen["url"], "http://f:3000/api/v1/prediction/abc")
        self.assertEqual(seen["headers"]["Authorization"], "Bearer k")
        self.assertEqual(seen["body"], {"question": "Bonjour", "streaming": False})
        self.assertEqual(seen["timeout"], 7)

    def test_sans_cle_pas_d_en_tete_authorization(self):
        seen = {}
        with mock.patch.dict(os.environ, {}, clear=True):
            flowise_run.run_flow("abc", "q", opener=opener_returning({"text": "x"}, seen))
        self.assertNotIn("Authorization", seen["headers"])
        self.assertTrue(seen["url"].startswith("http://flowise:3000/"))

    def test_lit_la_configuration_dans_l_environnement(self):
        seen = {}
        env = {"FLOWISE_URL": "http://autre:1234", "FLOWISE_API_KEY": "secret"}
        with mock.patch.dict(os.environ, env, clear=True):
            flowise_run.run_flow("abc", "q", opener=opener_returning({"text": "x"}, seen))
        self.assertEqual(seen["url"], "http://autre:1234/api/v1/prediction/abc")
        self.assertEqual(seen["headers"]["Authorization"], "Bearer secret")

    def test_override_config(self):
        seen = {}
        flowise_run.run_flow("abc", "q", override_config={"sessionId": "s"}, opener=opener_returning({"text": "x"}, seen))
        self.assertEqual(seen["body"]["overrideConfig"], {"sessionId": "s"})

    def test_no_alert_donne_une_sortie_vide(self):
        for value in ("NO_ALERT", " no_alert\n", ""):
            self.assertEqual(flowise_run.run_flow("abc", "q", opener=opener_returning({"text": value})), "")

    def test_no_alert_tolere_la_mise_en_forme_et_une_explication(self):
        for value in ("`NO_ALERT`", '"NO_ALERT".', "**NO_ALERT**", "NO_ALERT : le prix est de 94 000 $", "\n  No_Alert"):
            with self.subTest(value=value):
                self.assertEqual(flowise_run.run_flow("abc", "q", opener=opener_returning({"text": value})), "")

    def test_une_alerte_contenant_le_mot_ailleurs_reste_livree(self):
        text = "Alerte : ne répondez pas NO_ALERT, le prix dépasse le seuil."
        self.assertEqual(flowise_run.run_flow("abc", "q", opener=opener_returning({"text": text})), text)

    def test_id_manquant_ou_modele_non_rempli(self):
        for flow_id in ("", "COLLER-L-ID-DU-FLOW"):
            with self.assertRaisesRegex(flowise_run.FlowiseError, "ID du flow"):
                flowise_run.run_flow(flow_id, "q", opener=opener_returning({"text": "x"}))

    def http_error(self, code, body=b"{}"):
        return urllib.error.HTTPError("http://f", code, "err", {}, io.BytesIO(body))

    def test_erreurs_http(self):
        cases = [(401, "FLOWISE_API_KEY"), (403, "FLOWISE_API_KEY"), (404, "introuvable"), (500, "HTTP 500")]
        for code, pattern in cases:
            with self.subTest(code=code), self.assertRaisesRegex(flowise_run.FlowiseError, pattern):
                flowise_run.run_flow("abc", "q", opener=opener_raising(self.http_error(code)))

    def test_flowise_injoignable(self):
        with self.assertRaisesRegex(flowise_run.FlowiseError, "injoignable.*refused"):
            flowise_run.run_flow("abc", "q", opener=opener_raising(urllib.error.URLError("refused")))

    def test_delai_depasse(self):
        with self.assertRaisesRegex(flowise_run.FlowiseError, "n'a pas répondu en 5 s"):
            flowise_run.run_flow("abc", "q", timeout=5, opener=opener_raising(TimeoutError()))

    def test_reponses_invalides(self):
        for payload, pattern in ((b"<html>", "non JSON"), ({"autre": 1}, "sans champ"), ({"text": 3}, "sans champ")):
            with self.subTest(payload=payload), self.assertRaisesRegex(flowise_run.FlowiseError, pattern):
                flowise_run.run_flow("abc", "q", opener=opener_returning(payload))


class MainTest(unittest.TestCase):
    def test_affiche_le_texte(self):
        out = io.StringIO()
        with mock.patch("flowise_run.run_flow", return_value="Résultat"), mock.patch("sys.stdout", out):
            flowise_run.main("abc", "q")
        self.assertEqual(out.getvalue(), "Résultat\n")

    def test_silencieux_si_vide(self):
        out = io.StringIO()
        with mock.patch("flowise_run.run_flow", return_value=""), mock.patch("sys.stdout", out):
            flowise_run.main("abc", "q")
        self.assertEqual(out.getvalue(), "")

    def test_erreur_sur_stderr_et_code_1(self):
        err = io.StringIO()
        with mock.patch("flowise_run.run_flow", side_effect=flowise_run.FlowiseError("boum")), mock.patch("sys.stderr", err):
            with self.assertRaises(SystemExit) as ctx:
                flowise_run.main("abc", "q")
        self.assertEqual(ctx.exception.code, 1)
        self.assertIn("Erreur Flowise : boum", err.getvalue())


if __name__ == "__main__":
    unittest.main()
