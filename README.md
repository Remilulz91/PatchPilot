# PatchPilot 🛩️

**Centralized update management for your Linux fleet, from a simple web interface.**

PatchPilot connects to your **Debian / Ubuntu** machines over SSH (key-based) and runs — and only runs — these three commands:

- `apt update`
- `apt upgrade`
- `apt full-upgrade`

Update one machine with a single click, or the whole fleet at once, with real-time `apt` output in your browser.

> 🔜 More operating systems (RHEL/Rocky, openSUSE, Alpine…) will be supported in future versions.

## ✨ Features

- **Dashboard**: machine list, detected OS, status and date of the last update
- **One-click updates**: per machine, or an "Update all" button (parallel execution)
- **Real-time logs**: apt output streams live to the browser via WebSocket
- **Key-based SSH only**: dedicated ed25519 key, as root or a sudo-enabled user
- **Language switch**: English / French interface (EN/FR button)
- **Security**: login + mandatory **TOTP MFA** (Google Authenticator, Authy…), bcrypt password hashing, server-side sessions, brute-force protection, **strict command whitelist** (no arbitrary command can ever be sent), parameterized SQL queries
- **Automated installation**: one script, a few questions, and the site is online (HTTP, or HTTPS with Let's Encrypt)

## 📋 Requirements

- A **Debian 12+ or Ubuntu 22.04+** machine to host PatchPilot
- Root access on that machine
- For HTTPS: a domain name pointing to the machine (ports 80/443 open)
- Managed machines must be reachable over SSH from the PatchPilot server

## 🚀 Installation

```bash
git clone https://github.com/YOUR_ACCOUNT/patchpilot.git
cd patchpilot
sudo bash install.sh
```

The script asks for:

1. **Access mode**: `https` (recommended) or `http`
   - HTTPS → enter your **domain name** + an email (automatic Let's Encrypt certificate)
   - HTTP → enter the **IP address** of the host machine to use (detected IPs are listed)
2. The site **administrator account** (username + password)

A full **summary** is then displayed; type `yes` to confirm and everything installs automatically: packages, Python environment, dedicated SSH key, systemd service, nginx (and certificate for HTTPS). When it's done, just open the website.

### First login

1. Sign in with the admin account created during installation
2. Scan the **MFA QR code** with your authenticator app and confirm the code
3. You land on the dashboard

## 🖥️ Adding machines to manage

1. In the interface, click **"SSH public key"** and copy the key
2. On each machine to manage, authorize it for the chosen SSH user:

```bash
# As root:
echo 'ssh-ed25519 AAAA... patchpilot@server' >> /root/.ssh/authorized_keys

# Or for a regular user:
echo 'ssh-ed25519 AAAA... patchpilot@server' >> /home/USER/.ssh/authorized_keys
```

3. **For a non-root user**: allow only the 3 apt commands via passwordless sudo:

```bash
# On the managed machine, as root:
cat > /etc/sudoers.d/patchpilot <<'EOF'
USER ALL=(root) NOPASSWD: /usr/bin/apt-get update, /usr/bin/apt-get upgrade -y, /usr/bin/apt-get full-upgrade -y
EOF
chmod 440 /etc/sudoers.d/patchpilot
```

4. In PatchPilot: **"+ Add machine"** → name, IP/host, port, user → **"Test"** to check the connection and detect the OS

> ℹ️ Major version migrations (e.g. Debian 12 → 13) are intentionally **manual** and out of PatchPilot's scope.

## 🔄 Updating PatchPilot

```bash
cd patchpilot
git pull
sudo cp -r app requirements.txt /opt/patchpilot/
sudo /opt/patchpilot/venv/bin/pip install -q -r /opt/patchpilot/requirements.txt
sudo chown -R patchpilot:patchpilot /opt/patchpilot
sudo systemctl restart patchpilot
```

## 🛠️ Administration

```bash
systemctl status patchpilot        # service status
journalctl -u patchpilot -f        # service logs
sudo systemctl restart patchpilot  # restart
```

Data (SQLite database, SSH keys) lives in `/opt/patchpilot/data/` — **back it up**, and never publish it to GitHub (the `data/` folder is in `.gitignore`).

## 🔒 Security notes

- The fleet's private SSH key is stored on the PatchPilot server: protect this machine like a bastion (restricted access, kept up to date, firewalled)
- SSH host key verification is disabled by default (internal fleet). To harden: provide a `known_hosts` file in `app/ssh_manager.py`
- Prefer HTTPS; with HTTP, restrict access to the internal network / VPN
- Only 3 commands can be executed, hard-coded server-side — the interface cannot send any arbitrary command

## 📦 Tech stack

Python 3.10+ / FastAPI / asyncssh / SQLite / WebSocket — dependency-free HTML/CSS/JS frontend.

## 📄 License

MIT
