---
name: colab-web-evidence-workflow
description: "Use when assessing, preparing, automating, or troubleshooting Colab as an external GPU requires public web evidence followed by bulk extraction, crawling, or Scrapling diagnostics."
type: workflow
requires: [colab-external-gpu, universal-web-extraction-router, scrapling]
---

# Colab → routage web → Scrapling

## Périmètre

Appliquer cette chaîne lorsqu'une demande Colab nécessite de rechercher ou vérifier des sources publiques, puis de traiter plusieurs URLs, explorer un site ou diagnostiquer le backend Scrapling. Une demande Colab seule ou une extraction ponctuelle ne justifie pas d'exécuter toute la chaîne.

Les sous-skills restent les références pour leurs procédures. Ce workflow définit uniquement leur ordre, leurs passages de relais et les contrôles entre étapes.

## 1. Cadrer le besoin Colab

load colab-external-gpu with skill_read

Appliquer le sous-skill pour identifier le résultat demandé, le mode d'utilisation envisagé, les contraintes du compte et les inconnues à vérifier. Charger seulement ses références pertinentes.

**Transmission au routeur web :** objectif, questions factuelles, URLs officielles connues, informations à extraire, exigences de fraîcheur et preuves manquantes. Distinguer les informations publiques des vérifications nécessitant le compte de Monsieur.

**Contrôle de passage :** chaque recherche doit résoudre une inconnue utile à la décision Colab. Conserver le statut de préparation établi par le sous-skill ; la collecte documentaire ne vaut pas validation d'exécution et ne déclenche aucune allocation.

## 2. Choisir et éprouver la route web

load universal-web-extraction-router with skill_read

Soumettre le dossier de l'étape 1 au routeur. Le laisser déterminer la voie adaptée et appliquer ses contrôles sémantiques. Il reste l'autorité de routage, y compris lorsque Scrapling décrit une autre séquence de backends.

**Transmission à Scrapling :** URLs sélectionnées ou points de départ du crawl, objectif d'extraction, champs requis, seuil de couverture, périmètre et bornes de collecte. Pour un diagnostic, joindre l'appel en échec, les erreurs et les traces utiles, sans secrets. Joindre les résultats déjà validés afin d'éviter de les collecter à nouveau.

**Contrôle de passage :** poursuivre seulement si le routeur justifie un traitement bulk/crawl ou un diagnostic Scrapling explicite. Si l'extraction ponctuelle satisfait déjà le besoin, terminer la collecte ici. Si une interaction authentifiée ou une inspection visuelle est nécessaire, suivre la branche du routeur ; ne pas forcer Scrapling.

## 3. Exécuter la collecte ou le diagnostic ciblé

load scrapling with skill_read

Exécuter uniquement l'opération transmise, selon les procédures du sous-skill et le contrat fixé par le routeur. Ne pas élargir le crawl ni modifier une configuration pour une simple collecte sans nécessité liée à la demande.

**Retour au dossier Colab :** données normalisées, URLs sources, date de collecte, couverture obtenue, éléments manquants et erreurs. Pour un diagnostic, fournir le résultat observé et les limites restantes.

**Contrôle de sortie :** vérifier le sens des données et les champs requis sur les résultats, puis signaler les échecs ou la couverture partielle. En cas de blocage persistant, revenir à la décision de routage de l'étape 2 avec les traces ; ne pas répéter une tentative inchangée ni inventer les valeurs absentes.

## Clôture

Confronter les preuves collectées aux questions de l'étape 1 en appliquant les critères Colab déjà chargés. Présenter la conclusion, ses sources, les inconnues restantes et le statut réellement vérifié. Toute exécution Colab ultérieure reste soumise aux contrôles du sous-skill Colab ; la réussite de l'extraction ne les remplace pas.
