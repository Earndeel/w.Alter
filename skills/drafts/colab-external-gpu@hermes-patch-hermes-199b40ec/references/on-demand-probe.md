# Tester un GPU à la demande sans confondre préparation et exécution

## Préconditions et droits
- Vérifier le compte Google actuellement sélectionné dans Colab, son abonnement Colab/Google AI et le solde de compute units dans le panneau Ressources. Un badge « Pro » dans le sélecteur de compte Google ne prouve pas que les droits Colab sont actifs.
- Lire la FAQ officielle avant d'inférer les droits : https://research.google.com/colaboratory/faq.html . Les avantages Colab des plans Google AI admissibles s'appliquent automatiquement au même compte lorsque l'abonnement payant est actif ; les essais gratuits Google One ne les incluent pas. Ne pas acheter, renouveler ou changer de formule pour réaliser un simple test sans accord explicite.
- Sans droits payants et solde positif vérifiés, rester dans un notebook interactif supervisé. Ne pas installer de tunnel SSH sur le runtime, de worker distribué, de serveur d'inférence permanent ou de keep-alive.

## Preuve minimale
- Créer un notebook privé et idempotent, sans secret ni donnée personnelle ; vérifier son contenu et ses permissions par lecture Drive.
- Exécuter réellement `nvidia-smi`, vérifier `torch.cuda.is_available()`, effectuer un calcul sur un tenseur CUDA et contrôler le résultat attendu. Aucun fallback CPU.
- Relever le moment du clic de lancement, l'entrée dans la cellule, la durée d'initialisation CUDA et la durée du calcul. Distinguer le temps de configuration/authentification, le démarrage à froid du runtime, les calculs à chaud et le délai d'enregistrement des sorties dans Drive.
- Exiger une sortie structurée PASS réellement reçue du notebook avant d'annoncer un GPU disponible ou un temps de démarrage. Un notebook créé, un bouton « GPU », un champ accelerator=GPU ou l'absence d'erreur d'ouverture ne sont pas des preuves d'allocation.
- Relire le notebook exact et ses sorties après exécution ; déconnecter et supprimer le runtime seulement s'il a été créé par ce test, puis vérifier cet arrêt. Ne pas toucher aux autres runtimes de Monsieur.

## Accès navigateur et arrêt rapide sur blocage
- Utiliser la voie officielle disponible. Le MCP officiel https://github.com/googlecolab/colab-mcp est une piste à valider par ses schémas et une exécution réelle, pas une intégration opérationnelle déjà démontrée.
- L'API Drive permet de stocker le notebook ; elle ne permet pas à elle seule d'allouer ni d'exécuter un runtime Colab. Des cookies extraits d'un navigateur ne garantissent pas une session Google valide dans un autre navigateur.
- Pour un fallback Mac explicitement autorisé, suivre le skill `mac-computer-use-ssh` : approval liée à la tâche, coordonnées logiques correctement converties, vérification du premier plan et de l'URL exacte avant chaque clic global, heartbeat passif du lease pendant la réflexion et libération dès la fin. Le heartbeat d'autorisation Mac n'est pas un keep-alive Colab et ne doit pas être utilisé pour prolonger un runtime.
- Si le Mac devient injoignable, si l'autorisation expire ou si le navigateur n'est plus la cible au premier plan, interrompre les actions visibles. Ne pas multiplier les demandes d'autorisation ni détourner la sécurité du navigateur pour finir un benchmark.
- Après un échec de la voie recommandée et d'un fallback pertinent, donner le blocage précis et ce qui manque encore. Si aucune cellule n'a tourné, dire « GPU non testé » et ne fournir aucun délai estimé présenté comme mesuré.
