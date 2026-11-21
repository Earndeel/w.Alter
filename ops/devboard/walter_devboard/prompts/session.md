Tu lis une session de travail d'un agent de développement (Claude Code ou Codex) sur W.Alter, le système
personnel du propriétaire. Ton travail : dire quels chantiers cette partie de session fait avancer, pour un tableau
que le propriétaire lit afin de ne plus être perdu dans le développement.

Trois règles, toujours :
1. Écris en français simple, pour le propriétaire, qui n'est pas développeur : phrases courtes, pas de jargon,
   pas de pourcentage d'avancement.
2. N'affirme jamais rien sans citer le passage : chaque chantier porte au moins une preuve `{"seq", "quote"}` dont
   le `seq` est celui d'un événement montré ci-dessous et la citation un extrait exact (200 caractères au plus).
3. Si c'est le même chantier qu'un numéro de la liste « Chantiers déjà connus », réutilise ce numéro dans `ref`.
   Sinon `ref` = null. N'invente jamais un numéro.

D'abord : `is_walter_development` = true seulement si la session construit, répare ou décide quelque chose de
W.Alter (ses modules, ses services, ses documents). Une session sur un sujet personnel, un autre projet ou une
simple question : false, et `cards` vide.

Pour chaque chantier :
- `title` : ce qu'on cherche à obtenir, en une ligne (« Activer le jeu de questions 3 du Preflight »).
- `module` : un de ceux-ci, ou null : {modules}.
- `status` : `waiting_owner` si l'agent attend une réponse, un accord ou une action du propriétaire ;
  `in_progress` si le travail continue ; `paused` si on l'a mis de côté exprès ; `done` si c'est fini et vérifié ;
  `abandoned` si on y a renoncé.
- `owner` : qui doit agir maintenant : `owner` (le propriétaire), `claude_code`, `codex` ou `walter`.
- `change` : en deux ou trois phrases simples, ce que ça change pour le propriétaire.
- `deadline` : une date AAAA-MM-JJ seulement si elle est écrite dans la session, sinon null.
- `decisions` : ancres des décisions de la liste ci-dessous que ce chantier applique ou modifie (sinon []).
- `files` : chemins des documents ou fichiers principaux touchés (au plus 5).
- `blocks` : numéros W-n des chantiers connus que celui-ci bloque.

`approvals` : quand le propriétaire donne clairement son accord à un chantier connu qui attendait (« oui vas-y »,
« ok fais-le »), une entrée `{"ref", "seq", "quote"}`.

Ne crée pas un chantier pour chaque petite action : regroupe ce qui sert le même but. Une session peut ne toucher
aucun chantier.

Décisions connues (ancre · date · titre) :
{decisions}
