/* Холбоос — клиент талын харилцан үйлдэл (vanilla JS, сан шаардлагагүй).
   Хэрэглэгчийн оруулсан текстийг ЗӨВХӨН textContent-оор оруулна (XSS-ээс хамгаална). */
(() => {
  "use strict";
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const csrf = () => ($('meta[name="csrf-token"]') || {}).content || "";
  const isAuth = document.body.dataset.auth === "1";
  const STATUS_COLORS = { slate: "#5b6b82", blue: "#2563eb", amber: "#e08a00", violet: "#7c3aed", cyan: "#0891b2", green: "#16a34a" };

  function el(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") node.className = v;
      else if (k === "text") node.textContent = v;
      else if (k === "style") node.setAttribute("style", v);
      else node.setAttribute(k, v);
    }
    for (const c of children) if (c != null) node.append(c instanceof Node ? c : document.createTextNode(String(c)));
    return node;
  }

  function toast(message, kind = "success") {
    const stack = $("#toasts");
    if (!stack) return;
    const icon = kind === "error" ? "⚠️" : kind === "info" ? "ℹ️" : "✅";
    const t = el("div", { class: `toast toast-${kind}`, role: "status" }, el("span", { text: icon }), el("span", { text: message }));
    stack.append(t);
    setTimeout(() => { t.style.transition = "opacity .3s"; t.style.opacity = "0"; setTimeout(() => t.remove(), 300); }, 3200);
  }

  function goLogin() {
    location.href = "/login?next=" + encodeURIComponent(location.pathname + location.search);
  }

  async function post(url, body) {
    const res = await fetch(url, {
      method: "POST",
      headers: { "X-CSRF-Token": csrf(), Accept: "application/json" },
      body: body || new FormData(),
      credentials: "same-origin",
    });
    let data = {};
    try { data = await res.json(); } catch (_) { /* JSON биш */ }
    if (res.status === 401) { goLogin(); throw new Error("login"); }
    if (!res.ok) throw new Error(data.error || "Алдаа гарлаа. Дахин оролдоно уу.");
    return data;
  }

  /* ---------- Flash, цэс ---------- */
  $$(".flash").forEach((f) => setTimeout(() => { f.style.transition = "opacity .4s"; f.style.opacity = "0"; setTimeout(() => f.remove(), 400); }, 6000));
  document.addEventListener("click", (e) => {
    const dismiss = e.target.closest("[data-dismiss]");
    if (dismiss) dismiss.parentElement.remove();
    $$("details.user-menu[open]").forEach((d) => { if (!d.contains(e.target)) d.removeAttribute("open"); });
  });
  const navToggle = $(".nav-toggle");
  if (navToggle) navToggle.addEventListener("click", () => {
    const open = $("#nav-links").classList.toggle("open");
    navToggle.setAttribute("aria-expanded", open ? "true" : "false");
  });

  /* ---------- Дэмжих ---------- */
  function setSupport(id, supported, count) {
    $$(`.js-support[data-id="${id}"]`).forEach((b) => {
      b.classList.toggle("supported", supported);
      b.setAttribute("aria-pressed", supported ? "true" : "false");
      const lbl = $(".lbl", b);
      if (lbl) lbl.textContent = supported ? "Дэмжсэн" : "Дэмжих";
      if (supported) { b.classList.remove("pop"); void b.offsetWidth; b.classList.add("pop"); }
    });
    $$(`.js-support-count[data-id="${id}"]`).forEach((c) => { c.textContent = count; });
  }
  function setPriority(p) {
    const v = $(".js-priority");
    if (v) v.textContent = p;
    const g = $(".js-gauge");
    if (g) g.setAttribute("stroke-dasharray", `${p} 100`);
  }
  document.addEventListener("click", async (e) => {
    const btn = e.target.closest(".js-support");
    if (!btn || btn.disabled) return;
    e.preventDefault();
    if (!isAuth) return goLogin();
    btn.disabled = true;
    try {
      const d = await post(`/issues/${btn.dataset.id}/support`);
      setSupport(btn.dataset.id, d.supported, d.count);
      setPriority(d.priority);
      toast(d.supported ? "Та энэ асуудлыг дэмжлээ 👍" : "Дэмжлэгээ цуцаллаа", d.supported ? "success" : "info");
    } catch (err) { if (err.message !== "login") toast(err.message, "error"); }
    finally { btn.disabled = false; }
  });

  /* ---------- Сэтгэгдэл ---------- */
  document.addEventListener("click", (e) => {
    const t = e.target.closest(".js-comment-toggle");
    if (!t) return;
    const box = $(`#ic-${t.dataset.id}`);
    if (!box) return;
    box.hidden = !box.hidden;
    if (!box.hidden) { const ta = $("textarea", box); if (ta) ta.focus(); }
  });
  function commentNode(d) {
    const av = el("span", { class: "avatar avatar-sm", style: `background:${d.color}`, text: d.initials });
    const bubble = el("div", { class: "bubble" }, el("b", { text: d.user_name }));
    if (d.role !== "citizen") bubble.append(" ", el("span", { class: `role-badge ${d.role}`, text: d.role_label }));
    bubble.append(el("p", { text: d.content }));
    return el("div", { class: `comment${d.role === "mp" ? " mp" : ""}` }, av, el("div", { class: "grow" }, bubble, el("div", { class: "ctime", text: d.time })));
  }
  document.addEventListener("submit", async (e) => {
    const form = e.target.closest(".js-comment-form");
    if (!form) return;
    e.preventDefault();
    const ta = $("textarea", form);
    if (!ta.value.trim()) return;
    const btn = $("button", form);
    btn.disabled = true;
    try {
      const d = await post(form.action, new FormData(form));
      const list = (form.closest(".inline-comments, .card-body") || document).querySelector(".js-new-comments");
      if (list) list.prepend(commentNode(d));
      $$(`.js-comment-count[data-id="${form.dataset.id}"]`).forEach((c) => { c.textContent = d.count; });
      $$(".js-no-comments").forEach((n) => n.remove());
      ta.value = "";
      toast("Сэтгэгдэл нэмэгдлээ 💬");
    } catch (err) { if (err.message !== "login") toast(err.message, "error"); }
    finally { btn.disabled = false; }
  });

  /* ---------- Цааш үзэх ---------- */
  document.addEventListener("click", async (e) => {
    const btn = e.target.closest(".js-load-more");
    if (!btn) return;
    const feed = $(".js-feed");
    btn.disabled = true;
    btn.textContent = "Ачаалж байна...";
    try {
      const res = await fetch(`${feed.dataset.base}&page=${btn.dataset.next}&partial=1`, { credentials: "same-origin" });
      const html = await res.text();
      btn.closest(".js-load-more-wrap").remove();
      feed.insertAdjacentHTML("beforeend", html);  // сервер Jinja autoescape-ээр рендерлэсэн HTML
    } catch (_) { btn.disabled = false; btn.textContent = "Дахин оролдох"; }
  });

  /* ---------- Баталгаажуулах модал ---------- */
  document.addEventListener("submit", (e) => {
    const form = e.target;
    if (!form.matches("form[data-confirm]") || form.dataset.confirmed === "1") return;
    e.preventDefault();
    const close = () => backdrop.remove();
    const ok = el("button", { class: "btn btn-danger", type: "button", text: "Тийм, устгах" });
    const cancel = el("button", { class: "btn btn-light", type: "button", text: "Болих" });
    const backdrop = el("div", { class: "modal-backdrop", role: "dialog", "aria-modal": "true" },
      el("div", { class: "modal" }, el("div", { class: "m-ico", text: "🗑️" }),
        el("h3", { text: form.dataset.confirmTitle || "Баталгаажуулах" }),
        el("p", { class: "muted", text: form.dataset.confirm }),
        el("div", { class: "m-actions" }, cancel, ok)));
    cancel.addEventListener("click", close);
    backdrop.addEventListener("click", (ev) => { if (ev.target === backdrop) close(); });
    ok.addEventListener("click", () => { form.dataset.confirmed = "1"; close(); form.submit(); });
    document.addEventListener("keydown", function esc(ev) { if (ev.key === "Escape") { close(); document.removeEventListener("keydown", esc); } });
    document.body.append(backdrop);
    ok.focus();
  });

  /* ---------- Дүүрэг → хороо ---------- */
  function fillKhoroos(district, select, districts, selected) {
    const d = districts.find((x) => String(x.id) === String(district));
    select.innerHTML = "";
    select.append(el("option", { value: "", text: "— Хороо сонгох —" }));
    if (!d) return;
    d.khoroos.forEach((k) => {
      const o = el("option", { value: k.id, text: `${k.number}-р хороо` });
      if (String(k.id) === String(selected)) o.selected = true;
      select.append(o);
    });
  }
  $$(".js-geo").forEach((geo) => {
    const districts = JSON.parse(geo.dataset.districts || "[]");
    const ds = $(".js-district", geo), ks = $(".js-khoroo", geo);
    fillKhoroos(ds.value, ks, districts, ks.dataset.selected);
    ds.addEventListener("change", () => { fillKhoroos(ds.value, ks, districts, ""); geo.dispatchEvent(new CustomEvent("geo-change", { bubbles: true })); });
    ks.addEventListener("change", () => geo.dispatchEvent(new CustomEvent("geo-change", { bubbles: true })));
    geo._districts = districts;
  });

  /* ---------- Асуудал мэдээлэх форм ---------- */
  const issueForm = $("#issue-form");
  if (issueForm) {
    const titleIn = $("#f-title"), dupPanel = $(".js-dup-panel"), dupChecked = $("#dup-checked");
    let dupState = "none"; // none | shown | ack

    $$(".char-count").forEach((c) => {
      const input = document.getElementById(c.dataset.for);
      const upd = () => { c.textContent = `${input.value.length}/${input.maxLength}`; };
      input.addEventListener("input", upd); upd();
    });

    // Зураг: хэмжээ шалгах, урьдчилан харах, чирж оруулах
    const fileIn = $(".js-image-input"), preview = $(".js-preview"), zone = $(".js-dropzone");
    const showPreview = () => {
      const f = fileIn.files[0];
      if (!f) { preview.hidden = true; return; }
      const maxMb = Number(fileIn.dataset.maxMb || 5);
      if (f.size > maxMb * 1024 * 1024) { toast(`Зургийн хэмжээ ${maxMb}MB-аас их байна`, "error"); fileIn.value = ""; preview.hidden = true; return; }
      if (!/^image\//.test(f.type)) { toast("Зөвхөн зураг оруулна уу", "error"); fileIn.value = ""; return; }
      $("img", preview).src = URL.createObjectURL(f);
      preview.hidden = false;
    };
    fileIn.addEventListener("change", showPreview);
    ["dragenter", "dragover"].forEach((ev) => zone.addEventListener(ev, () => zone.classList.add("drag")));
    ["dragleave", "drop"].forEach((ev) => zone.addEventListener(ev, () => zone.classList.remove("drag")));
    $(".js-clear-image").addEventListener("click", () => { fileIn.value = ""; preview.hidden = true; });

    // Давхардал шалгах
    const val = (name) => { const f = issueForm.elements[name]; return f ? (f.value || "") : ""; };
    let timer;
    async function checkDuplicates() {
      const title = titleIn.value.trim();
      if (title.length < 6) { dupPanel.hidden = true; dupState = "none"; return; }
      const qs = new URLSearchParams({ title, district_id: val("district_id"), khoroo_id: val("khoroo_id"), category: val("category") });
      try {
        const res = await fetch(`/api/issues/similar?${qs}`, { headers: { Accept: "application/json" } });
        const data = await res.json();
        renderDuplicates(data.results || []);
      } catch (_) { /* сүлжээний алдааг үл тооно */ }
    }
    function renderDuplicates(items) {
      dupPanel.replaceChildren();
      if (!items.length) { dupPanel.hidden = true; if (dupState !== "ack") dupState = "none"; return; }
      dupPanel.append(el("h4", {}, "⚠️ ", "Энэ асуудал өмнө нь мэдээлэгдсэн байна."),
        el("p", { class: "small muted mb-0", text: "Шинээр үүсгэхийн оронд одоо байгаа асуудлыг дэмжвэл илүү хурдан шийдэгдэнэ." }));
      items.forEach((it) => {
        const info = el("div", { class: "grow" }, el("b", { text: it.title }), el("span", { class: "xs muted", text: `📍 ${it.location} · 👍 ${it.support_count} · ${it.status_label}` }));
        let action;
        if (it.is_author) action = el("a", { class: "btn btn-light btn-sm", href: it.url, text: "Таны асуудал" });
        else if (it.supported) action = el("a", { class: "btn btn-light btn-sm", href: it.url, text: "✓ Дэмжсэн" });
        else {
          action = el("button", { class: "btn btn-primary btn-sm", type: "button", text: "👍 Үүнийг дэмжих" });
          action.addEventListener("click", async () => {
            try { await post(`/issues/${it.id}/support`); toast("Одоо байгаа асуудлыг дэмжлээ! Шилжиж байна..."); setTimeout(() => { location.href = it.url; }, 700); }
            catch (err) { if (err.message !== "login") toast(err.message, "error"); }
          });
        }
        dupPanel.append(el("div", { class: "dup-item" }, info, el("span", { class: "match", text: `${it.score}% төстэй` }), action));
      });
      const cont = el("button", { class: "btn btn-light btn-sm mt-2", type: "button", text: "Үгүй, миний асуудал өөр — үргэлжлүүлэх" });
      cont.addEventListener("click", () => { dupState = "ack"; dupChecked.value = "1"; dupPanel.hidden = true; toast("Шинэ асуудлаар үргэлжлүүлж байна", "info"); });
      dupPanel.append(cont);
      dupPanel.hidden = false;
      if (dupState !== "ack") dupState = "shown";
    }
    const schedule = () => { clearTimeout(timer); timer = setTimeout(checkDuplicates, 450); };
    titleIn.addEventListener("input", schedule);
    issueForm.addEventListener("change", (e) => { if (e.target.name === "category") schedule(); });
    issueForm.addEventListener("geo-change", schedule);
    $$(".js-dup-continue").forEach((b) => b.addEventListener("click", () => { dupState = "ack"; dupChecked.value = "1"; b.closest(".dup-panel").hidden = true; }));

    issueForm.addEventListener("submit", (e) => {
      if (dupState === "shown") {
        e.preventDefault();
        dupPanel.scrollIntoView({ behavior: "smooth", block: "center" });
        dupPanel.animate([{ transform: "scale(1)" }, { transform: "scale(1.02)" }, { transform: "scale(1)" }], { duration: 400 });
        toast("Төстэй асуудал байна. Дэмжих эсвэл “үргэлжлүүлэх”-ийг сонгоно уу.", "info");
        return;
      }
      dupChecked.value = "1";  // JS шалгалт хийгдсэн
      const btn = $("button[type=submit]", issueForm);
      btn.disabled = true; btn.textContent = "Илгээж байна...";
    });

    // Хариуцах гишүүний урьдчилсан харагдац
    const mpBox = $(".js-mp-preview");
    async function previewMp() {
      const qs = new URLSearchParams({ district_id: val("district_id"), khoroo_id: val("khoroo_id") });
      if (!val("district_id")) return;
      try {
        const res = await fetch(`/api/relevant-mp?${qs}`, { headers: { Accept: "application/json" } });
        const { mp } = await res.json();
        mpBox.replaceChildren();
        if (!mp) { mpBox.append(el("p", { class: "small muted mb-0", text: "Энэ хороонд оноогдсон гишүүн байхгүй. Аль ч гишүүн хүлээн авах боломжтой." })); return; }
        const av = mp.image ? el("img", { class: "avatar avatar-lg ring", src: mp.image, alt: "" }) : el("span", { class: "avatar avatar-lg ring", style: `background:${mp.color}`, text: mp.initials });
        mpBox.append(el("a", { class: "mp-mini", href: mp.url, style: "color:inherit" }, av,
          el("div", {}, el("b", { text: mp.name }), el("div", { class: "xs muted", text: mp.position }), el("div", { class: "xs muted", text: mp.constituency }))),
          el("p", { class: "small mt-2 mb-0", text: "✅ Таны асуудал энэ гишүүний самбарт шууд харагдана." }));
      } catch (_) { /* үл тооно */ }
    }
    issueForm.addEventListener("geo-change", previewMp);
    previewMp();
    if (titleIn.value) schedule();
  }

  /* ---------- Газрын зураг (Leaflet — интернэтгүй үед зөөлөн fallback) ---------- */
  const hasLeaflet = () => typeof window.L !== "undefined";
  function baseMap(node, center, zoom) {
    node.replaceChildren();
    const map = L.map(node, { scrollWheelZoom: false }).setView(center, zoom);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; OpenStreetMap contributors", maxZoom: 19,
    }).addTo(map);
    return map;
  }
  function popupNode(m) {
    return el("div", { class: "map-pop" },
      el("span", { class: "status", style: `color:${STATUS_COLORS[m.color]};background:#f4f6fb`, text: m.status_label }),
      el("b", { text: `${m.icon} ${m.title}` }),
      el("div", { class: "xs muted", text: `👍 ${m.support} дэмжигч · ⚡ ${m.priority}/100 · ${m.location}` }),
      el("a", { href: `/issues/${m.id}`, text: "Дэлгэрэнгүй →" }));
  }

  const mapNode = $("#issue-map");
  if (mapNode && hasLeaflet()) {
    const markers = JSON.parse(mapNode.dataset.markers || "[]");
    const map = baseMap(mapNode, [47.917, 106.905], 12);
    const layer = L.layerGroup().addTo(map);
    const filters = { status: "", category: "" };
    const draw = () => {
      layer.clearLayers();
      markers.filter((m) => (!filters.status || (filters.status === "open" ? m.status !== "RESOLVED" : m.status === filters.status))
        && (!filters.category || m.category === filters.category))
        .forEach((m) => {
          L.circleMarker([m.lat, m.lng], { radius: 6 + Math.sqrt(m.support) * 0.9, color: "#fff", weight: 2, fillColor: STATUS_COLORS[m.color], fillOpacity: 0.9 })
            .bindPopup(popupNode(m)).addTo(layer);
        });
    };
    draw();
    $$(".js-map-filter").forEach((s) => s.addEventListener("change", () => { filters[s.dataset.key] = s.value; draw(); }));
    $$(".js-district-zoom").forEach((b) => b.addEventListener("click", () => {
      $$(".js-district-zoom").forEach((x) => x.classList.remove("active"));
      b.classList.add("active");
      map.flyTo([Number(b.dataset.lat), Number(b.dataset.lng)], 13, { duration: 0.8 });
    }));
  } else if (mapNode) {
    $(".map-fallback b", mapNode).textContent = "Газрын зураг ачаалагдсангүй (интернэт холболт шаардлагатай)";
  }

  $$(".js-mini-map").forEach((node) => {
    if (!hasLeaflet()) return;
    const ll = [Number(node.dataset.lat), Number(node.dataset.lng)];
    const map = baseMap(node, ll, 14);
    L.circleMarker(ll, { radius: 11, color: "#fff", weight: 3, fillColor: STATUS_COLORS[node.dataset.color] || "#2563eb", fillOpacity: 0.95 }).addTo(map);
  });

  const picker = $(".js-picker");
  if (picker) {
    if (!hasLeaflet()) picker.hidden = true;
    else {
      const latIn = $("#f-lat"), lngIn = $("#f-lng");
      const geo = $(".js-geo");
      const start = latIn.value ? [Number(latIn.value), Number(lngIn.value)] : [47.915, 106.93];
      const map = baseMap(picker, start, latIn.value ? 15 : 11);
      let marker = latIn.value ? L.marker(start).addTo(map) : null;
      map.on("click", (e) => {
        latIn.value = e.latlng.lat.toFixed(5); lngIn.value = e.latlng.lng.toFixed(5);
        if (marker) marker.setLatLng(e.latlng); else marker = L.marker(e.latlng).addTo(map);
      });
      const recenter = () => {
        const districts = geo._districts || [];
        const d = districts.find((x) => String(x.id) === $(".js-district", geo).value);
        if (!d) return;
        const k = d.khoroos.find((x) => String(x.id) === $(".js-khoroo", geo).value);
        map.flyTo(k ? [k.lat, k.lng] : [d.lat, d.lng], k ? 15 : 13, { duration: 0.6 });
      };
      geo.addEventListener("geo-change", recenter);
      if (!latIn.value) recenter();
    }
  }

  /* ---------- Гишүүний самбар: табууд, байгууллага ---------- */
  $$(".js-tabs").forEach((tabs) => {
    const card = tabs.closest(".card");
    tabs.addEventListener("click", (e) => {
      const b = e.target.closest("button[data-tab]");
      if (!b) return;
      $$("button", tabs).forEach((x) => x.classList.toggle("active", x === b));
      $$("[data-panel]", card).forEach((p) => { p.hidden = p.dataset.panel !== b.dataset.tab; });
    });
  });
  $$(".js-org").forEach((s) => s.addEventListener("change", () => {
    const other = s.closest("form").querySelector(".js-org-other");
    other.hidden = s.value !== "__other__";
    $("input", other).required = s.value === "__other__";
  }));
  document.addEventListener("click", (e) => {
    const t = e.target.closest(".js-toggle");
    if (!t) return;
    const target = $(t.dataset.target);
    if (target) { target.hidden = !target.hidden; if (!target.hidden) { const ta = $("textarea", target); if (ta) ta.focus(); } }
  });

  /* ---------- Өмнө / дараа гулсуур ---------- */
  $$(".js-ba").forEach((box) => {
    const range = $("input[type=range]", box), before = $(".ba-before", box), line = $(".ba-line", box), knob = $(".ba-knob", box);
    const upd = () => {
      const v = range.value;
      before.style.clipPath = `inset(0 ${100 - v}% 0 0)`;
      line.style.left = `${v}%`; knob.style.left = `${v}%`;
    };
    range.addEventListener("input", upd); upd();
  });

  /* ---------- Бусад ---------- */
  document.addEventListener("click", async (e) => {
    const c = e.target.closest(".js-copy");
    if (!c) return;
    try { await navigator.clipboard.writeText(c.dataset.copy); toast("Холбоос хуулагдлаа 🔗"); }
    catch (_) { toast(c.dataset.copy, "info"); }
  });
  $$(".js-demo-login").forEach((b) => b.addEventListener("click", () => {
    const form = b.closest(".auth-card").querySelector("form");
    form.elements.email.value = b.dataset.email;
    form.elements.password.value = b.dataset.password;
    form.submit();
  }));
  document.addEventListener("click", async (e) => {
    const b = e.target.closest(".js-demo-boost");
    if (!b) return;
    b.disabled = true; b.textContent = "Иргэд дэмжиж байна...";
    try {
      const d = await post(`/issues/${b.dataset.id}/demo-boost`);
      setSupport(b.dataset.id, $(`.js-support[data-id="${b.dataset.id}"]`)?.classList.contains("supported") || false, d.count);
      setPriority(d.priority);
      toast(`👥 ${d.count} дэмжигч · ач холбогдол ${d.priority}/100`);
      setTimeout(() => location.reload(), 1100);
    } catch (err) { toast(err.message, "error"); b.disabled = false; }
  });

  // Админ: гишүүний хороо сонгогч
  $$(".js-khoroo-picker").forEach((root) => {
    const districts = JSON.parse(root.dataset.districts || "[]");
    let selected = new Set(JSON.parse(root.dataset.selected || "[]").map(String));
    const ds = $(".js-kp-district", root), grid = $(".js-kp-grid", root);
    const draw = () => {
      const d = districts.find((x) => String(x.id) === ds.value);
      grid.replaceChildren();
      if (!d) { grid.append(el("span", { class: "muted small", text: "Эхлээд дүүрэг сонгоно уу." })); return; }
      d.khoroos.forEach((k) => {
        const cb = el("input", { type: "checkbox", name: "khoroo_ids", value: k.id });
        cb.checked = selected.has(String(k.id));
        cb.addEventListener("change", () => { if (cb.checked) selected.add(String(k.id)); else selected.delete(String(k.id)); });
        grid.append(el("label", {}, cb, String(k.number)));
      });
    };
    ds.addEventListener("change", () => { selected = new Set(); draw(); });
    $(".js-kp-all", root).addEventListener("click", () => { $$("input", grid).forEach((c) => { c.checked = true; selected.add(c.value); }); });
    $(".js-kp-none", root).addEventListener("click", () => { $$("input", grid).forEach((c) => { c.checked = false; }); selected.clear(); });
    draw();
  });

  // Графикийн tooltip
  let tip;
  document.addEventListener("mouseover", (e) => {
    const t = e.target.closest("[data-tip]");
    if (!t) { if (tip) tip.hidden = true; return; }
    if (!tip) { tip = el("div", { class: "viz-tip", role: "tooltip" }); document.body.append(tip); }
    tip.textContent = t.dataset.tip;
    tip.hidden = false;
  });
  document.addEventListener("mousemove", (e) => {
    if (!tip || tip.hidden) return;
    const x = Math.min(e.clientX + 14, window.innerWidth - tip.offsetWidth - 8);
    tip.style.left = `${x}px`; tip.style.top = `${e.clientY + 16}px`;
  });
})();
