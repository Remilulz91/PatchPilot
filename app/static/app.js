/* PatchPilot — dashboard */
"use strict";

const ACTION_LABELS = { "update": "apt update", "upgrade": "apt upgrade", "full-upgrade": "apt full-upgrade" };
const tbody = document.getElementById("machines");
const emptyEl = document.getElementById("empty");
const consoleEl = document.getElementById("console");
const runningMachines = new Set();

// ---------- Helpers ----------

function getCookie(name) {
  const m = document.cookie.match(new RegExp("(?:^|;\\s*)" + name + "=([^;]+)"));
  return m ? decodeURIComponent(m[1]) : "";
}

async function api(method, url, body) {
  const headers = body ? { "Content-Type": "application/json" } : {};
  if (method !== "GET") headers["X-CSRF-Token"] = getCookie("pp_csrf");
  const r = await fetch(url, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (r.status === 401) { window.location.href = "/login"; throw new Error("401"); }
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    // detail can be a string or a pydantic validation error array
    let msg = data.detail;
    if (Array.isArray(msg)) msg = msg[0]?.msg?.replace(/^Value error,\s*/, "") || t("error");
    throw new Error(tServer(msg) || t("error") + " " + r.status);
  }
  return data;
}

function esc(s) {
  const d = document.createElement("div");
  d.textContent = s ?? "";
  return d.innerHTML;
}

function logLine(html) {
  const div = document.createElement("div");
  div.innerHTML = html;
  consoleEl.appendChild(div);
  if (consoleEl.children.length > 3000) consoleEl.removeChild(consoleEl.firstChild);
  consoleEl.scrollTop = consoleEl.scrollHeight;
}

// ---------- Machines ----------

function badge(m) {
  if (runningMachines.has(m.id)) return `<span class="badge running">${t("badge_running")}</span>`;
  if (m.last_status === "success") return `<span class="badge success">${t("badge_ok")}</span>`;
  if (m.last_status === "error") return `<span class="badge error">${t("badge_error")}</span>`;
  return `<span class="badge idle">${t("badge_never")}</span>`;
}

let machines = [];

async function loadMachines() {
  machines = await api("GET", "/api/machines");
  render();
}

