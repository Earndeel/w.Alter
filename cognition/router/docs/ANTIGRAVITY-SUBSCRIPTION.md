# Abonnement Google AI Pro (Antigravity) dans Walter Router

La route `antigravity` exécute les modèles inclus dans l'abonnement Google AI Pro de l'instance avec la **CLI
officielle Antigravity** (`agy`). Elle sert du texte seul. Adaptateur : `llm/antigravity_subscription.py`. Voir aussi
CLAUDE-SUBSCRIPTION.md (même rôle pour Claude Pro) et EXECUTION.md.

## Pourquoi la CLI et rien d'autre

Google considère comme une violation de ses conditions toute utilisation de la connexion OAuth d'Antigravity ou de
Gemini CLI par un outil tiers (relais, proxys, plugins « antigravity-auth »). Des comptes, abonnés payants compris,
ont été suspendus tout au long de 2026, avec un bannissement définitif à la deuxième infraction. L'adaptateur ne lit,
ne copie et ne rejoue donc jamais le jeton : il lance le binaire officiel en mode impression, comme le ferait une
personne dans un terminal. Aucun texte de Google n'autorise explicitement cet usage automatisé : le risque résiduel
est accepté par le propriétaire (2026-11-02, compte principal).

## Ce que fait un appel

- Les messages OpenAI deviennent un seul prompt (instructions, conversation, dernier message), envoyé par l'entrée
  standard (`--input-format stream-json`), sans limite de taille d'argument.
- La CLI tourne dans un dossier vide et privé, avec `--sandbox`, `--disable-slash-commands` et une règle qui refuse
  toutes les familles d'outils (`read_file`, `write_file`, `read_url`, `execute_url`, `command`, `mcp`,
  `unsandboxed`). Le refus l'emporte toujours sur une autorisation. Vérifié le 2026-11-02 : écriture, lecture
  hors dossier et commande sont refusées.
- L'environnement enfant ne contient que `HOME` (le dossier de l'instance), `PATH` et `LANG` : aucune clé, aucun
  réglage de la passerelle.
- Le niveau de réflexion de la route choisit la variante vérifiée la plus proche (`gemini-3.8-flash-low|medium|high`).
- `response_format` `json_schema` passe par `--json-schema` ; `json_object` est demandé en toutes lettres puis vérifié.
- Le streaming relaie les morceaux de texte de la CLI au fil de l'eau.
- Après chaque appel, la conversation et ses traces sont supprimées du disque ; les résumés de conversations passées
  aussi, dès qu'aucun autre appel ne tourne. Aucun prompt ne survit à l'appel, aucun appel ne voit le précédent.

Refusé avant tout appel (la passerelle passe à la route suivante) : outils, images, audio, conversation qui ne finit
pas par un message de l'utilisateur.

## Coût et quota

Chaque appel ajoute les instructions d'agent de la CLI (environ 7 000 tokens d'entrée pour Gemini, 4 000 pour Sonnet,
2 800 pour GPT-OSS), décomptés du quota. Google décrit le quota AI Pro comme « d'entrée de gamme » : tous les modèles
Gemini puisent dans une même fenêtre de cinq heures, les modèles non Gemini dans une limite fixe séparée. Les crédits
IA ne servent plus qu'au dépassement. Aucun compteur n'est lisible : `meter.source = none`, un quota épuisé lève
`QuotaExhausted` et la passerelle passe à la route suivante.

## Configuration de l'instance

Dans `config/llm/gateway.json`, la clé `antigravity_subscription` :

- `enabled` : activation explicite (false par défaut).
- `cli` : le binaire officiel, copie de l'instance (`@instance/state/router/antigravity/bin/agy`).
- `home` : dossier personnel de la CLI, qui contient sa connexion (`.gemini/antigravity-cli/`, jamais lu par Walter).
- `timeout` : délai par appel, en secondes.
- `verified_models` : identifiants exacts de la CLI qualifiés sur le compte. Une présence au catalogue ne suffit pas.

Le plan `google-ai-pro` (Walter Router `plans`) porte `route_provider = antigravity`.

## Installation, connexion, mise à jour

```bash
curl -fsSL https://antigravity.google/cli/install.sh -o install.sh   # lire, puis : bash install.sh --dir <bin>
HOME=<home> <bin>/agy            # une fois, interactif : Google OAuth, coller le code ; décocher la collecte
HOME=<home> <bin>/agy models     # catalogue du compte
HOME=<home> <bin>/agy update
```

Sur la VM, la connexion a été faite le 2026-11-02 par le navigateur de session (CloakBrowser, cookies du propriétaire) :
choix du compte, confirmation « appli téléchargée depuis Google », code recopié dans la CLI sans être affiché.

## Vérification

```bash
walter-router research --source antigravity
walter-router route general --model gemini-3-8-flash     # antigravity en tête des routes
echo '{"route":{"provider":"antigravity","model":"gemini-3.8-flash","reasoning":"low"},"messages":[{"role":"user","content":"ok ?"}]}' | llm/gateway.py call
```

Après une mise à jour de la CLI : relancer `tests/test_antigravity_subscription.py` et refaire l'essai de refus des
outils (un fichier demandé ne doit pas apparaître).
