# Calcul ponctuel sans montage Drive

## Cycle sûr

- Préparer code, fichiers, paramètres et hashes sur l'agent avant l'allocation ; utiliser le plus petit accélérateur explicitement choisi qui suffit à la charge, jamais une substitution silencieuse. Une allocation GPU peut consommer des compute units dès la préparation : aucun achat et aucune consommation sont des contrats distincts.
- Employer le MCP officiel dans une session navigateur autorisée, puis l'interface Fichiers Colab pour les petits fichiers. Conserver OAuth côté agent : ne pas injecter de refresh token, ne pas exposer un serveur de fichiers public et ne pas appeler drive.mount pour ce chemin.
- Lire le runtime et toutes les sessions avant de modifier le type ou d'allouer ; refuser toute session préexistante. Un status doit lire seulement UI/resources, jamais initialiser une cellule ou ouvrir une connexion de calcul.
- Réserver un store local simple sans symlink ni parent symlink. Inspecter nom/taille/SHA256 avant upload : skip si identique, refuser la collision différente ou un objet symlink. Vérifier à nouveau après transfert.
- Borne avant réseau : exiger la taille mesurée côté runtime et SHA256 avant download ; contrôler blob/chunks et récupérer vers un fichier temporaire sans écrasement. Les SDK/UI peuvent tamponner la réponse entière : une borne sink n'est pas une garantie de mémoire réseau.
- Revalider l'origine et le chemin exacts dans chaque expression JS de mutation, lecture de chunk et nettoyage ; une lecture d'URL préalable seule laisse une course de navigation.
- Exécuter le job comme processus notebook borné, récupérer les sorties exactes et vérifier leurs hashes, puis supprimer en finally le runtime commencé par cette commande. Confirmer toolbar déconnectée ET zero session active. Ne pas relancer le job automatiquement après un timeout ambigu.
- Aucun keep-alive, daemon, multi-compte ou maintien de GPU en veille. Le GPU reste distant dans Colab : il n'est pas une extension CUDA transparente de la VM.

## UI et portabilité

- Lire un panneau Resources déjà ouvert avant de cliquer View resources : ce clic peut le fermer. Attendre les champs complets en délai borné après suppression ; un rendu partiel ne prouve pas la libération.
- Attendre les radios Material, lire checked/disabled, sélectionner puis rouvrir pour vérifier le type sauvegardé avant allocation.
- Confirmer Python/ABI, architecture, Torch/CUDA et versions sources avant de restaurer un cache de dépendances ; ne pas figer la version Colab. Préférer archives de petits fichiers et comparer les gros poids Drive au téléchargement public local ; les transferts par Blob navigateur ne conviennent pas aux dizaines de Go.
- Donner un main guard à tout script d'intégration live et tester son import sous réseau/subprocess bloqués ; la découverte de tests ne doit jamais allouer un runtime. Énumérer les suites locales autorisées plutôt que lancer discover sans revue.
- Les anciens scripts de preuve peuvent être incompatibles avec un contrat récemment durci (taille pin, status sans initialisation, ownership cellule). Ne pas les relancer aveuglément : revoir leurs appels avant une nouvelle autorisation live.

## Implantation

Le contrôleur et le runbook sont dans /opt/walter-colab ; les preuves d'exécution sont séparées des contrats et des tests locaux. Traiter les chemins comme points de découverte, vérifier les fichiers actuels avant usage et ne pas reprendre un état historique du solde ou du GPU comme état présent.
