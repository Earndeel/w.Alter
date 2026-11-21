---
name: google-flow-authenticated-workflow
description: Use when Monsieur veut ouvrir ou vérifier son compte Google Flow, consulter ses crédits ou préparer une génération nécessitant un accès navigateur authentifié.
type: workflow
requires: [google-flow-authenticated-access, web-service-browser, webtop-authenticated-browsing]
---

# Workflow d’accès authentifié Google Flow

Orchestrer les trois sous-skills dans cet ordre : cadrage Flow → accès au service → vérification technique du navigateur. Leurs procédures restent dans les sous-skills ; ne pas les recopier ici.

## 1. Cadrer la demande Flow

load google-flow-authenticated-access with skill_read.

Déterminer si Monsieur demande une ouverture, une vérification de compte/crédits ou une génération. Charger uniquement les références Flow pertinentes. Identifier les validations applicables avant toute action qui crée un projet ou consomme des crédits.

Transmettre à l’étape 2 : objectif, URL cible exacte si fournie, observations attendues, surface autorisée et état des validations de génération.

**Contrôle de passage :** une demande de consultation reste une consultation. Pour une génération, appliquer les validations du sous-skill avant les interactions qu’elles conditionnent ; ne pas transformer une préparation en soumission.

## 2. Préparer l’accès au service

load web-service-browser with skill_read.

Utiliser son entrée actuelle pour ouvrir le compte authentifié de Monsieur par le navigateur géré. Transmettre la cible et les contraintes de l’étape 1 au mécanisme d’accès ; réutiliser une session adaptée si elle existe.

Les consignes actuelles du harness et les avertissements datés des sous-skills priment sur leurs anciens exemples : utiliser l’injection serveur via walter_browse ou browser_session + walter-browser. Ne pas extraire soi-même les cookies, clés ou jetons.

Transmettre à l’étape 3 : identifiants non secrets de session/onglet, moteur et surface utilisés, URL atteinte, état de santé et première observation d’authentification, ou erreur précise si l’ouverture échoue. Ne transmettre aucune valeur d’authentification.

**Contrôle de passage :** vérifier que la session correspond à Flow et à la surface autorisée. Une page de connexion ou une ouverture réussie techniquement ne prouve pas l’accès au compte.

## 3. Vérifier le navigateur et résoudre les blocages

load webtop-authenticated-browsing with skill_read.

À partir du contexte transmis, vérifier la session et lire uniquement les références nécessaires au routage ou au problème constaté. Si le navigateur fonctionne, cette étape est une vérification courte ; ne pas lancer une seconde chaîne d’authentification.

Avant de reprendre les interactions, obtenir un snapshot frais et confirmer l’accès authentifié. Après navigation ou récupération, renouveler les références d’éléments. Un changement de moteur ou de surface doit respecter les contraintes héritées ; un fallback documenté ne vaut pas autorisation d’ouvrir un navigateur visible sur le Mac.

Renvoyer au cadrage Flow : session/onglet utilisables, URL actuelle, preuve d’authentification, snapshot récent et limites éventuelles. Si l’accès reste bloqué après la récupération pertinente, arrêter les actions dépendantes et rapporter le blocage sans contourner le harness.

## Exécuter, vérifier et terminer

Avec la session vérifiée, reprendre uniquement l’opération Flow cadrée à l’étape 1 selon google-flow-authenticated-access. Ce retour utilise le contexte déjà chargé et ne relance pas les trois étapes.

Accepter les crédits uniquement sur preuve live conforme au sous-skill Flow. Avant une soumission, vérifier que les validations requises sont acquises et que les réglages visibles correspondent à la demande. Après une erreur ambiguë, inspecter l’état et les jobs avant toute nouvelle soumission.

Rapporter les observations vérifiées et les résultats effectivement obtenus, avec les identifiants et preuves utiles sans secrets. Fermer les onglets temporaires créés par ce workflow, y compris en cas d’échec, après les vérifications ou exports nécessaires.
