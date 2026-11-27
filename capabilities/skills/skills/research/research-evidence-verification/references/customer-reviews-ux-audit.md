# Auditer des avis clients et des dispositifs UX sans surinterpréter les preuves

(Moved unchanged from SKILL.md on 2026-11-27.)

1. Lis le contrat de recherche avant toute collecte. Sépare les livrables : registre des sources, synthèse des avis par plateforme, thèmes d'avis, matrice UX et captures. Utilise le préfixe source attribué et relie chaque observation à une URL, une date de collecte et un identifiant de preuve.

2. Collecte les avis par plateforme sans fusionner leurs notes. Relève la note, le nombre total d'avis et la distribution des étoiles seulement lorsqu'ils sont visibles. Conserve séparément la taille de l'échantillon effectivement lu, les dates et les thèmes. Une demande de « dix avis » adressée à WebFetch ne prouve pas que dix avis exploitables ont été obtenus. Vérifie le résultat et annonce le déficit d'échantillon.

3. Applique trois états aux critères UX : `oui` = observé ; `non` = absence vérifiée dans un périmètre inspecté et explicité ; `nd` = non déterminé. Un critère non mentionné dans une extraction, un domaine inaccessible, une page bloquée ou une capture incomplète ne justifie jamais `non`. Vérifie aussi le domaine officiel avant de conclure qu'une marque n'a pas de site accessible.

4. Inspecte successivement l'accueil, une fiche produit et les pages de service pertinentes. Traite le tunnel de commande comme un périmètre distinct : l'accueil ne démontre pas la visibilité des garanties au moment de l'achat. Respecte les limites de lecture seule ; ne commande pas, ne soumets pas de formulaire et ne contacte pas un vendeur pour compléter une preuve manquante.

5. Pour les éléments visuels, vérifie d'abord l'environnement local avec `python3 -c "from playwright.sync_api import sync_playwright; print('playwright import OK')"`. Capture les pages publiques en desktop et mobile, par exemple avec `browser.new_page(viewport={"width": 1440, "height": 900})` puis `browser.new_page(viewport={"width": 390, "height": 844})`. Enregistre avec `page.screenshot(path=chemin, full_page=True)`. Ouvre ensuite les fichiers : une capture créée peut montrer seulement un bandeau de consentement, une erreur ou un chargement incomplet. Ne compte pas ces fichiers comme preuves du contenu masqué. Journalise URL finale, viewport et résultat.

6. En cas de blocage, essaie une autre voie publique autorisée : extraction WebFetch, `walter_browse`, puis navigateur local. Une recherche ou un extrait de moteur sert à découvrir une source, pas à remplacer automatiquement son contenu. Si les forums restent inaccessibles, note la lacune au lieu de multiplier les requêtes puis de présenter la collecte comme complète.

7. Pour calculer une fréquence de dispositif UX, affiche séparément `oui`, `non` et `nd`. Donne le nombre de marques réellement évaluables ; n'assimile pas les inconnus à des absences. Distingue ensuite observation du panel, témoignage individuel et recommandation analytique. La présence fréquente d'un dispositif chez les concurrents ne démontre pas, à elle seule, qu'il est indispensable à la conversion.

8. Avant remise, compare couverture demandée et couverture obtenue : plateformes, avis lus, marques, pages et captures vérifiées. Déclare explicitement les périmètres partiels, notamment le tunnel et les expériences transfrontalières. Si la mission exige `SubagentHandback`, termine par cet appel unique avec les fichiers, résultats et limites ; ne double pas l'envoi par un autre canal.
