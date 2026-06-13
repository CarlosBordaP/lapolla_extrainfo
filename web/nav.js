/* Shared top navigation + identity selector (typeahead modal).
   The user chip is clickable to change identity; the same modal opens
   automatically on first arrival (when not yet identified). */
(function () {
  const path = location.pathname;
  const base = [["/", "Inicio"], ["/calendar", "Calendario"], ["/board", "Tabla"]];

  let participants = null;   // cached roster
  let filtered = [];
  let active = -1;

  const norm = (s) => (s || "").normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase();

  function ensureModal() {
    if (document.getElementById("idOverlay")) return;
    const ov = document.createElement("div");
    ov.id = "idOverlay";
    ov.className = "id-overlay";
    ov.style.display = "none";
    ov.innerHTML = `
      <div class="id-modal" role="dialog" aria-modal="true">
        <button class="id-close" aria-label="Cerrar">✕</button>
        <h2>¿Quién eres?</h2>
        <p class="hint">Escribe tu nombre o usuario y selecciónate de la lista.</p>
        <input id="idInput" type="text" placeholder="Ej: Kevin o kevinb…" autocomplete="off" />
        <div class="id-list" id="idList"></div>
      </div>`;
    document.body.appendChild(ov);
    ov.addEventListener("click", (e) => { if (e.target === ov) closeIdentify(); });
    ov.querySelector(".id-close").onclick = closeIdentify;
    const input = ov.querySelector("#idInput");
    input.addEventListener("input", () => renderList(input.value));
    input.addEventListener("keydown", onKey);
  }

  function onKey(e) {
    if (e.key === "Escape") return closeIdentify();
    if (e.key === "ArrowDown") { e.preventDefault(); move(1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); move(-1); }
    else if (e.key === "Enter") { e.preventDefault(); if (filtered[active]) choose(filtered[active].username); }
  }

  function move(d) {
    if (!filtered.length) return;
    active = (active + d + filtered.length) % filtered.length;
    paintActive();
  }

  function paintActive() {
    const items = [...document.querySelectorAll(".id-item")];
    items.forEach((el, i) => el.classList.toggle("active", i === active));
    if (items[active]) items[active].scrollIntoView({ block: "nearest" });
  }

  function renderList(q) {
    const nq = norm(q);
    filtered = (participants || []).filter(
      (p) => norm(p.display_name).includes(nq) || norm(p.username).includes(nq)
    );
    active = filtered.length ? 0 : -1;
    const list = document.getElementById("idList");
    list.innerHTML = filtered.length
      ? filtered.map((p, i) =>
          `<div class="id-item ${i === 0 ? "active" : ""}" data-u="${p.username}">
             <span>${p.display_name}</span><span class="u">@${p.username}</span></div>`).join("")
      : `<div class="id-empty">Sin coincidencias.</div>`;
    [...list.querySelectorAll(".id-item")].forEach((el, i) => {
      el.addEventListener("mouseenter", () => { active = i; paintActive(); });
      el.addEventListener("click", () => choose(el.dataset.u));
    });
  }

  function choose(username) {
    fetch("/track/identify", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username }),
    }).then((r) => { if (r.ok) location.reload(); });
  }

  function openIdentify() {
    ensureModal();
    document.getElementById("idOverlay").style.display = "flex";
    const input = document.getElementById("idInput");
    input.value = "";
    const show = () => { renderList(""); input.focus(); };
    if (participants) show();
    else fetch("/track/participants").then((r) => r.json()).then((d) => { participants = d; show(); }).catch(() => {});
  }
  function closeIdentify() {
    const ov = document.getElementById("idOverlay");
    if (ov) ov.style.display = "none";
  }
  window.openIdentify = openIdentify;

  fetch("/me").then((r) => r.json()).then((me) => {
    const links = base.slice();
    if (me.is_admin) { links.push(["/insights", "Estadísticas"]); links.push(["/audit-view", "Auditoría"]); }
    const who = me.identified ? `@${me.username} ▾` : "Identifícate ▾";
    const header = document.createElement("header");
    header.className = "nav";
    header.innerHTML =
      `<div class="brand">⚽ Polla</div>
       <nav>${links.map(([h, t]) => `<a href="${h}" class="${path === h ? "active" : ""}">${t}</a>`).join("")}</nav>
       <button class="who" id="whoBtn">${who}</button>`;
    document.body.prepend(header);
    document.getElementById("whoBtn").onclick = openIdentify;
    if (!me.identified) openIdentify();  // primera visita
  }).catch(() => {});
})();
