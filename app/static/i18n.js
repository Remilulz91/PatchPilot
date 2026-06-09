/* PatchPilot — i18n (English / French) */
"use strict";

const I18N = {
  en: {
    subtitle: "Centralized update management",
    username: "Username",
    password: "Password",
    mfa_code: "MFA code (6 digits)",
    sign_in: "Sign in",
    enter_mfa: "Enter your MFA code.",
    network_error: "Network error",
    error: "Error",

    mfa_title: "Set up your MFA",
    mfa_sub: "Scan this QR code with your authenticator app (Google Authenticator, Authy, 2FAS…) then enter the generated code.",
    mfa_intro: "One-time setup to secure your account. You will need an authenticator app.",
    mfa_step1: "Install an authenticator app on your phone (Google Authenticator, Microsoft Authenticator, Authy, 2FAS…).",
    mfa_step2: "Scan the QR code below with that app (or enter the key manually).",
    mfa_step3: "Type the 6-digit code the app shows and click “Enable MFA”.",
    manual_key: "Or enter the key manually:",
    six_digit_code: "6-digit code",
    enable_mfa: "Enable MFA",
    invalid_code: "Invalid code",

    ssh_pubkey: "SSH public key",
    logout: "Log out",
    add_machine: "+ Add machine",
    action: "Action:",
    update_all: "⟳ Update all",
    th_machine: "Machine",
    th_os: "OS",
    th_status: "Status",
    th_last: "Last action",
    th_actions: "Actions",
    empty: "No machines yet. Click “Add machine”, then authorize PatchPilot's SSH public key on it.",
    console_hint: "— Console: apt output will appear here in real time —",

    add_title: "Add a machine",
    name_label: "Name (label)",
    host_label: "IP address or hostname",
    port_label: "SSH port",
    user_label: "SSH user (root or sudo-enabled user)",
    cancel: "Cancel",
    add: "Add",

    key_title: "PatchPilot SSH public key",
    key_hint: "Add it to ~/.ssh/authorized_keys of the SSH user on each managed machine:",
    key_missing: "Key not found — re-run install.sh",
    copy: "Copy",
    close: "Close",

    badge_running: "running…",
    badge_ok: "OK",
    badge_error: "error",
    badge_never: "never run",
    run: "Run",
    test: "Test",
    confirm_delete: "Delete “{name}”?",
    confirm_all: "Run “{action}” on ALL machines?",
    started_count: "Update started on {n} machine(s).",
    conn_ok: "Connection OK — {os}",
    conn_fail: "Failed: {err}",
    job_started: "▶ {action} started",
    job_done: "✔ {action} finished",
    job_failed: "✖ failed: {err}",
    unknown_error: "unknown error",
    up_to_date: "up to date",
    update_available: "update available: {v}",

    use_recovery: "Use a recovery code",
    use_totp: "Use your authenticator code",
    recovery_code: "Recovery code",

    rc_title: "Save your recovery codes",
    rc_intro: "If you lose access to your authenticator app, each of these one-time codes lets you log in. Store them somewhere safe.",
    rc_warn: "They are shown only once. Each code works a single time.",
    rc_continue: "I saved them — continue",

    users: "Users",
    users_title: "User management",
    u_th_user: "User",
    u_th_role: "Role",
    u_th_status: "Status",
    u_add_title: "Create a user",
    u_name_ph: "username",
    u_make_admin: "Administrator",
    u_create: "Create + get link",
    u_invite_hint: "Copy this activation link and send it to the user (it expires in 7 days). They will set their own password:",
    u_role_admin: "Admin",
    u_role_user: "User",
    u_pending: "pending",
    u_active: "active",
    u_relink: "New link",
    u_confirm_delete: "Delete this user?",

    act_title: "Activate your account",
    act_intro: "Welcome {user}. Choose a password to activate your account.",
    act_password: "Password (10 characters min)",
    act_password2: "Confirm password",
    act_submit: "Activate my account",
    act_invalid: "This activation link is invalid or has expired. Ask your administrator for a new one.",
    act_too_short: "Password too short (10 characters minimum).",
    act_mismatch: "Passwords do not match.",
    act_done: "Account activated! Redirecting to the login page…",
  },
  fr: {
    subtitle: "Gestion centralisée des mises à jour",
    username: "Nom d'utilisateur",
    password: "Mot de passe",
    mfa_code: "Code MFA (6 chiffres)",
    sign_in: "Se connecter",
    enter_mfa: "Saisissez votre code MFA.",
    network_error: "Erreur réseau",
    error: "Erreur",

    mfa_title: "Configurez votre MFA",
    mfa_sub: "Scannez ce QR code avec votre application d'authentification (Google Authenticator, Authy, 2FAS…) puis saisissez le code généré.",
    mfa_intro: "Configuration unique pour sécuriser votre compte. Vous aurez besoin d'une application d'authentification.",
    mfa_step1: "Installez une application d'authentification sur votre téléphone (Google Authenticator, Microsoft Authenticator, Authy, 2FAS…).",
    mfa_step2: "Scannez le QR code ci-dessous avec cette application (ou saisissez la clé manuellement).",
    mfa_step3: "Saisissez le code à 6 chiffres affiché par l'application et cliquez sur « Activer le MFA ».",
    manual_key: "Ou saisissez la clé manuellement :",
    six_digit_code: "Code à 6 chiffres",
    enable_mfa: "Activer le MFA",
    invalid_code: "Code invalide",

    ssh_pubkey: "Clé publique SSH",
    logout: "Déconnexion",
    add_machine: "+ Ajouter une machine",
    action: "Action :",
    update_all: "⟳ Tout mettre à jour",
    th_machine: "Machine",
    th_os: "OS",
    th_status: "Statut",
    th_last: "Dernière action",
    th_actions: "Actions",
    empty: "Aucune machine. Cliquez sur « Ajouter une machine », puis autorisez la clé publique SSH de PatchPilot sur celle-ci.",
    console_hint: "— Console : la sortie apt s'affichera ici en temps réel —",

    add_title: "Ajouter une machine",
    name_label: "Nom (libellé)",
    host_label: "Adresse IP ou nom d'hôte",
    port_label: "Port SSH",
    user_label: "Utilisateur SSH (root ou utilisateur avec sudo)",
    cancel: "Annuler",
    add: "Ajouter",

    key_title: "Clé publique SSH de PatchPilot",
    key_hint: "À ajouter dans ~/.ssh/authorized_keys de l'utilisateur SSH sur chaque machine à gérer :",
    key_missing: "Clé introuvable — relancer install.sh",
    copy: "Copier",
    close: "Fermer",

    badge_running: "en cours…",
    badge_ok: "OK",
    badge_error: "erreur",
    badge_never: "jamais lancé",
    run: "Lancer",
    test: "Tester",
    confirm_delete: "Supprimer « {name} » ?",
    confirm_all: "Lancer « {action} » sur TOUTES les machines ?",
    started_count: "Mise à jour lancée sur {n} machine(s).",
    conn_ok: "Connexion OK — {os}",
    conn_fail: "Échec : {err}",
    job_started: "▶ {action} démarré",
    job_done: "✔ {action} terminé",
    job_failed: "✖ échec : {err}",
    unknown_error: "erreur inconnue",
    up_to_date: "à jour",
    update_available: "mise à jour disponible : {v}",

    use_recovery: "Utiliser un code de secours",
    use_totp: "Utiliser le code de l'application",
    recovery_code: "Code de secours",

    rc_title: "Enregistrez vos codes de secours",
    rc_intro: "Si vous perdez l'accès à votre application d'authentification, chacun de ces codes à usage unique vous permet de vous connecter. Conservez-les en lieu sûr.",
    rc_warn: "Ils ne sont affichés qu'une seule fois. Chaque code ne fonctionne qu'une fois.",
    rc_continue: "Je les ai enregistrés — continuer",

    users: "Utilisateurs",
    users_title: "Gestion des utilisateurs",
    u_th_user: "Utilisateur",
    u_th_role: "Rôle",
    u_th_status: "Statut",
    u_add_title: "Créer un utilisateur",
    u_name_ph: "identifiant",
    u_make_admin: "Administrateur",
    u_create: "Créer + obtenir le lien",
    u_invite_hint: "Copiez ce lien d'activation et envoyez-le à l'utilisateur (il expire dans 7 jours). Il définira lui-même son mot de passe :",
    u_role_admin: "Admin",
    u_role_user: "Utilisateur",
    u_pending: "en attente",
    u_active: "actif",
    u_relink: "Nouveau lien",
    u_confirm_delete: "Supprimer cet utilisateur ?",

    act_title: "Activez votre compte",
    act_intro: "Bienvenue {user}. Choisissez un mot de passe pour activer votre compte.",
    act_password: "Mot de passe (10 caractères min)",
    act_password2: "Confirmez le mot de passe",
    act_submit: "Activer mon compte",
    act_invalid: "Ce lien d'activation est invalide ou expiré. Demandez-en un nouveau à votre administrateur.",
    act_too_short: "Mot de passe trop court (10 caractères minimum).",
    act_mismatch: "Les mots de passe ne correspondent pas.",
    act_done: "Compte activé ! Redirection vers la page de connexion…",
  },
};

