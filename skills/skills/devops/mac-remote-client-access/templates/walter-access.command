#!/bin/bash
# =============================================================================
# W.ALTER ACCESS — Bouton ON/OFF
# Double-cliquez pour activer OU désactiver l'accès complet de W.Alter.
# Mot de passe admin demandé UNE SEULE FOIS.
#
# ARCHITECTURE : w-alter initie la connexion SSH → ce Mac.
#                Ce Mac ne peut RIEN initier (protège le tailnet).
# =============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SSH_KEY="$SCRIPT_DIR/walter_key.pub"
SSH_DIR="$HOME/.ssh"
AUTHORIZED_KEYS="$SSH_DIR/authorized_keys"

# ── Détection de l'état ────────────────────────────────────────────────────
is_active() {
    systemsetup -getremotelogin 2>/dev/null | grep -q "On"
}

# ── Affichage ──────────────────────────────────────────────────────────────
show_status() {
    clear
    if is_active; then
        echo ""
        echo -e "${GREEN}${BOLD}  ╔══════════════════════════════════════════╗${NC}"
        echo -e "${GREEN}${BOLD}  ║     🟢  W.ALTER ACCESS — ACTIVÉ          ║${NC}"
        echo -e "${GREEN}${BOLD}  ╚══════════════════════════════════════════╝${NC}"
        echo ""
        echo -e "  ${DIM}W.Alter a actuellement accès à ce Mac.${NC}"
        echo ""
        echo -e "  Appuyez sur ${BOLD}Entrée${NC} pour ${RED}COUPER L'ACCÈS${NC}"
        echo -e "  (ou Ctrl+C pour annuler)"
    else
        echo ""
        echo -e "${RED}${BOLD}  ╔══════════════════════════════════════════╗${NC}"
        echo -e "${RED}${BOLD}  ║     🔴  W.ALTER ACCESS — DÉSACTIVÉ       ║${NC}"
        echo -e "${RED}${BOLD}  ╚══════════════════════════════════════════╝${NC}"
        echo ""
        echo -e "  ${DIM}W.Alter n'a PAS accès à ce Mac.${NC}"
        echo ""
        echo -e "  Appuyez sur ${BOLD}Entrée${NC} pour ${GREEN}ACTIVER L'ACCÈS${NC}"
        echo -e "  (ou Ctrl+C pour annuler)"
    fi
    echo ""
}

# ── DÉSACTIVATION ──────────────────────────────────────────────────────────
deactivate() {
    echo ""
    echo -e "${BOLD}⏻  Coupure de l'accès...${NC}"

    sudo bash -s << 'SUDO_OFF'
set -euo pipefail

echo "  → Screen Sharing..."
/System/Library/CoreServices/RemoteManagement/ARDAgent.app/Contents/Resources/kickstart \
    -deactivate -stop 2>/dev/null || true

echo "  → Remote Login..."
systemsetup -setremotelogin off 2>/dev/null || true
SUDO_OFF

    echo ""
    echo -e "${RED}  ╔══════════════════════════════════════════╗${NC}"
    echo -e "${RED}  ║     🔒  ACCÈS COUPÉ                      ║${NC}"
    echo -e "${RED}  ╚══════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  ${DIM}W.Alter ne peut plus se connecter.${NC}"
    echo -e "  ${DIM}Pour réactiver, relancez ce même fichier.${NC}"
    echo ""

    osascript -e 'display notification "W.Alter n'"'"'a plus accès à ce Mac." with title "🔒 W.Alter Access"' 2>/dev/null || true
    exit 0
}

