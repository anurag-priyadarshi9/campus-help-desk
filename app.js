"use strict";

const $ = (sel, root = document) => root.querySelector(sel);
const state = { user: null, meta: null, filter: "", q: "" };
const isAdmin = () => state.user && state.user.role === "admin";

/* ---------- helpers ---------- */
const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// SQLite stores UTC as "YYYY-MM-DD HH:MM:SS"
const fmt = (s) =>
  new Date(s.replace(" ", "T") + "Z").toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });

async function api(path, { method = "GET", body } = {}) {
  const res = await fetch("/api" + path, {
    method,
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "Something went wrong. Try again.");
  return data;
}

let toastTimer;
function toast(msg) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 2500);
}

function fillSelect(sel, items, placeholder) {
  sel.innerHTML =
    (placeholder ? `<option value="">${esc(placeholder)}</option>` : "") +
    items.map((i) => `<option>${esc(i)}</option>`).join("");
}

/* ---------- boot & view switching ---------- */
async function boot() {
  state.meta = await api("/meta");
  fillSelect($("#filter"), state.meta.statuses, "All statuses");
  fillSelect($("#t-category"), state.meta.categories);
  fillSelect($("#t-priority"), state.meta.priorities);
  $("#t-priority").value = "Medium";
  state.user = (await api("/me")).user;
  render();
}

function render() {
  const loggedIn = !!state.user;
  $("#auth").hidden = loggedIn;
  $("#app").hidden = !loggedIn;
  $("#userbox").hidden = !loggedIn;
  if (!loggedIn) return;
  $("#whoami").textContent = `${state.user.name} (${isAdmin() ? "Staff" : "Student"})`;
  $("#new-btn").hidden = isAdmin();
  $("#staff-btn").hidden = !isAdmin();
  $("#list-title").textContent = isAdmin() ? "All complaints" : "Your complaints";
  state.filter = "";
  state.q = "";
  $("#filter").value = "";
  $("#search").value = "";
  loadTickets();
}

/* ---------- auth ---------- */
document.querySelectorAll(".tabs button").forEach((tab) =>
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tabs button").forEach((t) =>
      t.setAttribute("aria-selected", String(t === tab)));
    $("#login-form").hidden = tab.dataset.tab !== "login";
    $("#register-form").hidden = tab.dataset.tab !== "register";
  }));

function authForm(formSel, path) {
  const form = $(formSel);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const err = $(".error", form);
    err.textContent = "";
    try {
      const data = await api(path, { method: "POST", body: Object.fromEntries(new FormData(form)) });
      state.user = data.user;
      form.reset();
      render();
    } catch (ex) {
      err.textContent = ex.message;
    }
  });
}
authForm("#login-form", "/login");
authForm("#register-form", "/register");

$("#logout").addEventListener("click", async () => {
  await api("/logout", { method: "POST" });
  state.user = null;
  $("#tickets").innerHTML = "";
  render();
});

/* ---------- ticket list ---------- */
async function loadTickets() {
  const params = new URLSearchParams();
  if (state.filter) params.set("status", state.filter);
  if (state.q) params.set("q", state.q);
  try {
    const { tickets } = await api("/tickets?" + params);
    renderTickets(tickets);
    if (isAdmin()) loadStats();
  } catch (ex) {
    toast(ex.message);
  }
}

function renderTickets(tickets) {
  const list = $("#tickets");
  if (!tickets.length) {
    const filtered = state.filter || state.q;
    list.innerHTML = `<li class="empty">${
      filtered ? "No complaints match these filters."
      : isAdmin() ? "No complaints have been filed yet."
      : "You haven't filed a complaint yet. Select New complaint to report a problem."}</li>`;
    return;
  }
  list.innerHTML = tickets.map((t) => `
    <li class="ticket" data-status="${esc(t.status)}">
      <button type="button" class="ticket-btn" data-id="${t.id}">
        <span class="t-main">
          <span class="t-title">${esc(t.title)}</span>
          <span class="t-meta">
            <span>#${t.id}</span><span>${esc(t.category)}</span>
            ${isAdmin() ? `<span>${esc(t.student_name)}</span>` : ""}
            <span>${esc(fmt(t.created_at))}</span>
          </span>
        </span>
        <span class="t-side">
          <span class="prio" data-p="${esc(t.priority)}">${esc(t.priority)} priority</span>
          <span class="chip">${esc(t.status)}</span>
        </span>
      </button>
    </li>`).join("");
}

async function loadStats() {
  const { counts, total } = await api("/stats");
  const box = $("#stats");
  box.hidden = false;
  const tile = (label, n, status) =>
    `<button type="button" class="stat" ${status ? `data-status="${esc(status)}"` : ""}
      data-filter="${esc(status || "")}" aria-pressed="${state.filter === (status || "")}">
      <b>${n}</b><span>${esc(label)}</span></button>`;
  box.innerHTML = tile("All", total, "") +
    state.meta.statuses.map((s) => tile(s, counts[s], s)).join("");
}

$("#stats").addEventListener("click", (e) => {
  const tile = e.target.closest(".stat");
  if (!tile) return;
  state.filter = tile.dataset.filter;
  $("#filter").value = state.filter;
  loadTickets();
});
$("#filter").addEventListener("change", (e) => { state.filter = e.target.value; loadTickets(); });

