# Maintien de Walter Router

Lire `docs/README.md` pour l'état actuel ; `docs/DESIGN.md` est historique.

- Toute évolution de paramètres, règles, schéma ou effet d'exécution doit mettre à jour son guide et les
  descriptions de `serve/api.py` / `documentation.py` correspondantes.
- Régénérer avec `walter-router docs --write`, puis vérifier `walter-router docs --check` et les tests pertinents.
  Le contrôle hors ligne est aussi intégré à la suite. Ne pas modifier les fichiers générés de `docs/reference/`.
- Une colonne SQL nouvelle doit être expliquée. Le snapshot documentaire ne contient que métadonnées, tâches
  et poids publics : aucune clé, compte, préférence privée, demande personnelle ou donnée métier brute.
- La note orchestrateur a un seul producteur, `serve/brief.py`. Mettre à jour la note quand l'usage optimal ou
  les limites changent, publier par `brief --write`, et tester son enveloppe. Ne pas recopier de prix ou de modèle
  choisi dans le prompt ; garder les octets stables pendant le tour.
- Garder les ports MCP/CLI cohérents et vérifier les schémas réellement exposés. Une documentation mise à jour
  ne recharge pas une connexion MCP déjà ouverte.
- Avant modification sur une instance, sauvegarder. Conserver les permissions du harness et documenter les
  limites d'intégration réelles ; aucune promesse de sandbox héritée sans preuve.
- Ajouter les décisions fonctionnelles à `docs/HISTORY.md`. Une modification de contrat exige la vérification
  des contrats et de leur registre généré par les interfaces Walter.
