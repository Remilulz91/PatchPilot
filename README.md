# PatchPilot 🛩️

**Centralized update management for your Linux fleet, from a simple web interface.**

PatchPilot connects to your **Debian / Ubuntu** machines over SSH (key-based) and runs — and only runs — apt maintenance commands:

- `apt update`
- `apt upgrade`
- `apt full-upgrade`
- `apt autoremove`

One click runs the full maintenance sequence in order: **update → upgrade → autoremove**.

Update one machine with a single click, or the whole fleet at once, with real-time `apt` output in your browser.

> 🔜 More operating systems (RHEL/Rocky, openSUSE, Alpine…) will be supported in future versions.

## ✨ Features

- **Dashboard**: machine list, detected OS, status and date of the last update
- **One-click updates**: full maintenance sequence (update → upgrade → autoremove) per machine, or "Update all" (parallel execution)
- **Pending-updates indicator**: a "Check" action refreshes package lists and shows how many updates are waiting per machine
- **Scheduled updates**: admins can run the full sequence automatically on all machines, daily or weekly at a chosen time (in-app, no cron needed)
- **Real-time logs**: apt output streams live to the browser via WebSocket
- **Key-based SSH only**: dedicated ed25519 key, as root or a sudo-enabled user
- **Language switch**: English / French interface (EN/FR button)
- **Multi-user**: admins create accounts and share a one-time **activation link** (no mail server needed) — the invited user sets their own password, then their own MFA
- **MFA recovery codes**: 10 single-use backup codes generated when MFA is enabled, to log in if the authenticator is lost
- **Update check**: the dashboard shows whether your PatchPilot install is up to date against the latest GitHub release
- **Security**: login + mandatory **TOTP MFA** (Google Authenticator, Authy…), bcrypt password hashing, server-side sessions with token rotation, **CSRF protection** (double-submit token + SameSite=Strict), **SSH host-key verification** (trust on first use), security headers (CSP, HSTS, X-Frame-Options), brute-force protection, **strict command whitelist** (no arbitrary command can ever be sent), parameterized SQL queries
- **Automated installation**: one script, a few questions, and the site is online (HTTP, or HTTPS with Let's Encrypt)

## 📋 Requirements

- A **Debian 12+ or Ubuntu 22.04+** machine to host PatchPilot
- Root access on that machine
- For HTTPS: a domain name pointing to the machine (ports 80/443 open)
- Managed machines must be reachable over SSH from the PatchPilot server

## 🚀 Installation

```bash
git clone https://github.com/Remilulz91/patchpilot.git
cd patchpilot
sudo bash install.sh
```

The script asks for:

1. **Access mode**: `https` (recommended) or `http`
   - HTTPS → enter your **domain name** + an email (automatic Let's Encrypt certificate)
   - HTTP → enter the **IP address** of the host machine to use (detected IPs are listed)
2. The site **administrator account** (username + password)

The script also offers an optional **UFW firewall + fail2ban** hardening step (recommended for production): UFW allows only SSH and the web ports, and fail2ban bans IPs that brute-force SSH or the PatchPilot login page (5 failures / 10 min → 30 min ban).

A full **summary** is then displayed; type `yes` to confirm and everything installs automatically: packages, Python environment, dedicated SSH key, systemd service, nginx (and certificate for HTTPS, plus UFW/fail2ban if chosen). When it's done, just open the website.

### First login

1. Sign in with the admin account created during installation
2. Scan the **MFA QR code** with your authenticator app and confirm the code
3. **Save the 10 recovery codes** shown once (they let you log in if you lose your authenticator)
4. You land on the dashboard

### Adding more users (admins only)

1. Click **Users**, enter a username (tick *Administrator* to grant admin rights), and click **Create + get link**
2. Copy the generated **activation link** and send it to the person manually (any channel — it expires in 7 days)
3. They open the link, set their own password, then log in and set up their own MFA

Lost authenticator? On the login page, after your password, click **Use a recovery code** and enter one of your backup codes.

## 🖥️ Adding machines to manage

1. In the interface, click **"SSH public key"** and copy the key
2. On each machine to manage, authorize it for the chosen SSH user:

```bash
# As root:
mkdir -p /root/.ssh && chmod 700 /root/.ssh
echo 'ssh-ed25519 AAAA... patchpilot@server' >> /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys

# Or for a regular user (replace USER):
mkdir -p /home/USER/.ssh && chmod 700 /home/USER/.ssh
echo 'ssh-ed25519 AAAA... patchpilot@server' >> /home/USER/.ssh/authorized_keys
chmod 600 /home/USER/.ssh/authorized_keys
chown -R USER:USER /home/USER/.ssh
```

> The `mkdir`/`chmod` lines make this work even when the `.ssh` directory does not exist yet (e.g. a freshly created user). Without them, the redirect would fail with “No such file or directory”.

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
- SSH host keys are verified using trust-on-first-use: the first successful **Test** records each machine's key in `data/keys/known_hosts`, and later connections reject a changed key (possible MITM). If you legitimately rebuild/rekey a machine, remove its line from `data/keys/known_hosts` and click **Test** again
- The WebSocket enforces an `Origin` check against `PATCHPILOT_ORIGIN` (set automatically by `install.sh`)
- Prefer HTTPS; with HTTP, restrict access to the internal network / VPN
- Only 3 commands can be executed, hard-coded server-side — the interface cannot send any arbitrary command

## 📦 Tech stack

Python 3.10+ / FastAPI / asyncssh / SQLite / WebSocket — dependency-free HTML/CSS/JS frontend.

## 📄 License

Copyright © 2026 Remilulz91 — **All rights reserved.**

You are free to **install and use** PatchPilot anywhere, including in companies and production environments. However, this project remains the exclusive property of its author: claiming ownership or redistributing it by any means other than sharing the official repository link (https://github.com/Remilulz91/patchpilot) is strictly prohibited. See [LICENSE](LICENSE).
