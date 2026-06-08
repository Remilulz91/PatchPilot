#!/usr/bin/env bash
#=============================================================================
# PatchPilot — Automated installation script (Debian / Ubuntu)
#
# Usage: sudo bash install.sh   (run from the repository root)
#
# The script asks a few questions, shows a summary, asks for confirmation,
# then installs EVERYTHING automatically (Python, nginx, systemd, certbot
# when HTTPS is selected).
#=============================================================================
set -euo pipefail

INSTALL_DIR="/opt/patchpilot"
SERVICE_USER="patchpilot"
APP_PORT="8744"   # internal port (uvicorn), behind nginx

C_BLUE='\033[1;34m'; C_GREEN='\033[1;32m'; C_RED='\033[1;31m'; C_YELLOW='\033[1;33m'; C_RESET='\033[0m'
info()  { echo -e "${C_BLUE}[INFO]${C_RESET} $*"; }
ok()    { echo -e "${C_GREEN}[ OK ]${C_RESET} $*"; }
err()   { echo -e "${C_RED}[ERROR]${C_RESET} $*" >&2; }

#--- Prerequisites -----------------------------------------------------------
[[ $EUID -eq 0 ]] || { err "This script must be run as root (sudo bash install.sh)"; exit 1; }
[[ -f "requirements.txt" && -d "app" ]] || { err "Run this script from the PatchPilot repository root."; exit 1; }
command -v apt-get >/dev/null || { err "This script only works on Debian / Ubuntu."; exit 1; }

echo ""
echo -e "${C_BLUE}=============================================${C_RESET}"
echo -e "${C_BLUE}        PatchPilot installation${C_RESET}"
echo -e "${C_BLUE}=============================================${C_RESET}"
echo ""

#--- 1. Questions ------------------------------------------------------------
# HTTP or HTTPS
while true; do
    read -rp "Site access mode [https/http]: " MODE
    MODE=$(echo "$MODE" | tr '[:upper:]' '[:lower:]')
    [[ "$MODE" == "http" || "$MODE" == "https" ]] && break
    echo "Invalid answer. Type 'https' or 'http'."
done

if [[ "$MODE" == "https" ]]; then
    while true; do
        read -rp "Domain name (e.g. patchpilot.mydomain.com): " DOMAIN
        [[ "$DOMAIN" =~ ^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$ ]] && break
        echo "Invalid domain name."
    done
    read -rp "Email for the Let's Encrypt certificate: " LE_EMAIL
    SERVER_NAME="$DOMAIN"
    SITE_URL="https://$DOMAIN"
else
    echo ""
    echo "IP addresses detected on this machine:"
    hostname -I | tr ' ' '\n' | grep -v '^$' | sed 's/^/   - /'
    echo ""
    while true; do
        read -rp "IP address to use for the site: " HOST_IP
        [[ "$HOST_IP" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ ]] && break
        echo "Invalid IP address."
    done
    SERVER_NAME="$HOST_IP"
    SITE_URL="http://$HOST_IP"
fi

# Site administrator account
echo ""
while true; do
    read -rp "Site administrator username: " ADMIN_USER
    [[ -n "$ADMIN_USER" ]] && break
