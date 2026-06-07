# PatchPilot 🛩️

**Gestion centralisée des mises à jour de votre parc Linux, depuis une simple interface web.**

PatchPilot se connecte en SSH (par clé) à vos machines **Debian / Ubuntu** et exécute — et uniquement — ces trois commandes :

- `apt update`
- `apt upgrade`
- `apt full-upgrade`

Mettez à jour une machine en un clic, ou tout le parc d'un coup, avec la sortie `apt` en temps réel dans votre navigateur.

> 🔜 D'autres systèmes (RHEL/Rocky, openSUSE, Alpine…) seront pris en charge dans de futures versions.

## ✨ Fonctionnalités

- **Tableau de bord** : liste des machines, OS détecté, statut et date de la dernière mise à jour
- **Mise à jour en un clic** : par machine, ou bouton « Tout mettre à jour » (exécution en parallèle)
- **Logs en temps réel** : la sortie d'apt s'affiche en direct via WebSocket
- **Connexion SSH par clé uniquement** : clé ed25519 dédiée, en root ou utilisateur avec sudo
- **Sécurité** : authentification + **MFA TOTP** obligatoire (Google Authenticator, Authy…), mots de passe bcrypt, sessions serveur, anti brute-force, **liste blanche stricte de commandes** (aucune commande arbitraire ne peut être envoyée), requêtes SQL paramétrées
- **Installation automatisée** : un seul script, quelques questions, et le site est en ligne (HTTP ou HTTPS avec Let's Encrypt)

## 📋 Prérequis

- Une machine **Debian 12+ ou Ubuntu 22.04+** pour héberger PatchPilot
- Accès root sur cette machine
- En HTTPS : un nom de domaine pointant vers la machine (ports 80/443 ouverts)
- Les machines à gérer doivent être accessibles en SSH depuis le serveur PatchPilot

## 🚀 Installation

```bash
git clone https://github.com/VOTRE_COMPTE/patchpilot.git
cd patchpilot
sudo bash install.sh
```

Le script vous demande :

1. **Mode d'accès** : `https` (recommandé) ou `http`
   - HTTPS → saisissez votre **nom de domaine** + un email (certificat Let's Encrypt automatique)
   - HTTP → saisissez l'**adresse IP** de la machine à utiliser (la liste des IP détectées s'affiche)
2. Le **compte administrateur** du site (nom d'utilisateur + mot de passe)

Un **résumé** complet s'affiche ensuite ; tapez `yes` pour valider et tout s'installe automatiquement : paquets, environnement Python, clé SSH dédiée, service systemd, nginx (et certificat si HTTPS). À la fin, vous n'avez plus qu'à ouvrir le site.

### Premier login

1. Connectez-vous avec le compte admin créé pendant l'installation
2. Scannez le **QR code MFA** avec votre application d'authentification et validez le code
3. Vous arrivez sur le tableau de bord

## 🖥️ Ajouter des machines à gérer

1. Dans l'interface, cliquez sur **« Clé publique SSH »** et copiez la clé
2. Sur chaque machine à gérer, ajoutez-la à l'utilisateur SSH choisi :

```bash
# En root :
echo 'ssh-ed25519 AAAA... patchpilot@serveur' >> /root/.ssh/authorized_keys

# Ou pour un utilisateur classique :
echo 'ssh-ed25519 AAAA... patchpilot@serveur' >> /home/UTILISATEUR/.ssh/authorized_keys
```

3. **Si utilisateur non-root** : autorisez uniquement les 3 commandes apt en sudo sans mot de passe :

```bash
# Sur la machine à gérer, en root :
cat > /etc/sudoers.d/patchpilot <<'EOF'
UTILISATEUR ALL=(root) NOPASSWD: /usr/bin/apt-get update, /usr/bin/apt-get upgrade -y, /usr/bin/apt-get full-upgrade -y
EOF
chmod 440 /etc/sudoers.d/patchpilot
```

4. Dans PatchPilot : **« + Ajouter une machine »** → nom, IP/hôte, port, utilisateur → **« Tester »** pour vérifier la connexion et détecter l'OS

> ℹ️ La migration de version majeure (ex : Debian 12 → 13) reste volontairement **manuelle** et hors périmètre de PatchPilot.

## 🔄 Mettre à jour PatchPilot

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
systemctl status patchpilot        # état du service
journalctl -u patchpilot -f        # logs du service
sudo systemctl restart patchpilot  # redémarrer
```

Les données (base SQLite, clés SSH) sont dans `/opt/patchpilot/data/` — **à sauvegarder**, et à ne jamais publier sur GitHub (le dossier `data/` est dans le `.gitignore`).

## 🔒 Notes de sécurité

- La clé privée SSH du parc est stockée sur le serveur PatchPilot : protégez cette machine comme un bastion (accès restreint, à jour, pare-feu)
- La vérification des clés d'hôte SSH est désactivée par défaut (parc interne). Pour durcir : renseigner un fichier `known_hosts` dans `app/ssh_manager.py`
- Préférez HTTPS ; en HTTP, réservez l'accès au réseau interne / VPN
- Seules 3 commandes sont exécutables, codées en dur côté serveur — l'interface ne peut envoyer aucune commande arbitraire

## 📦 Stack technique

Python 3.10+ / FastAPI / asyncssh / SQLite / WebSocket — frontend HTML/CSS/JS sans dépendance.

## 📄 Licence

MIT
