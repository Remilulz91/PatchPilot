#!/usr/bin/env bash
#=============================================================================
# PatchPilot — Script d'installation automatisé (Debian / Ubuntu)
#
# Usage : sudo bash install.sh   (à lancer depuis la racine du dépôt)
#
# Ce script pose quelques questions, affiche un résumé, demande confirmation,
# puis installe TOUT automatiquement (Python, nginx, systemd, certbot si HTTPS).
#=============================================================================
set -euo pipefail

INSTALL_DIR="/opt/patchpilot"
SERVICE_USER="patchpilot"
APP_PORT="8744"   # port interne (uvicorn), derrière nginx

C_BLUE='\033[1;34m'; C_GREEN='\033[1;32m'; C_RED='\033[1;31m'; C_YELLOW='\033[1;33m'; C_RESET='\033[0m'
info()  { echo -e "${C_BLUE}[INFO]${C_RESET} $*"; }
ok()    { echo -e "${C_GREEN}[ OK ]${C_RESET} $*"; }
err()   { echo -e "${C_RED}[ERREUR]${C_RESET} $*" >&2; }

#--- Pré-requis -------------------------------------------------------------
[[ $EUID -eq 0 ]] || { err "Ce script doit être lancé en root (sudo bash install.sh)"; exit 1; }
[[ -f "requirements.txt" && -d "app" ]] || { err "Lancez ce script depuis la racine du dépôt PatchPilot."; exit 1; }
command -v apt-get >/dev/null || { err "Ce script ne fonctionne que sur Debian / Ubuntu."; exit 1; }

echo ""
echo -e "${C_BLUE}=============================================${C_RESET}"
echo -e "${C_BLUE}      Installation de PatchPilot${C_RESET}"
echo -e "${C_BLUE}=============================================${C_RESET}"
echo ""

#--- 1. Questions -----------------------------------------------------------
# HTTP ou HTTPS
while true; do
    read -rp "Mode d'accès au site [https/http] : " MODE
    MODE=$(echo "$MODE" | tr '[:upper:]' '[:lower:]')
    [[ "$MODE" == "http" || "$MODE" == "https" ]] && break
    echo "Réponse invalide. Tapez 'https' ou 'http'."
done

if [[ "$MODE" == "https" ]]; then
    while true; do
        read -rp "Nom de domaine (ex: patchpilot.mondomaine.fr) : " DOMAIN
        [[ "$DOMAIN" =~ ^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$ ]] && break
        echo "Nom de domaine invalide."
    done
    read -rp "Email pour le certificat Let's Encrypt : " LE_EMAIL
    SERVER_NAME="$DOMAIN"
    SITE_URL="https://$DOMAIN"
else
    echo ""
    echo "Adresses IP détectées sur cette machine :"
    hostname -I | tr ' ' '\n' | grep -v '^$' | sed 's/^/   - /'
    echo ""
    while true; do
        read -rp "Adresse IP à utiliser pour le site : " HOST_IP
        [[ "$HOST_IP" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ ]] && break
        echo "Adresse IP invalide."
    done
    SERVER_NAME="$HOST_IP"
    SITE_URL="http://$HOST_IP"
fi

# Compte administrateur du site
echo ""
while true; do
    read -rp "Nom d'utilisateur administrateur du site : " ADMIN_USER
    [[ -n "$ADMIN_USER" ]] && break
