#!/bin/bash
# =============================================================================
# W.ALTER ACCESS — Off Switch
# Coupe immédiatement tout accès distant au Mac
# =============================================================================
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

LAUNCHD_LABEL="com.walter.keepalive"
LAUNCHD_PLIST="$HOME/Library/LaunchAgents/${LAUNCHD_LABEL}.plist"

clear
echo ""
echo -e "${RED}${BOLD}  ╔══════════════════════════════════════════╗${NC}"
echo -e "${RED}${BOLD}  ║     🔒  W.ALTER ACCESS — OFF SWITCH      ║${NC}"
echo -e "${RED}${BOLD}  ║      Coupe tout accès distant            ║${NC}"
echo -e "${RED}${BOLD}  ╚══════════════════════════════════════════╝${NC}"
echo ""

# 1. Désactive Screen Sharing (VNC + ARD)
echo -e "${BOLD}[1/4] Désactivation du Screen Sharing...${NC}"
sudo /System/Library/CoreServices/RemoteManagement/ARDAgent.app/Contents/Resources/kickstart \
    -deactivate -stop 2>/dev/null && echo "  ✓ Screen Sharing désactivé" || echo "  (déjà désactivé ou non configuré)"

# 2. Décharge le tunnel persistant
echo -e "${BOLD}[2/4] Coupure du tunnel...${NC}"
if [[ -f "$LAUNCHD_PLIST" ]]; then
    launchctl unload "$LAUNCHD_PLIST" 2>/dev/null && echo "  ✓ Tunnel coupé" || echo "  (tunnel non actif)"
    rm -f "$LAUNCHD_PLIST"
else
    echo "  (pas de tunnel configuré)"
fi

# 3. Tue les sessions SSH entrantes
echo -e "${BOLD}[3/4] Fermeture des connexions actives...${NC}"
SSH_PIDS=$(pgrep -f "sshd:.*@.*" 2>/dev/null || true)
if [[ -n "$SSH_PIDS" ]]; then
    echo "$SSH_PIDS" | xargs sudo kill 2>/dev/null || true
    echo "  ✓ Sessions SSH fermées"
else
    echo "  (aucune session active)"
fi

# 4. Optionnel : désactive Remote Login (SSH)
echo -e "${BOLD}[4/4] Désactivation du Remote Login...${NC}"
sudo systemsetup -setremotelogin off 2>/dev/null && echo "  ✓ Remote Login désactivé" || echo "  (vérifiez dans Préférences Système > Partage)"

echo ""
echo -e "${GREEN}${BOLD}  ╔══════════════════════════════════════════╗${NC}"
echo -e "${GREEN}${BOLD}  ║       ✅  ACCÈS COUPÉ AVEC SUCCÈS       ║${NC}"
echo -e "${GREEN}${BOLD}  ╚══════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${BOLD}W.Alter n'a plus accès à ce Mac.${NC}"
echo ""
echo -e "  Pour réactiver : relancez ${CYAN}install.command${NC}"
echo ""

osascript -e 'display notification "W.Alter n'\''a plus accès à ce Mac." with title "🔒 Accès coupé"' 2>/dev/null || true