/* French translations of server (API) error messages, which are in English */
const SERVER_MSG_FR = {
  "Not authenticated": "Non authentifié",
  "MFA required": "MFA requis",
  "Too many attempts. Try again in 15 minutes.": "Trop de tentatives. Réessayez dans 15 minutes.",
  "Invalid credentials": "Identifiants invalides",
  "Invalid MFA code": "Code MFA invalide",
  "MFA already enabled": "MFA déjà activé",
  "Invalid code": "Code invalide",
  "This machine already exists": "Cette machine existe déjà",
  "Machine not found": "Machine introuvable",
  "An update is already running on this machine": "Une mise à jour est déjà en cours sur cette machine",
  "Connection timed out": "Délai de connexion dépassé",
  "Command timed out": "Délai d'exécution dépassé",
  "passwordless sudo (NOPASSWD) not configured for this user": "sudo sans mot de passe (NOPASSWD) non configuré pour cet utilisateur",
  "Invalid host (IP address or hostname expected)": "Hôte invalide (adresse IP ou nom d'hôte attendu)",
  "Invalid Unix username": "Nom d'utilisateur Unix invalide",
  "Action not allowed": "Action non autorisée",
};

let LANG = localStorage.getItem("pp_lang") ||
  ((navigator.language || "en").toLowerCase().startsWith("fr") ? "fr" : "en");

