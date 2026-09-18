const API = ""; // same origin

let state = {
  token: localStorage.getItem("mb_token") || null,
  balanceVisible: true,
  card: null,
};

function screens() {
  return document.querySelectorAll(".screen");
}

function goto(name) {
  screens().forEach((s) => s.classList.add("hidden"));
  document.getElementById("screen-" + name).classList.remove("hidden");
  if (name === "home") loadHome();
  if (name === "cards") loadCards();
  if (name === "transfer") {
    document.getElementById("transfer-error").classList.add("hidden");
  }
}

async function api(path, options = {}) {
  const headers = options.headers || {};
  if (state.token) headers["Authorization"] = "Bearer " + state.token;
  if (options.body) headers["Content-Type"] = "application/json";
  const res = await fetch(API + path, { ...options, headers });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "Request failed");
  return data;
}

function money(n) {
  return "₹" + Number(n).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function initials(name) {
  return name
    .split(" ")
    .map((p) => p[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

function timeAgo(iso) {
  const d = new Date(iso);
  const now = new Date();
  const diffMs = now - d;
  const mins = Math.floor(diffMs / 60000);
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `Today, ${d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}`;
  const days = Math.floor(hours / 24);
  if (days === 1) return "Yesterday";
  if (days < 7) return `${days} days ago`;
  return d.toLocaleDateString();
}

// ---------------------------------------------------------------------
// Login
// ---------------------------------------------------------------------

document.getElementById("login-btn").addEventListener("click", async () => {
  const email = document.getElementById("email").value.trim();
  const password = document.getElementById("password").value;
  const errBox = document.getElementById("login-error");
  errBox.classList.add("hidden");
  try {
    const data = await api("/api/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    state.token = data.token;
    localStorage.setItem("mb_token", data.token);
    goto("home");
  } catch (e) {
    errBox.textContent = e.message;
    errBox.classList.remove("hidden");
  }
});

// ---------------------------------------------------------------------
// Home
// ---------------------------------------------------------------------

async function loadHome() {
  try {
    const me = await api("/api/me");
    document.getElementById("home-name").textContent = me.name;
    document.getElementById("home-avatar").textContent = initials(me.name);

    const accounts = await api("/api/accounts");
    const acc = accounts[0];
    if (acc) {
      state.primaryAccount = acc;
      document.getElementById("balance-fig").textContent = money(acc.balance);
      document.getElementById("balance-acc").textContent = `${acc.account_type} · ${acc.number_masked}`;
    }

    const insight = await api("/api/insights");
    const pct = Math.min(100, Math.round((insight.spent / insight.budget) * 100));
    document.getElementById("insight-text").textContent = `${money(insight.spent)} / ${money(insight.budget)}`;
    document.getElementById("insight-bar").style.width = pct + "%";

    const txs = await api("/api/transactions");
    const list = document.getElementById("tx-list");
    list.innerHTML = "";
    txs.slice(0, 6).forEach((tx) => {
      const row = document.createElement("div");
      row.className = "tx";
      const sign = tx.direction === "credit" ? "+" : "−";
      const cls = tx.direction === "credit" ? "pos" : "neg";
      row.innerHTML = `
        <div><div class="who">${tx.counterparty}</div><div class="when">${timeAgo(tx.created_at)}</div></div>
        <div class="amt ${cls}">${sign}${money(tx.amount)}</div>`;
      list.appendChild(row);
    });
  } catch (e) {
    if (e.message === "not authenticated") goto("login");
  }
}

document.getElementById("toggle-balance").addEventListener("click", (ev) => {
  state.balanceVisible = !state.balanceVisible;
  const fig = document.getElementById("balance-fig");
  if (state.balanceVisible) {
    fig.textContent = money(state.primaryAccount.balance);
    ev.target.textContent = "Hide";
  } else {
    fig.textContent = "•••••••";
    ev.target.textContent = "Show";
  }
});

document.getElementById("logout-btn").addEventListener("click", async () => {
  try {
    await api("/api/logout", { method: "POST" });
  } catch (e) {}
  state.token = null;
  localStorage.removeItem("mb_token");
});

// ---------------------------------------------------------------------
// Cards
// ---------------------------------------------------------------------

async function loadCards() {
  const cards = await api("/api/cards");
  const card = cards[0];
  state.card = card;
  const container = document.getElementById("card-container");
  if (!card) {
    container.innerHTML = "<p>No cards yet.</p>";
    return;
  }
  container.innerHTML = `
    <div class="debitcard">
      <div class="dc-top"><span>Mini Bank</span><span>${card.frozen ? "Frozen" : "Debit"}</span></div>
      <div class="dc-num">${card.number_masked}</div>
      <div class="dc-bottom">
        <div>Card holder<b>${card.holder_name}</b></div>
        <div>Expires<b>${card.expiry}</b></div>
      </div>
    </div>`;
  document.getElementById("card-limit").textContent = `₹${Number(card.daily_limit).toLocaleString("en-IN")} per day`;

  const toggle = document.getElementById("freeze-toggle");
  toggle.classList.toggle("on", !!card.frozen);
}

document.getElementById("freeze-toggle").addEventListener("click", async () => {
  if (!state.card) return;
  const data = await api(`/api/cards/${state.card.id}/freeze`, { method: "PATCH" });
  state.card.frozen = data.frozen;
  document.getElementById("freeze-toggle").classList.toggle("on", data.frozen);
  loadCards();
});

// ---------------------------------------------------------------------
// Transfer
// ---------------------------------------------------------------------

document.getElementById("transfer-btn").addEventListener("click", async () => {
  const to_name = document.getElementById("to-name").value.trim();
  const to_account = document.getElementById("to-account").value.trim();
  const amount = document.getElementById("amount").value;
  const note = document.getElementById("note").value.trim();
  const errBox = document.getElementById("transfer-error");
  errBox.classList.add("hidden");

  try {
    const data = await api("/api/transfer", {
      method: "POST",
      body: JSON.stringify({ to_name, to_account, amount, note }),
    });
    document.getElementById("succ-amt").textContent = money(data.amount);
    document.getElementById("succ-to").textContent = `to ${data.to_name}${data.to_account ? " · " + data.to_account : ""}`;
    document.getElementById("succ-txid").textContent = data.transaction_id;
    document.getElementById("succ-date").textContent = new Date(data.created_at).toLocaleString();

    // clear form for next time
    document.getElementById("to-name").value = "";
    document.getElementById("to-account").value = "";
    document.getElementById("amount").value = "";
    document.getElementById("note").value = "";

    goto("success");
  } catch (e) {
    errBox.textContent = e.message;
    errBox.classList.remove("hidden");
  }
});

// ---------------------------------------------------------------------
// Generic data-goto delegation
// ---------------------------------------------------------------------

document.addEventListener("click", (ev) => {
  const el = ev.target.closest("[data-goto]");
  if (el) goto(el.getAttribute("data-goto"));
});

// ---------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------

if (state.token) {
  goto("home");
} else {
  goto("login");
}
