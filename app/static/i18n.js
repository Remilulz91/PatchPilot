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

    mfa_title: "MFA setup",
    mfa_sub: "Scan this QR code with your authenticator app (Google Authenticator, Authy, 2FAS…) then enter the generated code.",
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

    mfa_title: "Configuration du MFA",
    mfa_sub: "Scannez ce QR code avec votre application d'authentification (Google Authenticator, Authy, 2FAS…) puis saisissez le code généré.",
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
