---
name: free-gpu-stack
description: "Stack de providers GPU — gratuits (Modal, Kaggle, Colab, GCP, Lightning, HF Spaces) et payants (Vast.ai). Auth, CLI, pricing, exemples, GPU selection pour inference. Also covers: vastai gpu workflow."
trigger: "gpu gratuit, free gpu, modal, kaggle, colab, lightning, gpu cloud, inference gpu, training gpu, vastai, vast.ai, louer gpu, rent gpu, gpu benchmark, 3d generation gpu"
---

# Free GPU Stack — Guide complet

Stack de providers GPU accessibles gratuitement, classés par praticité pour un usage CLI/API programmatique.

---

## 1. Modal (⭐ #1 recommandé)

**Offre** : $30/mois de crédits gratuits (plan Starter). Facturation à la seconde.

**GPUs disponibles** :
| GPU | VRAM | $/sec | $/heure |
|-----|------|-------|---------|
| T4 | 16 GB | $0.000164 | $0.59 |
| L4 | 24 GB | $0.000222 | $0.80 |
| A10 | 24 GB | $0.000306 | $1.10 |
| L40S | 48 GB | $0.000542 | $1.95 |
| A100 40GB | 40 GB | $0.000583 | $2.10 |
| A100 80GB | 80 GB | $0.000694 | $2.50 |
| H100 | 80 GB | $0.001097 | $3.95 |
| H200 | 141 GB | $0.001261 | $4.54 |
| B200 | 192 GB | $0.001736 | $6.25 |

**Budget $30/mois** : ~50h T4, ~8h L4, ~2h A100

**Auth** :
```bash
pip install modal
modal setup  # Browser OAuth → authentification automatique
# Ou : modal token set --token-id <id> --token-secret <secret>
```

**Exemple minimal** :
```python
import modal

app = modal.App("gpu-task")
image = modal.Image.debian_slim().pip_install("torch", "transformers")

@app.function(gpu="T4", image=image, timeout=600)
def run_inference(prompt: str):
    from transformers import pipeline
    pipe = pipeline("text-generation", model="Qwen/Qwen3-1.7B", device_map="cuda")
    return pipe(prompt, max_new_tokens=256)[0]["generated_text"]

# Exécution locale
if __name__ == "__main__":
    with app.run():
        print(run_inference.remote("Hello world"))
```

**CLI** :
```bash
modal run script.py          # Run local
modal deploy script.py       # Deploy as app
modal shell gpu="T4"         # Shell interactif avec GPU
modal notebook               # Notebook GPU en 1 click
modal volume create models   # Stockage persistant
```

**Limites Starter** :
- 100 containers, 10 GPU concurrent
- 5 cron jobs, 8 webhooks
- Logs 1 jour
- Preemption possible (3x prix pour non-preemptible)
- Régions: US par défaut (1.5-1.75x pour EU/APAC)

