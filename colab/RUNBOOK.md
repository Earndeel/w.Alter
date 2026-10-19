# W.Alter / Colab — calcul ponctuel, pas GPU en veille

## Contrat économique

- Aucun achat autorisé (`new_purchase_allowed=false`) ; aucun refresh token Google dans le notebook (`google_credentials_in_runtime_allowed=false`).
- **Zéro nouvel achat n'est pas zéro compute unit.** Un GPU Colab alloué peut consommer les unités incluses, y compris pendant la préparation. Aucun taux, économie ou disponibilité GPU ne doit être inventé à partir d'un test CPU ou d'un solde arrondi inchangé.
- Développement, tests du pont et du transport sur CPU. Pour le vrai calcul GPU, choix explicite de l'accélérateur et solde positif ; aucune substitution vers un worker Colab gratuit/sans solde.
- Ni keep-alive, ni serveur distant permanent, ni multi-comptes. Utilisation de cellules du notebook à travers le MCP officiel `googlecolab/colab-mcp` et l'interface Fichiers de Colab, avec sauvegarde/récupération des résultats avant suppression.
- Règles vivantes : https://research.google.com/colaboratory/faq.html ; le solde et les options du compte sont des preuves distinctes du matériel effectivement alloué.

## Chemin de moindre gaspillage

### Interverrouillage de préparation GPU

Le contrôleur canonique **refuse actuellement tous les jobs T4/L4/A100**, même avec `--allow-included-units`, avant lecture de la configuration, contact navigateur ou création du répertoire résultat. Il retourne `status=blocked`, `reason=gpu_preparation_incomplete`, `allocation_requested=false`. L'entrée directe `run_prepared` applique également le refus avant contact navigateur ; les jobs CPU restent opérationnels.

C'est un **verrou provisoire**, pas un validateur de préparation ni la preuve que les modèles sont prêts. Aucun paquet Qwen + LoRA ou H3 complet n'a encore été préparé/validé. Ne pas retirer le verrou avec un simple flag, un `ready=true` ou une attestation vide ; le remplacer uniquement par un contrôle réel des artefacts préparés et de leur restauration, accompagné de tests. Ne pas contourner ce verrou avec `run.py`, une ancienne cellule ou le script Qwen lancé directement : les outils bas niveau n'appliquent pas ce nouveau contrôle.

Conditions avant déverrouillage d'un pipeline précis :

- Révisions exactes du moteur, modèles/encodeur/VAE et éventuels LoRA ; poids identifiés et vérifiés, licence/accès résolus côté VM. Pour les LoRA, compatibilité avec la famille exacte, poids d'application et mots déclencheurs explicites ; leur présence dans Civitai ne démontre pas leur compatibilité Qwen 2.1/GGUF.
- Code et dépendances préparés hors GPU pour **le fingerprint cible** Python/ABI, x86_64, Torch/CUDA ; ne pas archiver l'environnement ARM de la VM comme s'il s'agissait de Colab. Construire et tester une restauration persistante avant allocation. Si la base change, refuser puis repréparer hors GPU, pas lancer un `pip install` de rattrapage sur GPU.
- Workflow et paramètres fixés, graphe/imports/tests CPU validés autant que possible, entrées/sorties prévues, aucun login ni choix de modèle à résoudre une fois le GPU alloué. Grouper uniquement les résultats réellement demandés, pour charger le modèle une seule fois.
- Transport des gros poids choisi et vérifié avant lancement ; ne pas les passer par le Blob navigateur ni prétendre qu'ils survivent à un changement CPU → GPU. Comparer copie/cache au téléchargement public pour le coût complet. Une restauration/copie locale, le chargement des poids et le contrôle CUDA/VRAM restent du temps alloué inévitable : en borner et mesurer le coût, sans promettre zéro préparation matérielle.
- Distinguer backend H3 local et API externe : pas de substitution payante/silencieuse, pas d'affirmation de compatibilité GPU/LoRA/2K sans validation du backend exact.
- Après allocation : contrôle matériel, restauration/chargement bornés, inférence, récupération vérifiée, suppression. Pas d'exploration, de débogage ou de téléchargement opportuniste pendant que les unités tournent.

1. Préparer code, données, hashes et paramètres **sur la VM W.Alter avant allocation**.
2. Préserver le navigateur Google déjà autorisé via le harnais Walter. Le MCP navigue vers le notebook privé configuré, préserve son fragment secret sur localhost et vérifie la cible exacte avant lecture/écriture/exécution.
3. Refuser une session Colab déjà active : ne pas modifier ou arrêter les calculs de Monsieur.
4. Choisir le CPU pour les contrôles ; pour un job GPU préparé, comparer le coût complet mesuré en unités par résultat utile à qualité égale, plutôt que choisir automatiquement le plus petit GPU. Une option disponible n'est pas une garantie d'allocation ; vérifier le matériel au démarrage, sans fallback CPU silencieux.
5. Envoyer les petits fichiers par l'interface Fichiers authentifiée, vérifier SHA256 et taille depuis le runtime ; ne pas injecter de credentials ni appeler `drive.mount()`.
6. Exécuter le calcul comme processus borné dans une cellule. Un script peut grouper plusieurs résultats pour amortir le démarrage, mais ne doit pas servir de daemon.
7. Récupérer exactement les sorties, avec taille et SHA256 mesurés sur Colab puis contrôlés sur la VM.
8. En `finally`, **déconnecter ET supprimer** uniquement le runtime commencé par cette commande ; vérifier ensuite le bouton déconnecté **et zéro session active** dans Resources. Une déconnexion de l'interface seule n'est pas une preuve de libération.

