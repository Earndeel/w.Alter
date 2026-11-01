# Préparer Qwen-Image 2.1 GGUF pour un notebook interactif

Ces règles proviennent de contrats de sources publiques et de tests hors GPU. Elles ne constituent pas une certification d'inférence Colab : mesurer le rendu avant d'annoncer une durée, une VRAM ou un résultat sûr.

- Épingler les revisions du modèle, de ComfyUI, du fork GGUF et du template avant d'installer ; comparer les tailles et SHA256 LFS avec le manifeste publié pour empêcher une substitution silencieuse.
- Employer le fork recommandé par la carte de modèle et vérifier que sa liste d'architectures inclut `qwen_image21` ; le README générique d'un fork peut encore montrer des commandes de clonage de son upstream ancien.
- Employer `CLIPLoader(type="qwen_image")` avec Qwen3-VL 8B et `TextEncodeQwenImage21` ; son latent natif est à 64 canaux et compression spatiale 16, différent du Qwen-Image original et du latent SD à 4 canaux.
- Extraire les réglages du template `image_qwen_image_2_1_t2i.json` jusque dans ses subgraphs ; un JSON éditeur n'est pas un workflow API directement exécutable.
- Signaler que le template t2i CFG=1 ignore le négatif ; utiliser un CFG supérieur uniquement comme écart explicite quand le négatif doit agir, en conservant le prompt adulte non explicite et en prévoyant une inspection visuelle.
- Charger les nœuds ciblés directement dans un processus Python lancé depuis la cellule notebook, sans entrée UI, serveur, tunnel, init de nœuds payants ni keep-alive ; activer le parsing des flags ComfyUI avant le premier import de `comfy.cli_args`.
- Désactiver DynamicVRAM pour le patcher GGUF historique et offloader/libérer encodeur, diffusion puis VAE successivement ; utiliser le cache prefixe CPU lossless et un VAE tuilé quand le budget mémoire est prioritaire.
- Conserver par contraintes exactes le Torch/torchvision CUDA du runtime plutôt que les remplacer aveuglément ; contrôler les imports du code épinglé avant les téléchargements multigigaoctets.
- Distinguer backend cu130 optimisé de comfy-kitchen et voie eager PyTorch prévue sur CUDA 12 ; l'existence de cette voie n'est pas une mesure de vitesse ni une preuve d'exécution ConvRot sur le GPU attribué.
- Forcer `token=False` pour les téléchargements publics Hugging Face et désactiver les tokens implicites ; ne lire ni afficher credentials ou cookies.
- Journaliser revisions, hashes réels des poids/script/PNG, paramètres, timings et GPU effectif ; distinguer le pic d'allocateur Torch d'une mesure continue de toutes les allocations CUDA natives.
- Refuser une sortie déjà présente avant un nouveau test pour ne pas confondre un ancien PNG avec un rendu réussi ; écrire une erreur honnête, sans fallback de modèle ou fournisseur.

Sources à relire :
- https://huggingface.co/abenzerps/Qwen-Image-2.1-Uncensored-GGUF
- https://huggingface.co/Qwen/Qwen-Image-2.1
- https://docs.comfy.org/tutorials/image/qwen/qwen-image-2-1
- https://github.com/leejet/ComfyUI-GGUF
- https://github.com/Comfy-Org/workflow_templates/blob/main/templates/image_qwen_image_2_1_t2i.json
