# Contribuer à OPEN_PHASE

Tout le travail se suit dans les **issues GitHub**. L'issue épinglée
[**#1 Sommaire**](https://github.com/foukouda/OPEN_PHASE/issues/1) les range par jalon :
ce qui est fait, ce qui reste, ce qui bloque.

**La vérité est sur GitHub.** Une mesure, une décision ou un piège trouvé va dans une
issue, jamais seulement dans une conversation, un message privé ou la mémoire d'une IA.

## Signaler un problème

1. **Chercher d'abord** dans les issues ouvertes et dans #1. Si le problème existe déjà,
   ajouter ta preuve en commentaire là-bas plutôt que d'ouvrir une nouvelle issue.
2. **New issue**, puis choisir le modèle :

   | Modèle | Quand l'utiliser |
   |---|---|
   | 🐞 Problème sur la carte | Quelque chose est faux et tu peux le montrer (DRC, fiche technique, mesure) |
   | 🔍 Point à vérifier | Un doute : ça peut se révéler correct |
   | 🔬 Carte reçue : défaut ou mesure | Un résultat sur une vraie carte, bon ou mauvais |
   | ❓ Décision à prendre | Un choix qui revient au responsable du projet |
   | 💡 Idée ou amélioration | Utile mais pas indispensable |
   | 🧩 Tâche | Un travail qui n'est pas un défaut (fichiers, commande, procédure) |

3. **Titre** : `Zone : ce qui ne va pas`. Exemples : `PCB : les LED de rail ne sont pas
   reliées à leurs résistances`, `BOM : IC3 n'a pas de référence LCSC`,
   `Carte 2 : +5VA à 4,62 V à vide`.
4. **Une issue = un problème** qu'on peut corriger et fermer d'un coup.
5. **Donner la preuve et son niveau** (voir plus bas). Un exemple complet :
   [#2](https://github.com/foukouda/OPEN_PHASE/issues/2).

Une bonne issue répond à quatre questions : **où** (références, nets, coordonnées),
**quel constat** (avec sa source), **quelle conséquence** sur la vraie carte, et **quoi
faire** (une case par action). Les modèles posent ces questions.

## Labels

Une issue triée porte **un type, au moins une partie, une priorité et un jalon**.

| Type | Sens |
|---|---|
| `bug` | Quelque chose est faux : schéma, PCB, BOM, fichiers ou CI |
| `vérification` | À vérifier : peut se révéler correct |
| `décision` | Demande une décision du responsable du projet |
| `idée` | Amélioration proposée, pas indispensable |
| `question` | Demande d'information, pas de travail prévu |

| Priorité | Sens |
|---|---|
| `P0` | **Bloquant** : empêche d'atteindre le jalon (on ne commande pas, on ne met pas sous tension) |
| `P1` | Important : à faire dans le jalon |
| `P2` | Non bloquant : quand il y a le temps |

| Partie | Contenu |
|---|---|
| `schéma` | Symboles, valeurs, connexions |
| `pcb` | Placement, routage, plans de cuivre, sérigraphie |
| `fabrication` | BOM, Gerbers, fichier de placement, commande |
| `mise-en-route` | Première mise sous tension et essais d'une carte reçue |
| `mesures` | Justesse, bruit, bande passante, chauffe, mesurés sur la carte |
| `simulation` | LTspice, openEMS, modèle thermique |
| `ci` | KiBot, GitHub Actions, sorties générées |
| `documentation` | README, guides, notes de conception |

| Suivi | Sens |
|---|---|
| `à-trier` | Posé par les modèles. Retiré au triage |
| `rev-b` | Pour la prochaine révision de la carte |
| `duplicate` | Déjà signalé : fermer avec le lien vers l'issue d'origine |
| `wontfix` | Ne sera pas fait : la raison est dans le dernier commentaire |
| `good first issue`, `help wanted` | Pour accueillir un nouveau venu |

Les labels et les jalons sont créés par `python -I .github/github_setup.py`. Pour en
changer, modifier ce script et ce tableau ensemble, puis relancer le script.

## Jalons

| Jalon | Contenu |
|---|---|
| **Rev A : prête à commander** | Tout ce qu'il faut corriger, vérifier ou décider avant de commander la rev A |
| **Rev A : mise en route** | Inspection, première mise sous tension limitée en courant, rails, puis chaque fonction |
| **Rev A : validation** | Prouver la carte : justesse sur les quatre voies, bruit, bande passante, chauffe des shunts |
| **Rev B** | Corrections et améliorations pour la révision suivante |

## Vie d'une issue

```
 Nouvelle ──▶ Triée ──▶ Prise ──▶ En cours ──▶ Fusionnée ──▶ Fermée
 à-trier      labels,   assignée  branche +    dans dev      cochée
              jalon,              PR brouillon               dans #1
              dans #1
```

**Trier** (le responsable du projet, ou la personne qu'il désigne, à chaque nouvelle
issue) : retirer `à-trier`, poser type, partie, priorité et jalon, puis ranger l'issue
dans #1 (sous-issue et ligne dans le bon jalon).

```
gh issue edit N --remove-label à-trier --add-label pcb,P1 --milestone "Rev A : prête à commander"
gh api repos/foukouda/OPEN_PHASE/issues/1/sub_issues -F sub_issue_id=$(gh api repos/foukouda/OPEN_PHASE/issues/N --jq .id)
```

**Prendre** : s'assigner l'issue (`gh issue edit N --add-assignee @me`). Sans droits
d'écriture, écrire « je prends » en commentaire. Une personne par issue.

**Un seul à la fois sur le PCB.** Un `.kicad_pcb` ou une feuille `.kicad_sch` ne se
fusionnent pas : avant de toucher à un fichier KiCad, vérifier que personne d'autre n'a
d'issue en cours dessus, et le dire dans la sienne.

**Travailler** :

1. Une branche par issue, partie de `dev` à jour : `fix/N-sujet`, `feature/N-sujet` ou
   `docs/N-sujet`.
2. Ouvrir tout de suite une PR en brouillon vers `dev` (`gh pr create --draft --base dev`),
   avec `Issue : #N` en tête. Le modèle de PR demande la preuve.
3. Chaque message de commit cite l'issue (`Route the rail LED anodes (#2)`) : il apparaît
   aussitôt dans l'issue.

**Fin d'étape** (fin de session, travail interrompu, PR prête) : un commentaire sur
l'issue, toujours sous cette forme :

```
**Fait** : …
**Preuve** : DRC-ERC / MESURÉ / …, avec les comptes, la capture ou le lien vers la CI
**Reste** : …
**Suite** : …
```

**Fermer** : la PR passe de brouillon à prête quand la preuve est écrite ; elle est
fusionnée dans `dev`, puis `dev` dans `main` à chaque étape terminée. GitHub ne ferme une
issue tout seul que pour une PR vers `main` : celui qui fusionne dans `dev` ferme donc
l'issue à la main, avec le lien vers la PR, et la coche dans #1. Une issue qui ne sera
pas faite se ferme en « not planned » avec la raison (`wontfix`), un doublon avec le lien
vers l'original (`duplicate`).

## Niveaux de preuve

Du plus fort au plus faible. On écrit toujours lequel s'applique.

| Niveau | Veut dire |
|---|---|
| **MESURÉ** | Vu sur une vraie carte, avec l'appareil et les conditions |
| **DRC-ERC** | Trouvé ou vérifié par `kicad-cli` (ou KiCad) sur un commit donné |
| **FICHE TECHNIQUE** | Lu dans la fiche du fabricant, page et tableau cités |
| **SIMULATION** | LTspice, openEMS ou modèle thermique du dossier `Simulation/` |
| **À VÉRIFIER** | Un doute, rien de prouvé |

Sans carte, on ne dit pas « ça marche » : on dit ce qui a été vérifié, et comment.

## Branches et commits

- `main` : état stable, la branche que tout le monde voit. `dev` : intégration.
- Un commit = un changement cohérent, à l'impératif en anglais
  (`Route the rail LED anodes (#2)`), avec un corps qui dit **pourquoi** et ce qui a été
  vérifié (DRC, mesure, simulation).
- La CI KiBot tourne à chaque push sur `dev` et `main` et ajoute ses propres commits
  « Update Outputs » : ne pas modifier les sorties générées à la main.
- Le `README.md` est **généré** depuis `kibot_resources/templates/readme.txt` : modifier
  le gabarit, pas le README.
- Chaque changement de la carte a sa ligne dans `CHANGELOG.md`, section `[Unreleased]`.

## Vérifier un changement de carte

```
kicad-cli sch erc OPEN_PHASE.kicad_sch
kicad-cli pcb drc --schematic-parity OPEN_PHASE.kicad_pcb
```

Un changement ne doit ajouter **aucun nouveau défaut**. Référence au 2026-11-08
(`dev` @ `7054a4e`) : ERC 6 violations ; DRC 203 violations, 4 éléments non connectés
(#2), 16 écarts schéma/PCB. Quand une PR fait baisser ces comptes, elle met cette ligne
à jour.

## Pour un assistant IA

- Lire ce fichier et l'issue #1 avant de commencer ; partir de `dev` à jour.
- Ne pas modifier le routage ni le placement du PCB sans qu'une issue le demande. Un
  défaut trouvé en chemin devient une issue, il ne se corrige pas en silence.
- Dire le niveau de preuve de chaque affirmation.
- Ce qui a été appris (mesure, décision, piège) va dans l'issue, pas seulement dans la
  mémoire de l'IA.