## Commande de calcul à la demande

Entrée canonique : `/opt/walter-colab/on_demand.py job SCRIPT`. Ne pas remplacer ce cycle par `run.py bootstrap`, `stage` ou `persist`, qui ne gèrent pas la suppression de bout en bout.

Exemple CPU réellement éprouvé (la fixture requiert `walter-probe.json`) :

```bash
/opt/walter-colab/mcp/.venv/bin/python -B /opt/walter-colab/on_demand.py job \
  /opt/walter-colab/fixtures/on-demand-cpu-smoke.py \
  --input /opt/walter-colab/evidence/20261011-cpu/cli-input/walter-probe.json \
  --output result.json --device cpu --timeout-seconds 10 \
  --result-dir /root/.hermes/cache/scratch/colab-cpu-result
```

Exemple de syntaxe GPU, **bloqué par l'interverrouillage actuel, pas un benchmark exécuté** :

```bash
/opt/walter-colab/mcp/.venv/bin/python -B /opt/walter-colab/on_demand.py job \
  /chemin/job.py --input /chemin/input.json --output output.json \
  --device T4 --allow-included-units --timeout-seconds 300 \
  --result-dir /chemin/resultats
```

- `--device` : `cpu` par défaut, ou `T4`, `L4`, `A100`. Les GPU sont provisoirement bloqués pour préparation incomplète. Après remplacement du verrou par un validateur réel, ils exigeront aussi `--allow-included-units` et un solde positif relu ; aucun achat ni repli silencieux. Ce flag autorise l'utilisation des unités présentes, **pas une consommation nulle**, et ne contourne pas le verrou de préparation.
- `--input` et `--output` sont répétables. Chaque script/entrée/sortie est limité à **80 MiB** dans ce CLI. Noms simples, pas de symlink, pas de collision ; fichier existant identique réutilisé, différent refusé. Les sources sont hashées avant allocation puis revalidées avant envoi.
- Le job est un script Python lancé une seule fois dans `/content/walter-cache-store`. Le type GPU demandé est contrôlé par `nvidia-smi` avant lancement ; cela n'est pas un test CUDA ni une garantie de capacité VRAM.
- `--timeout-seconds` borne le processus Python, de 1 à 3600 secondes (défaut 60), **pas** la durée complète allocation/transfert. Stdout/stderr ramenés à 8 KiB chacun.
- Rapport JSON : statut, hashes, tailles, chemins des résultats, durées cellule/totale, snapshots Resources, suppression. `compute_units_consumed=null` tant qu'aucun compteur exact n'est fourni ; ne jamais déduire zéro d'un solde arrondi.
- Code retour 0 uniquement pour un calcul réussi **et** une suppression vérifiée ; timeout/erreur = code non nul. Les erreurs de contrôleur sont rapportées sur stderr, sans exception externe brute.
- Verrou local non bloquant par notebook, conservé jusqu'après cleanup : une deuxième commande simultanée est refusée avant contact navigateur. Il ne protège pas des interventions manuelles ou des anciens outils bas niveau : ne pas les utiliser concurremment.
- Aucun retry/reconnexion automatique après erreur. Une session existante ou ambiguë est refusée, jamais supprimée par le CLI.

## Cache et gros modèles

`cache_runtime.py` sait travailler dans `/content/walter-cache-store`, sans montage Drive. Les objets persistants passent par `DriveStore` côté VM, avec fichiers privés immuables, hashes et relecture indépendante ; le cache local disparaît avec le runtime.

Le transport Fichiers est destiné aux scripts, entrées/sorties bornées et archives de dépendances raisonnables, **pas à la mise en RAM navigateur de plusieurs dizaines de Go de poids**. Sa limite est 1 GiB par fichier. Pour les gros poids publics, préférer un téléchargement local au runtime ou une voie documentée adaptée, puis mesurer le coût réel ; ne pas déplacer aveuglément tout le modèle via le navigateur.

Une archive de dépendances réutilisable doit être compatible Python/ABI, architecture, PyTorch, CUDA et versions sources ; si le fingerprint change, refuser le cache plutôt que l'importer aveuglément. Les tests actuels n'ont **pas construit ni benchmarké** l'archive ComfyUI, ni démontré un gain en unités sur une inférence.

## Vérifications réelles du 11 octobre 2026

Preuves durables : `evidence/20261011-cpu/two-fresh-cycles.json` et les deux sorties récupérées.

