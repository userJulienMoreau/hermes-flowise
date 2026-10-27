"""Tests du branchement du diagnostic sur une tâche planifiée.

Le script ne fait que trois choses : viser $HERMES_HOME/tools/flowise-mcp/server.py, lancer `--doctor`
et transmettre le résultat. Ce sont ces trois choses qu'on vérifie, avec un faux serveur.
"""

import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.abspath(os.path.join(HERE, "..", "scripts", "flowise_doctor.py"))


def faux_home(rapport, code):
    """Dossier HERMES_HOME contenant un faux server.py qui imprime `rapport` et sort avec `code`."""
    home = tempfile.mkdtemp()
    dossier = os.path.join(home, "tools", "flowise-mcp")
    os.makedirs(dossier)
    with open(os.path.join(dossier, "server.py"), "w", encoding="utf-8") as f:
        f.write(f"import sys\nprint({rapport!r})\nsys.exit({code})\n")
    return home


class FlowiseDoctorTest(unittest.TestCase):
    def lancer(self, home):
        return subprocess.run([sys.executable, SCRIPT], capture_output=True, text=True,
                              env={**os.environ, "HERMES_HOME": home}, timeout=30)

    def test_rapport_transmis_et_code_0(self):
        r = self.lancer(faux_home("aucun problème", 0))
        self.assertEqual(r.returncode, 0)
        self.assertIn("aucun problème", r.stdout)

    def test_code_de_sortie_non_nul_propage(self):
        """Un diagnostic en échec doit faire échouer le script : sinon la tâche planifiée resterait muette."""
        self.assertEqual(self.lancer(faux_home("", 1)).returncode, 1)

    def test_vise_le_serveur_du_dossier_hermes_home(self):
        """Le chemin est résolu depuis $HERMES_HOME, jamais codé en dur : c'est le point qui casse en silence."""
        home = faux_home("bon chemin", 0)
        r = self.lancer(home)
        self.assertIn("bon chemin", r.stdout)
        self.assertNotIn("Traceback", r.stderr)

    def test_outil_absent_signale_une_erreur_explicite(self):
        """Sans l'outil installé, mieux vaut une erreur claire qu'un silence."""
        r = self.lancer(tempfile.mkdtemp())
        self.assertEqual(r.returncode, 1)
        self.assertIn("introuvable", r.stderr)


if __name__ == "__main__":
    unittest.main()
