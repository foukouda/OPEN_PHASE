<!-- Une PR = une issue. L'ouvrir en brouillon vers dev dès le premier commit :
     gh pr create --draft --base dev
     Règles : CONTRIBUTING.md -->

Issue : #

## Ce qui change


## Preuve

Niveau : MESURÉ / DRC-ERC / FICHE TECHNIQUE / SIMULATION <!-- garder le bon -->

<!-- Comptes avant → après, capture avant/après, mesure, lien vers la CI. -->

| | Avant | Après |
|---|---|---|
| ERC (violations) | | |
| DRC (violations / non connectés / parité) | | |

## Vérifié

- [ ] `kicad-cli sch erc` et `kicad-cli pcb drc --schematic-parity` : aucun nouveau défaut
- [ ] Routage et placement touchés seulement là où l'issue le demande
- [ ] Une ligne dans `CHANGELOG.md` (`[Unreleased]`) si la carte change
- [ ] Commentaire de fin d'étape posté sur l'issue (Fait / Preuve / Reste / Suite)