**Cold start** : ~5-15s (dépend de l'image)

---

## 2. Kaggle

**Offre** : 30h/semaine de GPU gratuit. T4 (16GB) ou P100 (16GB).

**Auth** :
1. Créer compte sur kaggle.com
2. Aller dans Settings → API → Create New Token
3. Copier `kaggle.json` dans `~/.kaggle/kaggle.json`
```bash
pip install kaggle
# Configurer credentials
export KAGGLE_USERNAME="xxx"
export KAGGLE_KEY="xxx"
```

**Usage CLI** :
```bash
# Créer un notebook via API (pas de GPU direct CLI)
kaggle kernels init -p ./kernel
kaggle kernels push -p ./kernel
kaggle kernels status <kernel-slug>
```

**Limites** :
- 30h/semaine GPU
- Sessions max 12h (T4) ou 9h (P100)
- Notebook uniquement (pas de script direct)
- Pas de API GPU directe (wrapper notebook nécessaire)

---

## 3. Google Colab

**Offre** : T4 gratuit, sessions ~4h. Colab Pro ($10/mois) = T4/V100, ~24h.

**Auth** :
```python
# Via Google OAuth (browser nécessaire)
# Ou via service account
from google.colab import auth
auth.authenticate_user()
```

**Usage programmatique** :
```python
# Via API REST (avancé, nécessite Google Cloud project)
# Ou via colab-cli (non-officiel)
pip install jupyterlab
```

**Limites** :
- Sessions courtes (~4h gratuit)
- Pas de CLI propre
- Nécessite browser pour auth
- RAM limitée (12GB gratuit)

---

## 4. Google Cloud Platform ($300 crédits)

**Offre** : $300 crédits initiaux (90 jours). GPUs dans AI Platform / Compute Engine.

**GPUs** : T4 ($0.35/h), V100 ($2.48/h), A100 ($3.67/h), H100 ($11.24/h)

**Auth** :
```bash
# Créer compte GCP avec carte (pas de charge sous $300)
gcloud auth login
gcloud config set project <project-id>
gcloud compute instances create gpu-vm --zone=us-central1-a --accelerator=count=1,type=nvidia-tesla-t4 --machine-type=n1-standard-4
```

**Limites** :
- 90 jours pour utiliser les $300
- GPUs en zone limitée
- Quotas GPU à demander
- Shutdown automatique si pas de budget

---

## 5. Lightning AI

**Offre** : Heures GPU gratuites (variable, ~22h/mois T4).

**Auth** :
```bash
pip install lightning
lightning login
```

**Usage** :
```python
import lightning as L

# Lightning Studios avec GPU
# CLI: lightning run app app.py --cloud
```

**Limites** :
- Heures limitées
- Interface web-centric
- T4/A10G principalement

---

## 6. Hugging Face Spaces (Gradio/Streamlit)

**Offre** : T4 gratuit pour Spaces publiques.

**Usage** :
```bash
pip install huggingface_hub
huggingface-cli login
# Créer un Space avec GPU T4 sur huggingface.co/spaces
```

**Limites** :
- Spaces publiques uniquement (gratuit)
- T4 seulement
- Sleep après 48h d'inactivité
- Pas de CLI pour GPU direct

---

## 7. Vast.ai (Payant — meilleur rapport perf/prix)

**Offre** : Marketplace P2P de GPUs. Pas de crédits gratuits, mais prix 3-10x inférieurs aux clouds classiques.

**GPU populaires sur Vast.ai** :
| GPU | VRAM | $/hr typique | Use case |
|-----|------|-------------|----------|
| RTX 3060 | 12 GB | ~$0.15-0.20 | Modèles < 8B, budget min |
| RTX 4090 | 24 GB | ~$0.35-0.50 | Modèles < 13B, diffusion |
| A6000 | 48 GB | ~$0.40-0.70 | Modèles < 30B, marge VRAM |
| A100 80GB | 80 GB | ~$1.50-2.50 | Modèles < 70B |
| H100 | 80 GB | ~$2-4 | Benchmarks officiels, modèles lourds |
| H200 | 141 GB | ~$4-8 | Plus gros modèles, training |

**Auth** :
```bash
pip install vastai
vastai set api-key <API_KEY>   # Clé dans vault: vastai/api_key
```

**CLI — Recherche d'instances** :
```bash
# Chercher par GPU, trier par prix
vastai search offers 'gpu_name=RTX_4090 rentable=true' --order 'dph_total' --limit 5

# Filtrer par VRAM minimum, CUDA, disque
vastai search offers 'gpu_name=H100 rentable=true gpu_ram>=80 cuda_max_good>=12.0 disk_space>=100' --order 'dph_total'

# Lister tous les GPUs disponibles
vastai search offers 'rentable=true' --order 'dph_total' --limit 20

# Créer une instance
vastai create instance <ID> --image nvidia/cuda:12.4.0-devel-ubuntu22.04 --disk 50 --ssh

# Gérer les instances
vastai show instances
vastai destroy instance <ID>
```

**Colonnes utiles dans search offers** :
- `$/hr` — prix par heure
- `VRAM` — mémoire GPU en GB
- `Disk` — espace disque en GB
- `Net_up/Net_down` — bandwidth réseau (Mbps)
- `R` — reliability score (100 = parfait)
- `Max_Days` — durée max de location
- `CUDA` — version CUDA installée
- `status` — `verified` = host vérifié

**GPU selection pitfall (IMPORTANT)** :
Ne pas choisir un GPU UNIQUEMENT sur la VRAM. Pour l'inférence de modèles de diffusion/génération :
1. **Vérifier le GPU des benchmarks officiels** du modèle (souvent H100/A100) — NE PAS DISMISS l'intuition de l'utilisateur s'il demande H100
2. **Le bandwidth mémoire compte énormément** : H100 = 3.35 TB/s, RTX 4090 = 1 TB/s → facteur 2-4x sur les modèles de diffusion
3. **Vérifier les benchmarks concrets** avant de dire "c'est overkill" — chercher sur Reddit (r/StableDiffusion), GitHub issues, et le README du modèle
4. **Calculer le coût réel** : H100 à $4/hr qui fait 100 images/heure = $0.04/image. RTX 4090 à $0.40/hr qui fait 30 images/heure = $0.013/image. Le 4090 est moins cher par image MAIS plus lent en absolu.
5. **Règle** : Si le budget temps est serré ET le modèle recommande H100 → louer H100/H200. Si c'est du batch sans urgence → 4090 suffit.
6. **Anti-pattern** : Dire "c'est overkill" sans vérifier les benchmarks du modèle. L'utilisateur a souvent raison quand il dit que H100 est recommandé — vérifier avant de contredire. Montrer les vrais chiffres, pas des estimations.

## Decision Tree

```
Besoin GPU ?
├── Script/inference ponctuel → Modal ($30/mois gratuit)
├── Notebook exploration → Kaggle (30h/sem) ou Colab
├── Déploiement long terme → Vast.ai (payant) ou GCP ($300)
├── Training lourd → Modal H100 ou Vast.ai H100/H200
├── Inference rapide (benchmarks H100) → Vast.ai H200 ($4/hr) ou H100 si dispo
├── Batch sans urgence → Vast.ai RTX 4090 ($0.40/hr)
├── Modèle recommande H100 + budget serré → RTX 4090 (accepter 2-4x plus lent)
├── Modèle recommande H100 + vitesse critique → H200 ($4/hr, dispo plus souvent)
└── Demo/app web → HF Spaces (T4 gratuit)
```

## 2FA Handling (Automated Setup)

When creating accounts programmatically, Google requires 2FA for new OAuth authorizations. Server IP is flagged as suspicious.

**Protocol** :
1. Generate auth URL via CLI (`modal setup` or Kaggle registration)
2. Send URL to Lucas via Telegram (channel 1146774717)
3. Lucas completes auth on personal device (iPhone/Mac)
4. CLI receives token automatically (Modal) or manually (Kaggle API key)

**Kaggle reCAPTCHA v2** : Cannot be solved in headless mode. Requires browser on personal device. Use Google Sign-In (1 click on mobile, no CAPTCHA).

**Google 2FA** : Number matching challenge (e.g. "tap 55 on your phone"). Send number + explanation to Telegram.

## Vast.ai SSH Key Setup (CRITICAL PITFALL)

SSH keys must be attached to instances in TWO steps — missing either one causes `Permission denied (publickey)`:

```bash
# Step 1: Add SSH key to your ACCOUNT (once)
vastai create ssh-key ~/.ssh/id_ed25519.pub

# Step 2: Attach SSH key to the SPECIFIC INSTANCE (every new instance)
vastai attach ssh <INSTANCE_ID> ~/.ssh/id_ed25519.pub
```

**Why**: `create ssh-key` registers the key at the account level. `attach ssh` copies it into the instance's `authorized_keys`. New instances do NOT auto-inherit account-level keys — you must `attach ssh` each one.

**If you forgot step 2**: `attach ssh` works on running instances without restart. But if it still fails, `vastai stop instance <ID> && vastai start instance <ID>` forces re-read.

**Instance creation with pre-existing key**:
```bash
# If key is already on account, new instances MAY get it automatically
# But ALWAYS verify with ssh after creation, and attach if needed
vastai create instance <OFFER_ID> --image pytorch/pytorch:2.6.0-cuda12.4-cudnn9-devel --disk 100 --ssh --direct
```

**Verify connection**:
```bash
ssh -o StrictHostKeyChecking=no -p <PORT> root@ssh4.vast.ai "nvidia-smi"
```

## Pitfalls

- **Modal preemption** : Les fonctions peuvent être interrompues. Utiliser `--no-preempt` (3x prix) pour critique.
- **Kaggle 30h** : Le compteur se reset lundi 00:00 UTC. Tracker avec `kaggle kernels list`.
- **Colab disconnect** : L'onglet doit rester ouvert. Utiliser `colab-keep-alive.js` ou passer à Kaggle.
- **GCP quotas** : Demander augmentation quota GPU AVANT d'en avoir besoin (48-72h délai).
- **Cold starts Modal** : Première exécution ~15s. Utiliser `modal.Mount` pour gros fichiers.
- **ARM64** : Notre VM est ARM64. Modal/Kaggle/Colab exécutent en cloud x86_64 — pas de problème.
- **Modal token** : Stocker dans vault `modal/token_id` + `modal/token_secret`. Ne jamais commiter dans git.
- **Vast.ai no H100** : H100 souvent indisponible sur Vast.ai. Vérifier H200 comme alternative (même VRAM, prix similaire). H200 disponible à ~$4-8/hr.
- **Vast.ai PyTorch image** : Utiliser `pytorch/pytorch:2.6.0-cuda12.4-cudnn9-devel` pour CUDA 12.4 natif avec PyTorch pré-installé. Évite l'installation manuelle de CUDA.
- **GPU bandwidth ≠ VRAM** : Ne pas choisir un GPU seulement sur la VRAM. Le bandwidth mémoire (H100: 3.35 TB/s, 4090: 1 TB/s) impacte directement le temps d'inférence des modèles de diffusion. Voir `references/trellis2-3d-generation.md` pour un cas concret.
- **Vast.ai instance lifecycle** : `stop` preserves disk (packages, models, patches survive, relaunch ~30s). `destroy` loses everything (reinstall ~15 min). Always `attach ssh` to new instances even if key is on account. Instance stuck in "created" → explicitly `vastai start` or destroy+recreate. Stopped instances still incur small disk storage cost (~$0.01/hr per disk).
- **Vast.ai cost management — zero-idle-cost workflow** : When GPU is not actively in use, ALWAYS `destroy` instances to stop all charges (including storage). Use templates with `onstart-cmd` for automated setup on next boot. Workflow: (1) spin up from template, (2) use GPU, (3) `destroy` when done. Template `onstart-cmd` should install all deps, download models, and configure the environment automatically. For instant boot: take a `vastai take snapshot` of a running configured instance → push to Docker Hub → create template pointing to that image. Requires Docker Hub account. Alternative: use `onstart-cmd` with a setup script (~3-5 min boot delay but $0 when off). Always check `vastai show instances` for forgotten exited instances that still incur storage.
- **Vast.ai template creation** : `vastai create template --name <name> --image <docker_image> --onstart-cmd "<script>" --ssh --disk_space <GB>`. Templates encode the full launch config (image, env, onstart, disk). `vastai search templates` shows public templates. `vastai take snapshot <ID> --repo <user>/<repo>` pushes running container to Docker Hub for instant-boot templates.
- **Vast.ai long commands** : SSH timeouts on Vast.ai are common for commands >10s. **Always use tmux** for installs, builds, and generation: `tmux new-session -d -s name 'command > log 2>&1'`. Check with `tail -f log`. `nohup` and SSH heredocs can fail silently. **Never run long commands in foreground SSH** — they'll timeout and you'll lose progress.
- **Vast.ai HF gated models** : Set `HF_TOKEN` env var on the instance AND accept the license on HF web first. `vault get huggingface/token` returns masked `***` — use `age -d` on the vault file or pass the token explicitly. Download full model repo with `snapshot_download(local_dir=...)` for reproducible local loading. Some gated models (DINOv3) require manual review by the model owner — request access BEFORE you need the GPU.
- **Vast.ai setup script path** : When running setup scripts via SSH, use full absolute paths for Python scripts. `cd /path && python3 script.py` may not work correctly with `nohup` or `tmux` — the `cd` can be lost. Use `PYTHONPATH` env var instead: `PYTHONPATH=/root/TRELLIS.2 python3 /root/script.py`.

## References
- `references/trellis2-3d-generation.md` — Cas d'étude TRELLIS.2 : GPU selection pour 3D generation, benchmarks H100 vs estimations RTX 4090, pricing Vast.ai.
- **Google 2FA blocks new OAuth**: Modal and Kaggle "Sign in with Google" requires 2FA push on phone for FIRST auth. After that, API keys/tokens bypass OAuth. Plan for one manual 2FA approval per service.
- **Kaggle reCAPTCHA**: Kaggle registration uses reCAPTCHA v2 checkbox (sitekey `6LenZ0EUAAAAADh8FOnx3APzeEQxffiRaD9rcYs1`). Cannot be solved headlessly with `grecaptcha.execute()` — it's v2 checkbox, not invisible. Audio challenge selectors are unreliable in Chrome 147+. Use Google auth (requires 2FA once) or create account on a real browser.
- **Modal auth**: Modal signup requires GitHub or Google OAuth. Both need 2FA. GitHub 2FA is TOTP (can be automated if secret is stored). Google 2FA is push notification (requires phone).

## Also covers (merged 2026-11-01)

These procedures were separate skills; their full original text is kept here, unchanged.

- **free-gpu-stack** — Paid GPUs on Vast.ai: searching offers, creating and destroying instances, templates, cost optimisation.
  Read `references/merged-vastai-gpu-workflow/free-gpu-stack.md` (+ 1 supporting file in that folder).
