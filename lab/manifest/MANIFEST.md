### Walter Lab — mesurer avant de changer

Compare une variante au comportement actuel sur les mêmes scénarios de bout en bout que le banc (`walter-scenario`), essais entrelacés, règle de décision écrite avant les essais. Peut conclure « ne rien changer ». Ne modifie jamais Walter : la proposition va au propriétaire du module ou à {{owner.address}}.

**Utilisation** : `walter-lab list`, `walter-lab run <expérience> [--repeats N]`, `walter-lab history <expérience>`. Une expérience = `experiments/<nom>.yaml` (Experiment v1).

**Code externe** : interface distincte `walter-lab sandbox run --src <copie approuvée> -- <commande>`, Docker local
sans réseau, source filtrée, liens/fichiers spéciaux refusés, limites de copie et export vers un répertoire neuf.
`walter-lab sandbox probe` vérifie le backend réel. Les scénarios du banc conservent leurs permissions hôte ; ils ne
sont pas automatiquement isolés. Le bind de travail n'a pas de quota disque pendant l'exécution. Vérifier le README
avant usage sur du code externe ; les secrets sous un nom arbitraire demandent une validation de la source/image.

Les rapports conservent le protocole (scénario, règle, ordre, empreintes de définition/code), sans valeurs
d'environnement. Scout externe et comparaison générale de runtimes restent à construire.
