"""Create or update the labels and milestones used by the issue process (CONTRIBUTING.md).

Usage, from the repository root:
    python -I .github/github_setup.py --dry-run     # show what would change
    python -I .github/github_setup.py               # apply it
    python -I .github/github_setup.py --repo owner/name

Needs the GitHub CLI (`gh auth login`) with write access to the repository.
Safe to re-run: labels and milestones that already exist are updated, never duplicated.
A label listed in REMOVED is deleted only if no issue or pull request carries it.
To reuse the process on another board, copy .github/ and CONTRIBUTING.md, edit the
lists below, then run this script once.
"""

import argparse
import json
import subprocess
import sys
import urllib.parse

# (name, colour, description). One type, at least one part, one priority per sorted issue.
LABELS = [
    # Type
    ("bug", "d73a4a", "Quelque chose est faux : schéma, PCB, BOM, fichiers ou CI"),
    ("vérification", "fef2c0", "À vérifier : peut se révéler correct"),
    ("décision", "e99695", "Demande une décision du responsable du projet"),
    ("idée", "a2eeef", "Amélioration proposée, pas indispensable"),
    ("question", "d876e3", "Demande d'information, pas de travail prévu"),
    # Priority
    ("P0", "b60205", "Bloquant : empêche d'atteindre le jalon"),
    ("P1", "d93f0b", "Important : à faire dans le jalon"),
    ("P2", "fbca04", "Non bloquant : quand il y a le temps"),
    # Part of the project
    ("schéma", "1d76db", "Schéma KiCad : symboles, valeurs, connexions"),
    ("pcb", "0052cc", "Placement, routage, plans de cuivre, sérigraphie"),
    ("fabrication", "5319e7", "BOM, Gerbers, fichier de placement, commande"),
    ("mise-en-route", "0e8a16", "Première mise sous tension et essais d'une carte reçue"),
    ("mesures", "006b75", "Justesse, bruit, bande passante, chauffe, mesurés sur la carte"),
    ("simulation", "c5def5", "LTspice, openEMS, modèle thermique"),
    ("ci", "bfdadc", "KiBot, GitHub Actions, sorties générées"),
    ("documentation", "0075ca", "README, guides, notes de conception"),
    # Follow-up
    ("à-trier", "ededed", "Nouvelle : type, priorité et jalon pas encore posés"),
    ("rev-b", "cccccc", "Pour la prochaine révision de la carte"),
    ("duplicate", "cfd3d7", "Déjà signalé : fermer avec le lien vers l'issue d'origine"),
    ("wontfix", "ffffff", "Ne sera pas fait : la raison est dans le dernier commentaire"),
    ("good first issue", "7057ff", "Bon point d'entrée pour un nouveau venu"),
    ("help wanted", "008672", "Un coup de main est le bienvenu"),
]

# GitHub default labels replaced by the ones above (enhancement -> idée,
# invalid -> close the issue as "not planned" with the reason).
REMOVED = ["enhancement", "invalid"]

# (title, description), from the most urgent to the furthest.
MILESTONES = [
    ("Rev A : prête à commander",
     "Tout ce qu'il faut corriger, vérifier ou décider avant de commander la carte rev A "
     "(ERC, DRC, parité schéma/PCB, BOM, fichiers de fabrication)."),
    ("Rev A : mise en route",
     "Inspection, première mise sous tension limitée en courant, rails, "
     "puis essai de chaque fonction sur une carte reçue."),
    ("Rev A : validation",
     "Prouver la carte : justesse du courant et de la tension sur les quatre voies, "
     "bruit, bande passante, chauffe des shunts, tenue mécanique."),
    ("Rev B",
     "Corrections et améliorations pour la prochaine révision de la carte."),
]


def gh(*args):
    result = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8")
    if result.returncode:
        sys.exit(f"gh {' '.join(args)} failed:\n{result.stderr.strip()}")
    return result.stdout


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", help="owner/name (default: the repository of the current folder)")
    parser.add_argument("--dry-run", action="store_true", help="print the changes, apply nothing")
    args = parser.parse_args()
    repo = args.repo or json.loads(gh("repo", "view", "--json", "nameWithOwner"))["nameWithOwner"]
    dry = args.dry_run
    print(f"{repo}{' (dry run)' if dry else ''}")

    print("Labels")
    existing = {label["name"]: label for label in json.loads(
        gh("label", "list", "-R", repo, "--limit", "500", "--json", "name,color,description"))}
    for name, color, description in LABELS:
        current = existing.get(name)
        if current and current["color"].lower() == color and current["description"] == description:
            print(f"  ok      {name}")
            continue
        print(f"  {'update' if current else 'create'}  {name}")
        if not dry:
            gh("label", "create", name, "-R", repo, "--color", color,
               "--description", description, "--force")
    for name in REMOVED:
        if name not in existing:
            continue
        query = urllib.parse.quote(name)
        if json.loads(gh("api", f"repos/{repo}/issues?labels={query}&state=all&per_page=1")):
            print(f"  keep    {name} (still on an issue or a pull request)")
            continue
        print(f"  delete  {name}")
        if not dry:
            gh("label", "delete", name, "-R", repo, "--yes")

    print("Milestones")
    milestones = {m["title"]: m for m in json.loads(
        gh("api", f"repos/{repo}/milestones?state=all&per_page=100"))}
    for title, description in MILESTONES:
        current = milestones.get(title)
        if current and (current["description"] or "") == description:
            print(f"  ok      {title}")
            continue
        print(f"  {'update' if current else 'create'}  {title}")
        if dry:
            continue
        if current:
            gh("api", "-X", "PATCH", f"repos/{repo}/milestones/{current['number']}",
               "-f", f"description={description}")
        else:
            gh("api", f"repos/{repo}/milestones",
               "-f", f"title={title}", "-f", f"description={description}")


if __name__ == "__main__":
    main()