# ── ACTIVATION ─────────────────────────────────────────────────────────────
activate() {
    echo ""
    echo -e "${BOLD}[1/4] Activation des services système...${NC}"

    sudo bash -s << 'SUDO_ON'
set -euo pipefail

echo "  → Remote Login (SSH)..."
systemsetup -setremotelogin on 2>/dev/null

echo "  → Screen Sharing (VNC)..."
/System/Library/CoreServices/RemoteManagement/ARDAgent.app/Contents/Resources/kickstart \
    -activate -configure -allowAccessFor -allUsers -restart -agent 2>/dev/null || true
SUDO_ON

    echo -e "  ${GREEN}✓ Services système activés${NC}"

    echo -e "${BOLD}[2/4] Clé SSH W.Alter...${NC}"
    mkdir -p "$SSH_DIR"
    chmod 700 "$SSH_DIR"

    if grep -qF "root@w-alter" "$AUTHORIZED_KEYS" 2>/dev/null; then
        echo -e "  ${GREEN}✓ Déjà présente${NC}"
    else
        cat "$SSH_KEY" >> "$AUTHORIZED_KEYS"
        chmod 600 "$AUTHORIZED_KEYS"
        echo -e "  ${GREEN}✓ Ajoutée${NC}"
    fi

    echo -e "${BOLD}[3/4] Tailscale...${NC}"
    if ! command -v tailscale &>/dev/null; then
        echo -e "  Installation en cours..."
        curl -fsSL https://tailscale.com/install.sh | sh
        echo -e "  ${GREEN}✓ Installé${NC}"
    else
        echo -e "  ${GREEN}✓ Déjà installé${NC}"
    fi

    if tailscale status &>/dev/null 2>&1; then
        echo -e "  ${GREEN}✓ Déjà connecté au tailnet${NC}"
    else
        echo ""
        echo -e "  ${YELLOW}⚠️  Connexion Tailscale requise.${NC}"
        echo -e "  ${DIM}Demandez à Lucas une clé d'auth ou le lien d'invitation.${NC}"
        echo ""
        read -r -p "  Collez la clé d'auth Tailscale (ou Entrée pour skip) : " AUTH_KEY
        if [[ -n "$AUTH_KEY" ]]; then
            sudo tailscale up --auth-key="$AUTH_KEY" --hostname="ami-walter" 2>/dev/null || {
                echo -e "  ${YELLOW}⚠ Auth key failed. Tentative sans clé...${NC}"
                sudo tailscale up --hostname="ami-walter" 2>/dev/null || true
            }
        else
            sudo tailscale up --hostname="ami-walter" 2>/dev/null || true
        fi
        echo -e "  ${GREEN}✓ Connecté${NC}"
    fi

    echo ""
    echo -e "${BOLD}[4/4] Informations de connexion${NC}"
    echo ""

    TS_IP=$(tailscale ip -4 2>/dev/null || echo "en attente...")
    TS_HOSTNAME=$(tailscale status --json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('Self',{}).get('HostName','?'))" 2>/dev/null || echo "?")

    echo -e "  ${BOLD}IP Tailscale  :${NC} ${CYAN}${TS_IP}${NC}"
    echo -e "  ${BOLD}Hostname      :${NC} ${CYAN}${TS_HOSTNAME}${NC}"
    echo ""

    osascript -e 'display notification "W.Alter a maintenant accès à ce Mac." with title "🟢 W.Alter Access"' 2>/dev/null || true

    echo -e "${GREEN}  ╔══════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}  ║     ✅  W.ALTER ACCESS — ACTIVÉ !       ║${NC}"
    echo -e "${GREEN}  ╚══════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  ${BOLD}Pour couper l'accès :${NC} relancez ce même fichier."
    echo ""
    echo -e "  ${DIM}ℹ️  Aucun tunnel sortant — c'est w-alter qui initie la connexion.${NC}"
    echo -e "  ${DIM}   Le réseau de Lucas est protégé.${NC}"
    echo ""

    open "x-apple.systempreferences:com.apple.preferences.sharing" 2>/dev/null || true
}

# ── MAIN ───────────────────────────────────────────────────────────────────

if [[ "$(uname)" != "Darwin" ]]; then
    echo -e "${RED}⚠ Ce script est pour macOS uniquement.${NC}"
    exit 1
fi

show_status
read -r

if is_active; then
    deactivate
else
    activate
fi
