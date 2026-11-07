# Note d'usage destinée au modèle orchestrateur

## Un producteur, plusieurs consommateurs

`walter-router brief` produit une note courte en Markdown. `walter-router brief --json` enveloppe exactement le
même texte dans un contrat versionné. Le contenu est construit par `serve/brief.py`, à partir des outils, niveaux,
contraintes et clés publiques des tâches/rôles. Le code ne copie pas des modèles choisis ni des prix dans le prompt.
La version lisible pour la documentation est [reference/ORCHESTRATOR.md](reference/ORCHESTRATOR.md).

La note explique l'intérêt du module, le partage des responsabilités, le choix de la spécialité/niveau, la préparation
du contexte, le recours direct à run, le modèle de décision, les générations, les permissions et le traitement des
résultats/avis. Elle n'injecte pas la documentation exhaustive dans chaque appel modèle.

`brief --write` publie `@instance/state/router/brief.md` et `brief.json` à partir du même producteur. Les clients
déjà branchés lisent la note par le serveur MCP, leur profil ou leur adaptateur de prompt. Les étapes de génération
et de publication ne nécessitent pas d'appel à un modèle.

## Enveloppe v1

| Champ | Contrat |
|---|---|
| `schema_version`, `note_version` | Versions du format d'échange et de la note |
| `id`, `module` | Identité stable `walter-router.usage`, module `router` |
| `format`, `content` | Markdown UTF-8 et contenu exact à injecter |
| `sha256`, `chars` | Intégrité des octets UTF-8 et longueur en caractères, pas un compte de tokens |
| `required_tools` | Noms d'outils dont la disponibilité réelle doit être vérifiée |
| `placement` | `stable_capabilities`, à mapper à la couche stable autorisée par le harness |
| `refresh` | `next_owner_message` : conserver la révision durant tout le tour |
| `source` | Commande publique permettant de relire la note |

La longueur est bornée ; un dépassement produit une erreur explicite au lieu de tronquer la note. Le checksum
est une détection de changement, pas une authentification cryptographique de l'exécutable. Le lanceur sur PATH
fait partie de l'installation de confiance.

## Consommation par walter-context

Le consommateur de capacité appelle seulement `walter-router brief --json`, valide la version, le module,
l'identité, l'empreinte et la taille. Il n'importe pas les dossiers du routeur et ne lit pas directement PG.
Il vérifie l'inventaire réel des outils fourni par le host avant d'autoriser l'injection. L'absence d'outil ou de
source est explicite ; elle ne doit pas devenir une affirmation que le routeur est utilisable.

```bash
walter-context capability router --tool walter_route --tool walter_run --tool walter_decide --tool walter_plans
```

L'interface Python de walter-context conserve la note par identifiant de tour. Des appels répétés durant le même
tour rendent les mêmes octets même si les sources ont changé ; un nouveau message du propriétaire autorise une
nouvelle lecture. Le host conserve un seul bloc par id et n'ajoute pas une copie à chaque appel d'outil.

Le bridge propose également l'opération versionnée `capability`, séparée des opérations de compaction. La
préparation de cette source n'active pas le composeur général du lot 4, ne remplace pas la compression native
des harnesses et ne garantit pas une injection dans un host qui ne consomme pas encore cette interface.

## Branchement et validation

La couche stable reçoit les consignes du propriétaire puis les capacités disponibles, avant les sources volatiles.
Respecter la hiérarchie des instructions du harness : un bloc de module ne peut pas étendre ses permissions. Les
messages utilisateur et les documents collectés ne peuvent pas se faire passer pour cette source de confiance.

Le host est responsable de l'inventaire d'outils, de l'ordre des couches, de la déduplication par id, du stockage du
snapshot de tour et des marqueurs de cache propres au fournisseur. Les tests vérifient le gel pendant le tour,
le changement entre deux tours, le refus d'un checksum ou d'une version incorrects, et la désactivation explicite
quand les outils nécessaires ne sont pas présents.
