# W.Alter Skills — procédures et workflows

Bibliothèque de procédures testées et de workflows (qui enchaînent plusieurs skills), partagée entre les agents. Le Curator l'entretient en continu : noms, descriptions, domaines, fusions, archivage, et l'index.

**Utilisation**
1. Repérer le domaine ci-dessous, puis `skills_index(domain)` (ou `module_index("skills", domain)`) : à quoi sert chaque entrée, workflows d'abord.
2. Si le domaine est inconnu : `skills_search(query)` par intention.
3. `skill_read(name)`, puis seulement les références utiles. Un workflow renvoie à ses skills composants.
4. Après une tâche qui se reproduira : `skill_propose` ; un skill faux ou périmé : `skill_patch`.
