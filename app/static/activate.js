/* PatchPilot — account activation page */
"use strict";

const errEl = document.getElementById("error");
const params = new URLSearchParams(window.location.search);
const token = params.get("token") || "";

(async () => {
  if (!token) { showInvalid(); return; }
  try {
    const r = await fetch("/api/activation/info?token=" + encodeURIComponent(token));
    const data = await r.json();
    if (!r.ok) { showInvalid(); return; }
    document.getElementById("act-intro").textContent = t("act_intro", { user: data.username });
  } catch {
    showInvalid();
  }
})();

function showInvalid() {
  document.getElementById("act-fields").style.display = "none";
  errEl.textContent = t("act_invalid");
}

document.getElementById("activate-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  errEl.textContent = "";
  const pw = document.getElementById("password").value;
  const pw2 = document.getElementById("password2").value;
  if (pw.length < 10) { errEl.textContent = t("act_too_short"); return; }
  if (pw !== pw2) { errEl.textContent = t("act_mismatch"); return; }
  try {
    const r = await fetch("/api/activation/complete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token, password: pw }),
    });
    const data = await r.json();
    if (!r.ok) { errEl.textContent = tServer(data.detail) || t("error"); return; }
    document.getElementById("act-fields").style.display = "none";
    const done = document.getElementById("act-done");
    done.textContent = t("act_done");
    done.style.display = "block";
    setTimeout(() => { window.location.href = data.redirect || "/login"; }, 2500);
  } catch {
    errEl.textContent = t("network_error");
  }
});