function t(key, vars) {
  let s = (I18N[LANG] && I18N[LANG][key]) || I18N.en[key] || key;
  if (vars) for (const k of Object.keys(vars)) s = s.replace("{" + k + "}", vars[k]);
  return s;
}

/* Translate a server error message if needed */
function tServer(msg) {
  if (LANG === "fr" && SERVER_MSG_FR[msg]) return SERVER_MSG_FR[msg];
  return msg;
}

function applyI18n() {
  document.documentElement.lang = LANG;
  document.querySelectorAll("[data-i18n]").forEach(el => { el.textContent = t(el.dataset.i18n); });
  document.querySelectorAll("[data-i18n-ph]").forEach(el => { el.placeholder = t(el.dataset.i18nPh); });
  const toggle = document.getElementById("lang-toggle");
  if (toggle) toggle.textContent = LANG === "en" ? "FR" : "EN";
}

function setLang(lang) {
  LANG = lang;
  localStorage.setItem("pp_lang", lang);
  applyI18n();
  window.dispatchEvent(new Event("pp-lang"));
}

document.addEventListener("DOMContentLoaded", () => {
  applyI18n();
  const toggle = document.getElementById("lang-toggle");
  if (toggle) toggle.addEventListener("click", () => setLang(LANG === "en" ? "fr" : "en"));
});