function render() {
  tbody.innerHTML = "";
  emptyEl.style.display = machines.length ? "none" : "block";
  for (const m of machines) {
    const busy = runningMachines.has(m.id);
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><b>${esc(m.name)}</b><div class="host">${esc(m.username)}@${esc(m.host)}:${m.port}</div></td>
      <td>${esc(m.os_info || "—")}</td>
      <td>${badge(m)}</td>
      <td>${m.last_action ? esc(ACTION_LABELS[m.last_action] || m.last_action) + "<div class='host'>" + esc(m.last_run || "") + "</div>" : "—"}</td>
      <td>
        <div class="row-actions">
          <select data-action-for="${m.id}">
            <option value="update">apt update</option>
            <option value="upgrade">apt upgrade</option>
            <option value="full-upgrade">apt full-upgrade</option>
          </select>
          <button class="small" data-run="${m.id}" ${busy ? "disabled" : ""}>${t("run")}</button>
          <button class="small secondary" data-test="${m.id}">${t("test")}</button>
          <button class="small danger" data-del="${m.id}">✕</button>
        </div>
      </td>`;
    tbody.appendChild(tr);
  }
}

// ---------- Version / update check ----------

let versionInfo = null;

function renderVersion() {
  const el = document.getElementById("version-badge");
  if (!versionInfo) return;
  el.style.display = "inline-block";
  const v = versionInfo;
  if (v.up_to_date === false) {
    el.className = "badge running";
    el.innerHTML = `<a href="${esc(v.releases_url)}" target="_blank" rel="noopener" style="color:inherit;text-decoration:none">v${esc(v.version)} — ${esc(t("update_available", { v: v.latest }))}</a>`;
  } else if (v.up_to_date === true) {
    el.className = "badge success";
    el.textContent = `v${v.version} — ${t("up_to_date")}`;
  } else {
    el.className = "badge idle";
    el.textContent = `v${v.version}`;
  }
}

async function loadVersion() {
  try {
    versionInfo = await api("GET", "/api/version");
    renderVersion();
  } catch { /* version check is best-effort */ }
}

// Re-render dynamic content when the language changes
window.addEventListener("pp-lang", () => { render(); renderVersion(); });

tbody.addEventListener("click", async (e) => {
  const btn = e.target.closest("button");
  if (!btn) return;
  try {
    if (btn.dataset.run) {
      const id = Number(btn.dataset.run);
      const action = document.querySelector(`select[data-action-for="${id}"]`).value;
      await api("POST", `/api/machines/${id}/run`, { action });
    } else if (btn.dataset.test) {
      const id = Number(btn.dataset.test);
      btn.disabled = true;
      const res = await api("POST", `/api/machines/${id}/test`);
      btn.disabled = false;
      const m = machines.find(x => x.id === id);
      if (res.ok) logLine(`<span class="m">[${esc(m.name)}]</span> <span class="ok">${esc(t("conn_ok", { os: res.os_info }))}</span>`);
      else logLine(`<span class="m">[${esc(m.name)}]</span> <span class="ko">${esc(t("conn_fail", { err: tServer(res.error) }))}</span>`);
      await loadMachines();
    } else if (btn.dataset.del) {
      const id = Number(btn.dataset.del);
      const m = machines.find(x => x.id === id);
      if (confirm(t("confirm_delete", { name: m.name }))) {
        await api("DELETE", `/api/machines/${id}`);
        await loadMachines();
      }
    }
  } catch (err) {
    btn.disabled = false;
    logLine(`<span class="ko">${esc(err.message)}</span>`);
  }
});

// ---------- Global buttons ----------

document.getElementById("btn-add").onclick = () => openModal("modal-add");
document.getElementById("btn-run-all").onclick = async () => {
  const action = document.getElementById("global-action").value;
  if (!confirm(t("confirm_all", { action: ACTION_LABELS[action] }))) return;
  try {
    const res = await api("POST", "/api/run-all", { action });
    logLine(`<span class="ok">${esc(t("started_count", { n: res.count }))}</span>`);
  } catch (err) {
    logLine(`<span class="ko">${esc(err.message)}</span>`);
  }
};
document.getElementById("btn-logout").onclick = async () => {
  await fetch("/api/logout", { method: "POST" });
  window.location.href = "/login";
};
document.getElementById("btn-pubkey").onclick = async () => {
  const res = await api("GET", "/api/public-key");
  document.getElementById("pubkey").textContent = res.public_key || t("key_missing");
  openModal("modal-key");
};
document.getElementById("btn-copy-key").onclick = () => {
  navigator.clipboard.writeText(document.getElementById("pubkey").textContent);
};

// ---------- Current user / admin ----------

let me = null;

async function loadMe() {
  try {
    me = await api("GET", "/api/me");
    const el = document.getElementById("current-user");
    const role = me.is_admin ? " (admin)" : "";
    el.innerHTML = `<b>${esc(me.username)}</b>${esc(role)}`;
    if (me.is_admin) document.getElementById("btn-users").style.display = "";
  } catch { /* ignore */ }
}

// ---------- Recovery codes ----------

document.getElementById("btn-recovery").onclick = async () => {
  document.getElementById("rc-manage").style.display = "block";
  document.getElementById("rc-result").style.display = "none";
  document.getElementById("rc-error").textContent = "";
  document.getElementById("rc-code").value = "";
  try {
    const st = await api("GET", "/api/mfa/recovery/status");
    document.getElementById("rc-remaining").textContent =
      st.enabled ? t("rc_remaining", { n: st.remaining }) : t("rc_need_mfa");
    document.getElementById("btn-regen").disabled = !st.enabled;
  } catch { /* ignore */ }
  openModal("modal-recovery");
};

document.getElementById("btn-regen").onclick = async () => {
  const errEl = document.getElementById("rc-error");
  errEl.textContent = "";
  try {
    const res = await api("POST", "/api/mfa/recovery/regenerate", {
      code: document.getElementById("rc-code").value.trim(),
    });
    const grid = document.getElementById("rc-new-grid");
    grid.innerHTML = "";
    for (const c of res.recovery_codes) {
      const span = document.createElement("span");
      span.textContent = c;
      grid.appendChild(span);
    }
    document.getElementById("btn-copy-newrc").onclick = () =>
      navigator.clipboard.writeText(res.recovery_codes.join("\n"));
    document.getElementById("rc-manage").style.display = "none";
    document.getElementById("rc-result").style.display = "block";
  } catch (err) { errEl.textContent = err.message; }
};

// ---------- Users management (admin) ----------

document.getElementById("btn-users").onclick = async () => {
  await loadUsers();
  document.getElementById("invite-box").style.display = "none";
  document.getElementById("user-error").textContent = "";
  openModal("modal-users");
};

async function loadUsers() {
  const users = await api("GET", "/api/users");
  const tb = document.getElementById("users-body");
  tb.innerHTML = "";
  for (const u of users) {
    const role = u.is_admin ? t("u_role_admin") : t("u_role_user");
    const status = u.pending ? `<span class="badge running">${t("u_pending")}</span>`
                             : `<span class="badge success">${t("u_active")}</span>`;
    const isSelf = me && u.username === me.username;
    const reinvite = u.pending ? `<button class="small secondary" data-reinvite="${u.id}">${t("u_relink")}</button>` : "";
    const del = isSelf ? "" : `<button class="small danger" data-deluser="${u.id}">✕</button>`;
    const tr = document.createElement("tr");
    tr.innerHTML = `<td><b>${esc(u.username)}</b></td><td>${esc(role)}</td><td>${status}</td>
                    <td><div class="row-actions">${reinvite}${del}</div></td>`;
    tb.appendChild(tr);
  }
}

function showInvite(link) {
  document.getElementById("invite-link").textContent = link;
  document.getElementById("invite-box").style.display = "block";
}

document.getElementById("users-body").addEventListener("click", async (e) => {
  const btn = e.target.closest("button");
  if (!btn) return;
  const errEl = document.getElementById("user-error");
  errEl.textContent = "";
  try {
    if (btn.dataset.deluser) {
      const id = Number(btn.dataset.deluser);
      if (confirm(t("u_confirm_delete"))) {
        await api("DELETE", `/api/users/${id}`);
        await loadUsers();
      }
    } else if (btn.dataset.reinvite) {
      const res = await api("POST", `/api/users/${btn.dataset.reinvite}/reinvite`);
      showInvite(res.activation_link);
    }
  } catch (err) { errEl.textContent = err.message; }
});

document.getElementById("form-user").addEventListener("submit", async (e) => {
  e.preventDefault();
  const errEl = document.getElementById("user-error");
  errEl.textContent = "";
  try {
    const res = await api("POST", "/api/users", {
      username: document.getElementById("u-name").value.trim(),
      is_admin: document.getElementById("u-admin").checked,
    });
    document.getElementById("u-name").value = "";
    document.getElementById("u-admin").checked = false;
    await loadUsers();
    showInvite(res.activation_link);
  } catch (err) { errEl.textContent = err.message; }
});

document.getElementById("btn-copy-invite").onclick = () => {
  navigator.clipboard.writeText(document.getElementById("invite-link").textContent);
};

// ---------- Modals ----------

function openModal(id) { document.getElementById(id).classList.add("open"); }
document.querySelectorAll("[data-close]").forEach(b => {
  b.onclick = () => b.closest(".modal-bg").classList.remove("open");
});
document.querySelectorAll(".modal-bg").forEach(bg => {
  bg.addEventListener("click", (e) => { if (e.target === bg) bg.classList.remove("open"); });
});

document.getElementById("form-add").addEventListener("submit", async (e) => {
  e.preventDefault();
  const errEl = document.getElementById("add-error");
  errEl.textContent = "";
  try {
    await api("POST", "/api/machines", {
      name: document.getElementById("m-name").value.trim(),
      host: document.getElementById("m-host").value.trim(),
      port: Number(document.getElementById("m-port").value) || 22,
      username: document.getElementById("m-user").value.trim() || "root",
    });
    document.getElementById("modal-add").classList.remove("open");
    e.target.reset();
    document.getElementById("m-port").value = 22;
    document.getElementById("m-user").value = "root";
    await loadMachines();
  } catch (err) {
    errEl.textContent = err.message;
  }
});

// ---------- WebSocket (real-time logs) ----------

function connectWS() {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${window.location.host}/ws`);

  ws.onmessage = (ev) => {
    const e = JSON.parse(ev.data);
    if (e.type === "line") {
      logLine(`<span class="m">[${esc(e.machine_name)}]</span> ${esc(e.line)}`);
    } else if (e.type === "status") {
      if (e.status === "running") {
        runningMachines.add(e.machine_id);
        logLine(`<span class="m">[${esc(e.machine_name)}]</span> <span class="ok">${esc(t("job_started", { action: ACTION_LABELS[e.action] }))}</span>`);
      } else {
        runningMachines.delete(e.machine_id);
        if (e.status === "success") {
          logLine(`<span class="m">[${esc(e.machine_name)}]</span> <span class="ok">${esc(t("job_done", { action: ACTION_LABELS[e.action] }))}</span>`);
        } else {
          logLine(`<span class="m">[${esc(e.machine_name)}]</span> <span class="ko">${esc(t("job_failed", { err: tServer(e.error) || t("unknown_error") }))}</span>`);
        }
        loadMachines();
      }
      render();
    }
  };
  ws.onclose = () => setTimeout(connectWS, 3000);
  setInterval(() => { if (ws.readyState === 1) ws.send("ping"); }, 30000);
}

// ---------- Init ----------

loadMe();
loadMachines().then(connectWS).catch(() => {});
loadVersion();
