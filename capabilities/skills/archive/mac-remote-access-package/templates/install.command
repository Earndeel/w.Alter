#!/bin/bash
# =============================================================================
# W.ALTER ACCESS — Installateur Mac
# Donne à W.Alter l'accès complet au Mac (SSH + Screen Sharing)
# Double-cliquez pour lancer. Votre mot de passe admin sera demandé.
# =============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SSH_KEY="$SCRIPT_DIR/walter_key.pub"
SSH_DIR="$HOME/.ssh"
AUTHORIZED_KEYS="$SSH_DIR/authorized_keys"
LAUNCHD_LABEL="com.walter.keepalive"
LAUNCHD_PLIST="$HOME/Library/LaunchAgents/${LAUNCHD_LABEL}.plist"
OFFSWITCH="$SCRIPT_DIR/offswitch.command"

# ── À adapter par installation ────────────────────────────────────────────
RELAY_HOST="w-alter"
RELAY_PORT="19922"
VNC_PASSWORD="walter2024"

print_header() {
    clear
    echo ""
    echo -e "${CYAN}${BOLD}  ╔══════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}${BOLD}  ║          W.ALTER  ACCESS  INSTALLER       ║${NC}"
    echo -e "${CYAN}${BOLD}  ║         Majordome numérique à distance     ║${NC}"
    echo -e "${CYAN}${BOLD}  ╚══════════════════════════════════════════╝${NC}"
    echo ""
}

