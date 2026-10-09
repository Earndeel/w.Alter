#!/bin/bash
# =============================================================================
# W.ALTER ACCESS — Bouton ON/OFF
# Double-cliquez pour activer OU désactiver l'accès complet de W.Alter.
# Mot de passe admin demandé UNE SEULE FOIS.
#
# Détection automatique de l'état :
# - Si SSH + VNC sont actifs → propose OFF
# - Si inactifs → propose ON (installe Tailscale, configure SSH/VNC)
# =============================================================================

set -euo pipefail

# ── Configuration ──────────────────────────────────────────────────────────
WALTER_PUB_KEY_FILE="$(dirname "$0")/walter_key.pub"
TAILSCALE_AUTH_KEY="__TAILSCALE_AUTH_KEY__"  # ← REMPLACER par la clé générée
TAILSCALE_HOSTNAME="ami-walter"
LOG_FILE="/tmp/walter-access.log"

# ── Couleurs ───────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; DIM='\033[2m'; NC='\033[0m'

# ── Dépendances ────────────────────────────────────────────────────────────
install_tailscale() {
    if ! command -v tailscale &>/dev/null; then
        curl -fsSL https://tailscale.com/install.sh | sh
    fi
    if ! tailscale status &>/dev/null 2>&1; then
        sudo tailscale up --auth-key="$TAILSCALE_AUTH_KEY" --hostname="$TAILSCALE_HOSTNAME" 2>/dev/null || {
            sudo tailscale up --hostname="$TAILSCALE_HOSTNAME" 2>/dev/null || true
        }
    fi
}

# ── État ───────────────────────────────────────────────────────────────────
is_active() {
    systemsetup -getremotelogin 2>/dev/null | grep -q "On"
}

# ── Affichage ──────────────────────────────────────────────────────────────
show_status() {
    clear
    if is_active; then
        echo ""
        echo -e "${GREEN}${BOLD} ╔══════════════════════════════════════════╗${NC}"
        echo -e "${GREEN}${BOLD} ║       W.ALTER ACCESS — ACTIVÉ            ║${NC}"
        echo -e "${GREEN}${BOLD} ╚══════════════════════════════════════════╝${NC}"
        echo ""
        TS_IP=$(tailscale ip -4 2>/dev/null || echo "inconnue")
        echo -e "  ${DIM}IP Tailscale :${NC} ${BOLD}${TS_IP}${NC}"
        echo -e "  ${DIM}SSH :${NC}          ${GREEN}activé${NC}"
        echo -e "  ${DIM}Partage d'écran :${NC} ${GREEN}activé${NC}"
        echo ""
        echo -e "  ${YELLOW}⚠️  Ne fermez PAS ce terminal tant que Lucas travaille.${NC}"
        echo ""
    else
        echo ""
        echo -e "${YELLOW}${BOLD} ╔══════════════════════════════════════════╗${NC}"
        echo -e "${YELLOW}${BOLD} ║       W.ALTER ACCESS — DÉSACTIVÉ         ║${NC}"
        echo -e "${YELLOW}${BOLD} ╚══════════════════════════════════════════╝${NC}"
        echo ""
        echo -e "  ${DIM}L'accès distant est coupé.${NC}"
        echo ""
    fi
}

# ── Activation ─────────────────────────────────────────────────────────────
activate() {
    echo -e "${BOLD}Activation de l'accès W.Alter...${NC}"
    echo ""

    # Phase 1 : sudo
    echo -e "${BOLD}[1/4] Authentification...${NC}"
    sudo -v

    # Phase 2 : SSH + VNC
    echo -e "${BOLD}[2/4] Activation SSH + Partage d'écran...${NC}"
    sudo systemsetup -setremotelogin on 2>/dev/null || true
    sudo /System/Library/CoreServices/RemoteManagement/ARDAgent.app/Contents/Resources/kickstart \
        -activate -configure -allowAccessFor -allUsers -privs -all \
        -clientopts -setmenuextra -menuextra yes 2>/dev/null || true

    SSH_KEY="$WALTER_PUB_KEY_FILE"
    AUTHORIZED_KEYS="$HOME/.ssh/authorized_keys"
    mkdir -p "$HOME/.ssh"
    chmod 700 "$HOME/.ssh"

    if [ -f "$SSH_KEY" ]; then
        if ! grep -qF "$(cat "$SSH_KEY")" "$AUTHORIZED_KEYS" 2>/dev/null; then
            cat "$SSH_KEY" >> "$AUTHORIZED_KEYS"
            chmod 600 "$AUTHORIZED_KEYS"
            echo -e " ${GREEN}✓ Clé SSH ajoutée${NC}"
        fi
    fi

    # Phase 3 : Tailscale
    echo -e "${BOLD}[3/4] Tailscale...${NC}"
    install_tailscale
    echo -e " ${GREEN}✓ Connecté${NC}"

    # Phase 4 : IP
    echo -e "${BOLD}[4/4] IP Tailscale...${NC}"
    sleep 3
    TS_IP=$(tailscale ip -4 2>/dev/null || echo "inconnue")
    echo -e " ${GREEN}✓ IP : ${BOLD}${TS_IP}${NC}"

    echo ""
    echo -e "${GREEN}${BOLD}╔════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}${BOLD}║  ACCÈS ACTIVÉ — IP : ${TS_IP}  ║${NC}"
    echo -e "${GREEN}${BOLD}╚════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e " ${YELLOW}⚠️  Gardez ce terminal ouvert.${NC}"
    echo ""
    read -r -p " Appuyez sur Entrée pour quitter (l'accès reste actif)..."
}

# ── Désactivation ──────────────────────────────────────────────────────────
deactivate() {
    echo -e "${YELLOW}${BOLD}Désactivation de l'accès W.Alter...${NC}"
    echo ""

    sudo -v
    sudo systemsetup -setremotelogin off 2>/dev/null || true
    sudo /System/Library/CoreServices/RemoteManagement/ARDAgent.app/Contents/Resources/kickstart \
        -deactivate -stop 2>/dev/null || true

    echo -e " ${GREEN}✓ SSH désactivé${NC}"
    echo -e " ${GREEN}✓ Partage d'écran désactivé${NC}"
    echo ""
    echo -e "${GREEN}${BOLD}Accès coupé.${NC}"
    echo ""
    read -r -p " Appuyez sur Entrée pour fermer..."
}

# ── Main ───────────────────────────────────────────────────────────────────
show_status

if is_active; then
    echo -ne " ${YELLOW}Voulez-vous DÉSACTIVER l'accès ? (o/N) : ${NC}"
    read -r REPLY
    if [[ "$REPLY" =~ ^[oO] ]]; then
        deactivate
    fi
else
    echo -ne " ${GREEN}Voulez-vous ACTIVER l'accès ? (O/n) : ${NC}"
    read -r REPLY
    if [[ -z "$REPLY" ]] || [[ "$REPLY" =~ ^[oO] ]]; then
        activate
    fi
fi