done
while true; do
    read -rsp "Administrator password (10 characters min): " ADMIN_PASS; echo ""
    if [[ ${#ADMIN_PASS} -lt 10 ]]; then echo "Too short (10 characters minimum)."; continue; fi
    read -rsp "Confirm password: " ADMIN_PASS2; echo ""
    [[ "$ADMIN_PASS" == "$ADMIN_PASS2" ]] && break
    echo "Passwords do not match."
done

#--- 2. Summary + confirmation ------------------------------------------------
echo ""
echo -e "${C_YELLOW}=============== INSTALLATION SUMMARY ===============${C_RESET}"
echo "  Mode                 : $MODE"
if [[ "$MODE" == "https" ]]; then
echo "  Domain               : $DOMAIN"
echo "  Let's Encrypt email  : $LE_EMAIL"
else
echo "  IP address           : $HOST_IP"
fi
echo "  Site URL             : $SITE_URL"
echo "  Install directory    : $INSTALL_DIR"
echo "  System user          : $SERVICE_USER (no shell)"
echo "  Site admin           : $ADMIN_USER (MFA set up on first login)"
echo ""
echo "  Will be installed/configured automatically:"
echo "   - Packages: python3, python3-venv, nginx$([[ "$MODE" == "https" ]] && echo ', certbot')"
echo "   - Application in $INSTALL_DIR (Python virtual environment)"
echo "   - Dedicated ed25519 SSH key (to authorize on your machines)"
echo "   - systemd service 'patchpilot' (starts on boot)"
echo "   - Nginx reverse proxy$([[ "$MODE" == "https" ]] && echo ' + Let'"'"'s Encrypt certificate')"
echo -e "${C_YELLOW}====================================================${C_RESET}"
echo ""
read -rp "Confirm installation? [yes/no]: " CONFIRM
[[ "$(echo "$CONFIRM" | tr '[:upper:]' '[:lower:]')" == "yes" ]] || { err "Installation cancelled."; exit 1; }

#--- 3. Installation -----------------------------------------------------------
info "Installing system packages..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip nginx openssh-client >/dev/null
[[ "$MODE" == "https" ]] && apt-get install -y -qq certbot python3-certbot-nginx >/dev/null
ok "Packages installed"

info "Creating system user '$SERVICE_USER'..."
id -u "$SERVICE_USER" &>/dev/null || useradd --system --home "$INSTALL_DIR" --shell /usr/sbin/nologin "$SERVICE_USER"

info "Copying the application to $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"
cp -r app requirements.txt "$INSTALL_DIR/"
mkdir -p "$INSTALL_DIR/data/keys"

info "Creating the Python environment..."
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --quiet --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install --quiet -r "$INSTALL_DIR/requirements.txt"
ok "Python dependencies installed"

info "Generating the dedicated SSH key (ed25519)..."
if [[ ! -f "$INSTALL_DIR/data/keys/id_ed25519" ]]; then
    ssh-keygen -t ed25519 -N "" -C "patchpilot@$(hostname)" -f "$INSTALL_DIR/data/keys/id_ed25519" -q
fi

info "Creating the site administrator account..."
cd "$INSTALL_DIR"
ADMIN_USERNAME="$ADMIN_USER" ADMIN_PASSWORD="$ADMIN_PASS" PATCHPILOT_DATA="$INSTALL_DIR/data" \
    "$INSTALL_DIR/venv/bin/python" -m app.create_admin
cd - >/dev/null

chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
chmod 700 "$INSTALL_DIR/data" "$INSTALL_DIR/data/keys"
chmod 600 "$INSTALL_DIR/data/keys/id_ed25519"

info "Creating the systemd service..."
COOKIE_SECURE=$([[ "$MODE" == "https" ]] && echo "1" || echo "0")
cat > /etc/systemd/system/patchpilot.service <<EOF
[Unit]
Description=PatchPilot - Centralized update management
After=network.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR
Environment=PATCHPILOT_DATA=$INSTALL_DIR/data
Environment=PATCHPILOT_COOKIE_SECURE=$COOKIE_SECURE
Environment=PATCHPILOT_ORIGIN=$SITE_URL
ExecStart=$INSTALL_DIR/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port $APP_PORT --proxy-headers --forwarded-allow-ips 127.0.0.1
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
ok "patchpilot service started"

info "Configuring nginx..."
cat > /etc/nginx/sites-available/patchpilot <<EOF
server {
    listen 80;
    server_name $SERVER_NAME;

    location / {
        proxy_pass http://127.0.0.1:$APP_PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$remote_addr;
        proxy_set_header X-Forwarded-Proto \$scheme;
        # WebSocket (real-time logs)
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
ok "Nginx configured"

if [[ "$MODE" == "https" ]]; then
    info "Requesting the Let's Encrypt certificate (the domain must point to this machine)..."
    certbot --nginx -d "$DOMAIN" -m "$LE_EMAIL" --agree-tos --non-interactive --redirect
    ok "HTTPS enabled with automatic redirect"
fi

#--- 4. Done -------------------------------------------------------------------
PUBKEY=$(cat "$INSTALL_DIR/data/keys/id_ed25519.pub")
echo ""
echo -e "${C_GREEN}=============================================${C_RESET}"
echo -e "${C_GREEN}   Installation completed successfully!${C_RESET}"
echo -e "${C_GREEN}=============================================${C_RESET}"
echo ""
echo "  Website     : $SITE_URL"
echo "  Login       : $ADMIN_USER (MFA will be set up on first login)"
echo ""
echo "  PatchPilot SSH public key (also visible in the web interface):"
echo ""
echo "    $PUBKEY"
echo ""
echo "  On EACH machine to manage, authorize this key:"
echo "    echo '$PUBKEY' >> ~/.ssh/authorized_keys"
echo ""
echo "  (For a non-root user, see the README for the sudo NOPASSWD setup.)"
echo ""
