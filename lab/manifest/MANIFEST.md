### Walter Lab — mesurer avant de changer

Compare une variante au comportement actuel sur les mêmes scénarios de bout en bout que le banc (`walter-scenario`), essais entrelacés, règle de décision écrite avant les essais. Peut conclure « ne rien changer ». Ne modifie jamais Walter : la proposition va au propriétaire du module ou à {{owner.address}}.

**Utilisation** : `walter-lab list`, `walter-lab run <expérience> [--repeats N]`, `walter-lab history <expérience>`. Une expérience = `experiments/<nom>.yaml` (Experiment v1).