- Deux cycles complets successifs **sur des runtimes CPU neufs**, chacun supprimé avant le suivant.
- Durées totales observées : **42,068 s**, puis **47,316 s**. Ces nombres comprennent connexion navigateur/MCP, contrôles, allocation CPU, transferts, calcul et suppression ; ce ne sont pas des durées d'inférence GPU.
- Ancienne sortie absente dans le deuxième runtime : suppression réelle du disque local vérifiée.
- Code cache importé dans le vrai runtime et `/content/walter-cache-store` validé sans montage Drive.
- Architecture réellement observée : `x86_64` ; Python **3.13.16**. Ne pas reprendre l'ancienne hypothèse Python 3.12 pour préparer le cache.
- Entrées et sorties vérifiées taille + SHA256 ; aucune autorisation Drive demandée au notebook et aucun token Google injecté.
- Solde affiché : **82,84 unités** avant/après ces tests CPU ; Resources indique **0 session active** et un taux approximatif **0 par heure** après libération. Le solde arrondi n'est pas un compteur de consommation exacte.
- Sauvegarde du notebook relue par l'API Drive sur son identifiant exact : une seule cellule de contrôle, dernière sortie/hachage conforme.
- Aucun nouveau GPU n'a été alloué pour ces validations. Elles prouvent le cycle et le transport, **pas le temps/coût d'une inférence GPU ni la disponibilité future d'un A100**.

## Validation réelle du CLI complet

Preuves : `evidence/20261011-cpu/cli-live/` et `evidence/20261011-cpu/cli-guarded-live/`.

| Parcours CPU | Résultat effectivement observé | Durée totale | Après suppression |
| --- | --- | --- | --- |
| CLI succès | Input 55 octets, résultat 152 octets relu sur la VM ; taille/SHA256 conformes | 50,035 s | 0 session active |
| CLI timeout volontaire | Processus arrêté à 1 s, exitcode -9, retour CLI 1 ; runtime supprimé malgré le timeout | 51,595 s | 0 session active |
| CLI final avec verrou | Même résultat relu, aucune présence de `nvidia-smi`, Python 3.13.16 / x86_64 | 77,802 s | 0 session active |

Le dernier calcul lui-même a pris environ 0,067 s : l'essentiel du délai vient du cycle navigateur/MCP, allocation et transferts, pas du calcul. Ce chemin convient à des jobs regroupés, pas à des micro-appels GPU supposés instantanés. Les tests finaux n'ont alloué **aucun GPU** ; le solde affiché est resté 82,84, sans preuve d'une consommation exacte nulle. Aucun montage Drive, credential notebook, achat ou service permanent ajouté.

## Pannes et garde-fous

- `HTTP 404 /tab/...: Tab not found` : onglet expiré. Le harnais de session peut restaurer les cookies sans réparer le fichier `.tab`. Créer un onglet dans **la même session autorisée** avec `walter-browser -s SESSION new ...`, naviguer vers le notebook identifié, puis rebrancher le MCP. Ne pas extraire de cookies.
- Les dialogues Material ont un rendu asynchrone. Attendre les radios `MWC-RADIO[name=accelerator]`, lire `value/checked/disabled`, vérifier la sauvegarde en rouvrant le dialogue.
- `View resources` peut fermer le panneau déjà ouvert : lire les champs présents avant de cliquer. Un rendu partiel juste après suppression impose une attente bornée, pas une nouvelle allocation.
- Les cellules de contrôle possèdent un marqueur stable ; Colab peut remplacer leur ID lors d'un ajout. Refuser les cellules étrangères, les doublons et les changements entre écriture et exécution. Ne jamais lancer `Run all`.
- Les anciens scripts `test_bootstrap.py`, `test_runner.py`, `test_fresh_runtime.py` ont désormais un main guard : un test de régression bloque subprocess/réseau à l'import et confirme qu'ils ne déclenchent pas d'appel live. Ils restent des preuves historiques susceptibles de ne plus correspondre aux contrats actuels : ne pas les exécuter comme validation courante. Énumérer les suites locales autorisées.
- `run.py status` est strictement une lecture UI/resources et n'alloue pas. À l'inverse, `bootstrap`, `stage` et `persist` sont des outils bas niveau pouvant initialiser un runtime et **ne le suppriment pas automatiquement** : ne pas les utiliser comme commande de calcul à la demande.
- Suite locale actuelle sans réseau/Colab :

```bash
/opt/walter-colab/mcp/.venv/bin/python -B -m unittest \
  test_import_safety test_transfer test_cache_local test_bridge_local \
  test_bridge_safety test_transport_safety test_on_demand test_controller_lock \
  test_gpu_preparation_gate -v
```

87 tests locaux passent : transport, contrôle de cible, imports sans effet, cycle du CLI, erreurs/timeout/cleanup, collisions, garde GPU et sérialisation, dont 5 nouveaux tests du blocage pour préparation incomplète. Les tests locaux et les cycles CPU réels prouvent des couches différentes ; aucun pipeline d'inférence GPU de production n'est encore validé.
- Un timeout de processus et un `finally` ne garantissent pas la libération si la VM W.Alter est éteinte ou si son processus est tué. Le notebook reste un environnement interactif préemptible, pas un SLA GPU.
