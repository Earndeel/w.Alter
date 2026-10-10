# Pilotage réel avec le MCP officiel Colab

## Voie et sécurité
- Préférer `googlecolab/colab-mcp` pour le pilotage de notebook. Découvrir les schémas réels par `list_tools`, puis éprouver lecture → exécution d'une cellule inoffensive → relecture exacte des sorties avant de dire que le pont est opérationnel.
- Distinguer le pont navigateur de l'API REST grand public sur allowlist avec scope Colab spécifique, de l'API Drive qui ne provisionne pas les GPU et de Colab Enterprise.
- Maintenir le navigateur authentifié et le pont sur le même hôte si le lien officiel cible un WebSocket `localhost`. Utiliser la session VM autorisée plutôt que dépendre du Mac lorsque ce chemin est disponible.
- Utiliser le harnais de session authentifiée ; ne pas extraire les cookies. Ne jamais imprimer les tokens du fragment MCP ni exposer le pont sur Internet.

## Initialisation et contrôles
- Si l'onglet est déjà sur Colab, une navigation ne changeant que le fragment peut laisser la SPA intacte sans initialiser MCP. Forcer une navigation complète avec un paramètre query non secret unique, en préservant le fragment officiel. Le dialogue d'approbation, le clic explicite et `get_notebook_connection_info` prouvent la connexion ; un port ouvert ou `tools/list` seul ne la prouve pas.
- Traverser les shadow roots pour les boutons Material. Cibler le bouton natif dans `shadowRoot` si le composant hôte ne transmet pas le clic.
- Privilégier un clic natif sur la référence du snapshot pour les menus ; si le snapshot borné omet un menu tardif, cibler rôle/nom exact dans le DOM profond. Un menu Closure peut réagir à `mousedown`/`mouseup` plutôt qu'au seul `.click()` synthétique. Éviter les coordonnées aveugles.
- Attendre explicitement l'apparition des contrôles après l'ouverture d'un dialogue : l'absence immédiate du radio A100 peut être une course de rendu, pas une indisponibilité GPU. Lire ensuite son état `disabled` avant toute allocation.
- Inspecter le solde via `Runtime → View resources`, même sans runtime connecté ; le bouton `Additional connection options` n'est pas une voie fiable dans cet état. Séparer solde vérifié, type sélectionné et matériel réellement attribué.

## Allocation vérifiable et bornée
- Lorsqu'un test matériel est autorisé, utiliser seulement un notebook privé de test déjà identifié. Vérifier l'identifiant et le contenu de la cellule avant son exécution.
- Sélectionner explicitement A100, puis relever modèle et mémoire par `nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader` et mémoire exposée par CUDA. « A100 » n'implique pas « 80 Go » : le modèle attribué peut être `NVIDIA A100-SXM4-40GB`.
- Refuser le fallback CPU. Exercer un petit calcul CUDA ; vérifier sa valeur attendue, son périphérique, le modèle et la mémoire avant de marquer `gpu_verified`. Une validation CUDA réussie n'est pas une validation de capacité 80 Go.
- Relire les sorties via MCP puis, si sauvegardées, via Drive sur le même `fileId`. Ne pas substituer une sortie plausible à une exécution réelle.
- En `finally`, déconnecter et supprimer uniquement le runtime créé pour le test. Lire ensuite l'absence de connexion et le nombre de sessions actives. Ne pas garder de GPU comme service ni faire de keep-alive.
- Ne pas interpréter un solde arrondi immédiatement inchangé comme une consommation nulle. Séparer durée de cellule, appel MCP avec allocation et préparation/authentification initiale.

## Droits du compte
- Lire Google One, le solde Colab, les options activées et le matériel attribué comme des preuves distinctes. Une offre partenaire Google AI Pro ne prouve pas l'origine d'un solde Colab.
- Vérifier au moment de la demande les conditions officielles d'admissibilité payante/essai gratuit. Ne pas promettre de dépôt mensuel à une offre partenaire non vérifiée ni de GPU/type mémoire garanti.
