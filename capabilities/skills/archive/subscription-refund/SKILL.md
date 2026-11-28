---
name: subscription-refund
description: "Annuler un abonnement SaaS et contester un prélèvement — patterns Camoufox pour modals, Gmail envoi, droit EU consommateur."
version: 2.0.0
author: W.Alter
metadata:
  hermes:
    tags: [refund, subscription, saas, gmail, camoufox, consumer-rights]
---

# Subscription Refund

Patterns réutilisables pour annuler un abonnement SaaS et demander un remboursement.

## Étapes génériques

1. **Identifier le prélèvement** — Gmail search par société/montant/date
2. **Accéder au compte** — cookies Mac Brave → Camoufox (voir web-service-browser)
3. **Annuler l'abonnement** — naviguer vers subscription/billing, annuler
4. **Demander le remboursement** — email au support avec base juridique EU
5. **Escalade** — si refus sous 7-10j → chargeback bancaire

## Patterns sous-jacents

Les patterns techniques utilisés ici sont documentés dans leurs skills respectifs :
- **Modals Ant Design** → `web-service-browser` (section Pièges)
- **Gmail OAuth send** → `google-workspace` (section Envoi)
- **Cookies Mac → Camoufox** → `web-service-browser` (Step 1)

## Pattern : Droit EU consommateur

Template réutilisable pour tout SaaS qui prélève un abonnement sans utilisation :

```
- Directive (EU) 2011/83, Article 14(4)-(5) : obligation de prévenir le consommateur
  avant chaque renouvellement et lui donner l'opportunité d'annuler.
- Code de la consommation, Article L.221-18 : droit de rétractation de 14 jours
  pour tout contrat de fourniture de contenu numérique/service en ligne.
- Code de la consommation, Articles L.215-1 à L.215-3 : pour les abonnements
  à reconduction tacite, le prestataire doit notifier le consommateur avant
  le renouvellement et le consommateur peut refuser la reconduction.
```

**Quand invoquer** : le SaaS prélève automatiquement, aucun rappel avant renouvellement, crédits/services non utilisés.

## Pitfalls

1. **Vérifier les scopes Gmail AVANT de tenter d'envoyer** — un 403 `insufficientPermissions` = relancer l'auth
2. **Fermer les popups promo** avant d'accéder aux boutons d'annulation
3. **Refuser systématiquement les offres de rétention** (réductions, extensions gratuites)
4. **Vérifier l'annulation** : bouton "Resume" visible = auto-renew désactivé
5. **Documenter le nom de la société** (souvent différent du nom du service — ex: NANONOBLE = Hailuo)