done
while true; do
    read -rsp "Mot de passe administrateur (10 caractères min) : " ADMIN_PASS; echo ""
    if [[ ${#ADMIN_PASS} -lt 10 ]]; then echo "Trop court (10 caractères minimum)."; continue; fi
    read -rsp "Confirmez le mot de passe : " ADMIN_PASS2; echo ""
    [[ "$ADMIN_PASS" == "$ADMIN_PASS2" ]] && break
    echo "Les mots de passe ne correspondent pas."
done

#--- 2. Résumé + validation -------------------------------------------------
echo ""
echo -e "${C_YELLOW}=============== RÉSUMÉ DE L'INSTALLATION ===============${C_RESET}"
echo "  Mode                  : $MODE"
if [[ "$MODE" == "https" ]]; then
echo "  Domaine               : $DOMAIN"
echo "  Email Let's Encrypt   : $LE_EMAIL"
else
echo "  Adresse IP            : $HOST_IP"
fi
echo "  URL du site           : $SITE_URL"
echo "  Dossier d'install     : $INSTALL_DIR"
echo "  Utilisateur système   : $SERVICE_USER (sans shell)"
echo "  Admin du site         : $ADMIN_USER (MFA configuré au 1er login)"
echo ""
echo "  Sera installé/configuré automatiquement :"
echo "   - Paquets : python3, python3-venv, nginx$([[ "$MODE" == "https" ]] && echo ', certbot')"
echo "   - Application dans $INSTALL_DIR (environnement virtuel Python)"
echo "   - Clé SSH ed25519 dédiée (à autoriser sur vos machines)"
echo "   - Service systemd 'patchpilot' (démarrage automatique)"
echo "   - Nginx en reverse proxy$([[ "$MODE" == "https" ]] && echo ' + certificat Let'"'"'s Encrypt')"
echo -e "${C_YELLOW}========================================================${C_RESET}"
echo ""
read -rp "Confirmer l'installation ? [yes/no] : " CONFIRM
[[ "$(echo "$CONFIRM" | tr '[:upper:]' '[:lower:]')" == "yes" ]] || { err "Installation annulée."; exit 1; }

#--- 3. Installation --------------------------------------------------------
info "Installation des paquets système..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip nginx openssh-client >/dev/null
[[ "$MODE" == "https" ]] && apt-get install -y -qq certbot python3-certbot-nginx >/dev/null
ok "Paquets installés"

info "Création de l'utilisateur système '$SERVICE_USER'..."
id -u "$SERVICE_USER" &>/dev/null || useradd --system --home "$INSTALL_DIR" --shell /usr/sbin/nologin "$SERVICE_USER"

info "Copie de l'application vers $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"
cp -r app requirements.txt "$INSTALL_DIR/"
mkdir -p "$INSTALL_DIR/data/keys"

info "Création de l'environnement Python..."
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --quiet --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install --quiet -r "$INSTALL_DIR/requirements.txt"
ok "Dépendances Python installées"

info "Génération de la clé SSH dédiée (ed25519)..."
if [[ ! -f "$INSTALL_DIR/data/keys/id_ed25519" ]]; then
    ssh-keygen -t ed25519 -N "" -C "patchpilot@$(hostname)" -f "$INSTALL_DIR/data/keys/id_ed25519" -q
fi

info "Création du compte administrateur du site..."
cd "$INSTALL_DIR"
ADMIN_USERNAME="$ADMIN_USER" ADMIN_PASSWORD="$ADMIN_PASS" PATCHPILOT_DATA="$INSTALL_DIR/data" \
    "$INSTALL_DIR/venv/bin/python" -m app.create_admin
cd - >/dev/null

chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
chmod 700 "$INSTALL_DIR/data" "$INSTALL_DIR/data/keys"
chmod 600 "$INSTALL_DIR/data/keys/id_ed25519"

info "Création du service systemd..."
COOKIE_SECURE=$([[ "$MODE" == "https" ]] && echo "1" || echo "0")
cat > /etc/systemd/system/patchpilot.service <<EOF
[Unit]
Description=PatchPilot - Gestion centralisée des mises à jour
After=network.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR
Environment=PATCHPILOT_DATA=$INSTALL_DIR/data
Environment=PATCHPILOT_COOKIE_SECURE=$COOKIE_SECURE
ExecStart=$INSTALL_DIR/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port $APP_PORT
Restart=on-failure
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=$INSTALL_DIR/data
ProtectHome=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now patchpilot >/dev/null 2>&1
ok "Service patchpilot démarré"

info "Configuration de nginx..."
cat > /etc/nginx/sites-available/patchpilot <<EOF
server {
    listen 80;
    server_name $SERVER_NAME;

    location / {
        proxy_pass http://127.0.0.1:$APP_PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-Proto \$scheme;
        # WebSocket (logs en temps réel)
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 3700s;
    }
}
EOF
ln -sf /etc/nginx/sites-available/patchpilot /etc/nginx/sites-enabled/patchpilot
rm -f /etc/nginx/sites-enabled/default
nginx -t -q && systemctl reload nginx
ok "Nginx configuré"

if [[ "$MODE" == "https" ]]; then
    info "Obtention du certificat Let's Encrypt (le domaine doit pointer vers cette machine)..."
    certbot --nginx -d "$DOMAIN" -m "$LE_EMAIL" --agree-tos --non-interactive --redirect
    ok "HTTPS activé avec redirection automatique"
fi

#--- 4. Fin -----------------------------------------------------------------
PUBKEY=$(cat "$INSTALL_DIR/data/keys/id_ed25519.pub")
echo ""
echo -e "${C_GREEN}=============================================${C_RESET}"
echo -e "${C_GREEN}   Installation terminée avec succès !${C_RESET}"
echo -e "${C_GREEN}=============================================${C_RESET}"
echo ""
echo "  Site web      : $SITE_URL"
echo "  Connexion     : $ADMIN_USER (le MFA sera configuré au premier login)"
echo ""
echo "  Clé publique SSH de PatchPilot (aussi visible dans l'interface web) :"
echo ""
echo "    $PUBKEY"
echo ""
echo "  Sur CHAQUE machine à gérer, ajoutez cette clé :"
echo "    echo '$PUBKEY' >> ~/.ssh/authorized_keys"
echo ""
echo "  (Pour un utilisateur non-root, voir le README pour la config sudo NOPASSWD.)"
echo ""