let searchTimer;
$("#search").addEventListener("input", (e) => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => { state.q = e.target.value.trim(); loadTickets(); }, 250);
});

$("#tickets").addEventListener("click", (e) => {
  const btn = e.target.closest(".ticket-btn");
  if (btn) showTicket(btn.dataset.id);
});

/* ---------- change password ---------- */
$("#change-pw-btn").addEventListener("click", () => $("#password-dialog").showModal());

$("#password-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const err = $(".error", form);
  err.textContent = "";
  try {
    await api("/change-password", { method: "POST", body: Object.fromEntries(new FormData(form)) });
    form.reset();
    $("#password-dialog").close();
    toast("Password updated");
  } catch (ex) {
    err.textContent = ex.message;
  }
});

/* ---------- add staff (admin only) ---------- */
$("#staff-btn").addEventListener("click", () => $("#staff-dialog").showModal());

$("#staff-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const err = $(".error", form);
  err.textContent = "";
  try {
    await api("/staff", { method: "POST", body: Object.fromEntries(new FormData(form)) });
    form.reset();
    $("#staff-dialog").close();
    toast("Staff account created");
  } catch (ex) {
    err.textContent = ex.message;
  }
});

/* ---------- new complaint ---------- */
$("#new-btn").addEventListener("click", () => $("#new-dialog").showModal());

$("#new-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const err = $(".error", form);
  err.textContent = "";
  try {
    await api("/tickets", { method: "POST", body: Object.fromEntries(new FormData(form)) });
    form.reset();
    $("#t-priority").value = "Medium";
    $("#new-dialog").close();
    toast("Complaint submitted");
    loadTickets();
  } catch (ex) {
    err.textContent = ex.message;
  }
});

/* ---------- complaint detail ---------- */
async function showTicket(id) {
  try {
    const { ticket, replies } = await api("/tickets/" + id);
    renderDetail(ticket, replies);
    const dlg = $("#detail");
    if (!dlg.open) dlg.showModal();
  } catch (ex) {
    toast(ex.message);
  }
}

function renderDetail(t, replies) {
  const admin = isAdmin();
  const canReply = admin || t.status !== "Closed";
  $("#detail-body").innerHTML = `
    <header class="dlg-head">
      <div>
        <h2 id="detail-title">${esc(t.title)}</h2>
        <div class="t-meta">
          <span>#${t.id}</span><span>${esc(t.category)}</span><span>${esc(t.priority)} priority</span>
          ${admin ? `<span>Filed by ${esc(t.student_name)}</span>` : ""}
          <span>${esc(fmt(t.created_at))}</span>
        </div>
      </div>
      <button type="button" class="btn ghost" data-close>Close</button>
    </header>
    <div class="dlg-section"><p class="desc">${esc(t.description)}</p></div>
    <div class="dlg-section status-row" data-status="${esc(t.status)}">
      ${admin
        ? `<label>Status
             <select id="status-select">${state.meta.statuses.map((s) =>
               `<option${s === t.status ? " selected" : ""}>${esc(s)}</option>`).join("")}</select>
           </label>`
        : `<span class="chip">${esc(t.status)}</span>`}
    </div>
    <div class="dlg-section">
      <h3>Replies</h3>
      ${replies.length
        ? `<ul class="replies">${replies.map((r) => `
            <li class="reply${r.role === "admin" ? " staff" : ""}">
              <div class="reply-head"><b>${esc(r.name)}</b>${r.role === "admin" ? "<span>Staff</span>" : ""}<span>${esc(fmt(r.created_at))}</span></div>
              <p>${esc(r.message)}</p>
            </li>`).join("")}</ul>`
        : `<p class="muted">No replies yet.</p>`}
      ${canReply
        ? `<form id="reply-form">
             <label>Your reply<textarea name="message" rows="3" maxlength="2000" required></textarea></label>
             <p class="error" role="alert"></p>
             <button class="btn primary" type="submit">Send reply</button>
           </form>`
        : `<p class="muted">This complaint is closed. File a new complaint if the problem returns.</p>`}
    </div>`;

  const select = $("#status-select");
  if (select) {
    select.addEventListener("change", async () => {
      try {
        await api("/tickets/" + t.id, { method: "PATCH", body: { status: select.value } });
        toast("Status updated");
        showTicket(t.id);
        loadTickets();
      } catch (ex) { toast(ex.message); }
    });
  }

  const form = $("#reply-form");
  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const err = $(".error", form);
      err.textContent = "";
      try {
        await api(`/tickets/${t.id}/replies`, { method: "POST", body: Object.fromEntries(new FormData(form)) });
        toast("Reply sent");
        showTicket(t.id);
        loadTickets();
      } catch (ex) { err.textContent = ex.message; }
    });
  }
}

/* ---------- dialogs: close buttons and backdrop click ---------- */
document.addEventListener("click", (e) => {
  const closer = e.target.closest("[data-close]");
  if (closer) closer.closest("dialog").close();
  else if (e.target.tagName === "DIALOG") e.target.close();
});

boot().catch((ex) => toast(ex.message));