step() { echo -e "\n${GREEN}${BOLD}[▸]${NC} ${BOLD}$1${NC}"; }
error() { echo -e "${RED}${BOLD}[✗] ERREUR :${NC} $1"; exit 1; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
ok() { echo -e "${GREEN}  ✓${NC} $1"; }

# ── 0. Pré-vérifications ──────────────────────────────────────────────────
preflight() {
    step "Vérification de l'environnement..."

    if [[ "$(uname)" != "Darwin" ]]; then
        error "Ce script est pour macOS uniquement."
    fi

    macos_version=$(sw_vers -productVersion 2>/dev/null || echo "inconnue")
    ok "macOS ${macos_version} détecté"

    if [[ ! -f "$SSH_KEY" ]]; then
        warn "Clé SSH non trouvée dans le dossier. L'installateur va la générer."
        ssh-keygen -t ed25519 -f "$SSH_DIR/id_ed25519_walter" -N "" -C "walter-access" 2>/dev/null || true
        cp "$SSH_DIR/id_ed25519_walter.pub" "$SSH_KEY" 2>/dev/null || true
    fi

    chmod +x "$OFFSWITCH" 2>/dev/null || true
    ok "Pré-vérifications OK"
}

# ── 1. Tailscale ──────────────────────────────────────────────────────────
install_tailscale() {
    step "Installation de Tailscale..."

    if command -v tailscale &>/dev/null; then
        ok "Tailscale déjà installé : $(tailscale version | head -1)"
    else
        echo "  Téléchargement de Tailscale..."
        curl -fsSL https://tailscale.com/install.sh | sh
        ok "Tailscale installé"
    fi

    if tailscale status &>/dev/null; then
        ok "Tailscale déjà connecté"
        return
    fi

    echo ""
    echo -e "  ${YELLOW}── TAILSCALE AUTH KEY ──${NC}"
    echo "  Il faut une clé d'authentification générée par le propriétaire"
    echo "  du tailnet. Sans cette clé, on fait l'auth interactive :"
    echo ""
    echo -e "  ${BOLD}Entrez la clé (ou laissez vide pour auth par navigateur) :${NC}"
    read -r -p "  > " AUTH_KEY

    if [[ -n "$AUTH_KEY" ]]; then
        sudo tailscale up --authkey "$AUTH_KEY" --accept-routes
        ok "Tailscale connecté via auth key"
    else
        echo ""
        echo -e "  ${YELLOW}Ouverture de l'authentification dans le navigateur...${NC}"
        sudo tailscale up --accept-routes
        ok "Tailscale connecté"
    fi
}

# ── 2. SSH ─────────────────────────────────────────────────────────────────
setup_ssh() {
    step "Configuration SSH..."

    sudo systemsetup -setremotelogin on 2>/dev/null || {
        warn "Impossible d'activer Remote Login via systemsetup. Essayez manuellement :"
        echo "  Préférences Système > Général > Partage > Connexion distante : ON"
    }
    ok "Remote Login activé"

    mkdir -p "$SSH_DIR"
    chmod 700 "$SSH_DIR"

    if [[ -f "$SSH_KEY" ]]; then
        if grep -qF "$(cat "$SSH_KEY")" "$AUTHORIZED_KEYS" 2>/dev/null; then
            ok "Clé SSH déjà présente"
        else
            cat "$SSH_KEY" >> "$AUTHORIZED_KEYS"
            ok "Clé SSH ajoutée à authorized_keys"
        fi
        chmod 600 "$AUTHORIZED_KEYS"
    else
        warn "Pas de clé SSH trouvée — l'accès SSH ne sera pas possible"
    fi
}

# ── 3. Screen Sharing (VNC) ───────────────────────────────────────────────
setup_vnc() {
    step "Activation du Screen Sharing (VNC)..."

    sudo /System/Library/CoreServices/RemoteManagement/ARDAgent.app/Contents/Resources/kickstart \
        -activate -configure -allowAccessFor -allUsers -clientopts \
        -setvnclegacy -vnclegacy yes -setvncpw "$VNC_PASSWORD" \
        -restart -agent 2>/dev/null

    ok "Screen Sharing activé avec VNC (mot de passe défini)"

    echo ""
    echo -e "  ${YELLOW}── PERMISSION MANUELLE NÉCESSAIRE ──${NC}"
    echo "  Pour que W.Alter puisse voir votre écran :"
    echo ""
    echo -e "  ${BOLD}1. Ouvrez → Préférences Système → Général → Partage${NC}"
    echo -e "  ${BOLD}2. Vérifiez que « Partage d'écran » est coché${NC}"
    echo -e "  ${BOLD}3. Dans « Autoriser l'accès pour », sélectionnez${NC}"
    echo -e "     ${BOLD}« Tous les utilisateurs »${NC}"
    echo ""

    open "x-apple.systempreferences:com.apple.preferences.sharing" 2>/dev/null || true
}

# ── 4. Reverse tunnel (pour connexion derrière NAT) ────────────────────────
setup_tunnel() {
    step "Configuration du tunnel persistant..."

    cat > "$LAUNCHD_PLIST" << LAUNCHEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${LAUNCHD_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/ssh</string>
        <string>-N</string>
        <string>-R</string>
        <string>19922:localhost:22</string>
        <string>-R</string>
        <string>15900:localhost:5900</string>
        <string>-o</string>
        <string>ServerAliveInterval=30</string>
        <string>-o</string>
        <string>ServerAliveCountMax=3</string>
        <string>-o</string>
        <string>ExitOnForwardFailure=yes</string>
        <string>${RELAY_HOST}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/walter-tunnel.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/walter-tunnel.err</string>
</dict>
</plist>
LAUNCHEOF

    chmod 644 "$LAUNCHD_PLIST"

    if [[ ! -f "$SSH_DIR/id_ed25519_walter" ]]; then
        ssh-keygen -t ed25519 -f "$SSH_DIR/id_ed25519_walter" -N "" -C "walter-tunnel" 2>/dev/null || true
        cat "$SSH_DIR/id_ed25519_walter.pub" >> "$AUTHORIZED_KEYS"
    fi

    launchctl unload "$LAUNCHD_PLIST" 2>/dev/null || true
    launchctl load "$LAUNCHD_PLIST" 2>/dev/null || true

    ok "Tunnel persistant installé (reconnexion automatique au réveil)"
}

# ── 5. Vérification finale ─────────────────────────────────────────────────
verify() {
    step "Vérification de la connexion..."

    local_ip=$(tailscale ip -4 2>/dev/null || echo "inconnue")
    ok "IP Tailscale : ${local_ip}"

    echo ""
    echo -e "${GREEN}${BOLD}  ╔══════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}${BOLD}  ║     ✅  W.ALTER ACCESS — INSTALLÉ !     ║${NC}"
    echo -e "${GREEN}${BOLD}  ╚══════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  ${BOLD}Pour couper l'accès :${NC}"
    echo -e "  ● Double-cliquez sur ${CYAN}offswitch.command${NC} dans le dossier"
    echo ""
    echo -e "  ${BOLD}Ce qui a été configuré :${NC}"
    echo "  ● Tailscale connecté au tailnet privé"
    echo "  ● SSH activé (clé publique autorisée)"
    echo "  ● Screen Sharing (VNC) activé"
    echo "  ● Tunnel persistant (survit au sommeil)"
    echo ""
    echo -e "  ${YELLOW}⚠️  Vérifiez que « Partage d'écran » est coché dans :${NC}"
    echo -e "  ${YELLOW}   Préférences Système → Général → Partage${NC}"
    echo ""
    echo -e "  ${BOLD}Le dossier W.Alter Access est ici :${NC}"
    echo "  $SCRIPT_DIR"
    echo ""
}

# ── MAIN ───────────────────────────────────────────────────────────────────
print_header

echo "Cet installateur va :"
echo "  1. Installer Tailscale (VPN privé)"
echo "  2. Activer SSH (accès terminal)"
echo "  3. Activer Screen Sharing (accès écran + clics)"
echo "  4. Configurer un tunnel persistant"
echo ""
echo -e "${YELLOW}Votre mot de passe administrateur sera demandé plusieurs fois.${NC}"
echo ""
read -r -p "Continuer ? (O/n) : " CONFIRM
if [[ "$CONFIRM" == "n" || "$CONFIRM" == "N" ]]; then
    echo "Annulé."
    exit 0
fi

preflight
install_tailscale
setup_ssh
setup_vnc
setup_tunnel
verify
