/* PatchPilot — dashboard */
"use strict";

const ACTION_LABELS = { "update": "apt update", "upgrade": "apt upgrade", "full-upgrade": "apt full-upgrade" };
const tbody = document.getElementById("machines");
const emptyEl = document.getElementById("empty");
const consoleEl = document.getElementById("console");
const runningMachines = new Set();

// ---------- Helpers ----------

async function api(method, url, body) {
  const r = await fetch(url, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
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

// Re-render dynamic content when the language changes
window.addEventListener("pp-lang", render);

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

loadMachines().then(connectWS).catch(() => {});
