# ХОЛБООС (Holboos)

> **Иргэний асуудлаас бодит шийдэл хүртэл.** — From a citizen's problem to a real solution.

An official civic platform connecting citizens with Members of Parliament (УИХ-ын гишүүд).
Citizens report problems, neighbours support them, the constituency MP accepts and responds,
the issue is forwarded to the responsible government organization, resolution evidence
(before/after photos) is published, and citizens confirm whether it was *actually* fixed —
all in one transparent, auditable timeline.

Stack: **Python · FastAPI · SQLAlchemy · SQLite · Jinja2 · vanilla JS/CSS**. No build step, no external services required.

---

## 1. Run it

```bash
pip install -r requirements.txt
cp .env.example .env          # then set SECRET_KEY (see below)
python run.py                 # or: uvicorn app.main:app --reload
```

Open **http://127.0.0.1:8000**.

On the first start the app creates `holboos.db` and seeds realistic Mongolian demo data
automatically (~10 s — it hashes passwords and draws the illustrations). Subsequent starts are instant.

Generate a secret key for `.env`:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Reset the demo data at any time (e.g. before presenting):

```bash
python -m app.seed --reset
```

### Deploy (Render)

The repo includes `render.yaml`. On [render.com](https://render.com): **New → Blueprint → select this repo → Apply**.
It installs the requirements, generates `SECRET_KEY`, and starts
`uvicorn app.main:app --host 0.0.0.0 --port $PORT`. The demo data seeds itself on first boot.

- With the default SQLite, data resets whenever the free instance restarts (fine for demos).
- For persistent data, create a Render PostgreSQL database and set `DATABASE_URL` to its URL
  (`postgres://…` is converted automatically to the `psycopg` driver). Uploaded photos still need a persistent disk.
- Free instances sleep after ~15 min idle; open the site once before presenting.

GitHub Pages and Vercel are not suitable: Pages can't run Python, and Vercel's serverless functions can't keep the SQLite file or uploaded images.

## 2. Demo accounts

All demo accounts use the password **`Holboos2026!`** (configurable via `DEMO_PASSWORD` in `.env`;
stored in the database only as an Argon2id hash). On the login page you can also click an account card to sign in with one click.

| Role | Email | Who |
|---|---|---|
| Citizen | `citizen@holboos.mn` | Д.Сарангэрэл — Bayanzurkh, khoroo 26 |
| MP | `mp@holboos.mn` | Г.Бат-Эрдэнэ — Bayanzurkh constituency, khoroos 1, 2, 3, 4, 26 |
| Admin | `admin@holboos.mn` | Platform administrator |
| Citizen 2 | `bold@holboos.mn` | Б.Болд — Bayanzurkh, khoroo 3 |

Other seeded logins (same password): MPs `narantuya@`, `ganzorig@`, `enkhtuya@`, `temuulen@`, `zolboo@`, `munkhbat@`;
citizens `tsetseg@`, `solongo@`, `uyanga@`, `temuujin@`, `oyunaa@`, `anar@`, `munkhzul@`, `ganbold@`, `erdene@`, `nomin@`, `khulan@`, `batbayar@` (all `@holboos.mn`).
The 120 `irgenNNN@demo.holboos.mn` accounts are background supporters with random, unknown passwords (they cannot log in).

## 3. Live demo script (≈ 5 minutes)

Sample photos for uploading are in **`demo_images/`** (`01_zam_evdrel_umnu.jpg` = damaged road, `02_zam_zasvarlasan_daraa.jpg` = repaired road).

| # | Step | Where / what to click |
|---|---|---|
| 1 | Login as citizen | `/login` → **Иргэн** card |
| 2–3 | Create *“26-р хорооны замын эвдрэл”* | **＋ Асуудал мэдээлэх** → title, category *Зам, дэд бүтэц*, description, district/khoroo (pre-filled: Баянзүрх / 26), photo `01_…` → **Асуудал илгээх**. The right panel shows which MP it will go to. |
| 4–5 | Other citizens support it | On the issue page, sidebar **🧪 Демо горим → Иргэдийн дэмжлэг цуглуулах** (+30 supporters, 3 comments). Priority jumps to ~70+/100 → *high priority*. *(Or log in as `bold@` and click 👍 Дэмжих.)* |
| — | *Duplicate detection (optional)* | As `bold@`, start reporting *“26-р хорооны зам эвдэрсэн”* in Баянзүрх / 26 → *“Энэ асуудал өмнө нь мэдээлэгдсэн байна.”* with a one-click **Үүнийг дэмжих**. |
| 6–7 | Login as MP | `/login` → **УИХ-ын гишүүн**. The dashboard shows the issue under **⚡ Шуурхай анхаарах** and **📍 Таны тойргийн асуудлууд** (tagged *Таны хороо*). |
| 8–9 | Open & accept | Click the issue → gold **Гишүүний үйлдэл** panel → **✅ Асуудлыг хүлээн авах** |
| 10 | Status → *Шалгаж байна* | Tab **🔄 Статус** |
| 11 | Official response | Tab **🏛️ Албан хариу** — renders as a distinct 🏛️ АЛБАН ЁСНЫ ХАРИУ card, separate from comments |
| 12 | Forward to organization | Tab **📨 Шилжүүлэх** → e.g. *Нийслэлийн Авто замын газар* |
| 13 | Status → *Шийдвэрлэж байна* | Tab **🔄 Статус** |
| 14–15 | Upload evidence & resolve | Tab **✅ Шийдвэрлэх** → explanation, action taken, date, AFTER photo `02_…` → **Шийдвэрлэсэн гэж тэмдэглэх** |
| 16–18 | Citizen confirms | Log in as citizen → notification 🔔 → issue shows the full timeline, before/after slider → **✅ Тийм, шийдэгдсэн** (or **❌ Үгүй** with a reason + optional photo) |
| 19 | Admin sees everything | Log in as admin → **Асуудлууд** → **🔎 Аудит** on the issue: every status change, response, forward, comment and confirmation in order |

## 4. What's implemented

**Citizens** — register/login/logout · Facebook-style feed (tabs: new / 🔥 top / most supported / resolved, search, district/status/category filters, infinite "load more") · issue cards with author, image, district/khoroo, category, date, support & comment counts, status, relevant MP, priority · **👍 Дэмжих** (one support per citizen, toggle) · inline comments · create issue with photo, category tiles, district → khoroo cascade, optional map pin, urgency and affected scope · live **duplicate detection** · issue detail with 6-step status timeline, full activity log, official responses, before/after comparison slider, citizen confirmation (Yes / No + reason + photo) · My issues (reported / supported / awaiting confirmation) · notifications · profile & password change.

**MPs** — separate dashboard prioritized by constituency (assigned khoroos → constituency district → most supported → highest priority) with sections *Шуурхай анхаарах шаардлагатай*, *Таны тойргийн асуудлууд*, *🔥 Топ асуудлууд*, *Хамгийн их дэмжигдсэн*, *Шийдвэрлэгдэж буй*, *Шийдвэрлэгдсэн*, per-khoroo chart and KPIs (avg. response time, citizen satisfaction) · filtered lists (constituency / new / in progress / resolved / urgent) · actions: accept, change status, official response, progress update, forward to organization, resolve with evidence (after photo required), reopen · public MP scorecards at `/mps`.

**Admin** — dashboard (users, citizens, MPs, total/new/in-progress/resolved issues; weekly created-vs-resolved chart; status, district and category breakdowns; recent activity; MP performance) · users: search, filter, edit, change role, block, reset password, delete (with confirmation) · MPs: create/edit/delete, assign district, constituency and khoroos (checkbox grid), focus categories, photo · issues: list, full audit trail, reassign MP, delete · comment moderation (hide / restore / delete) · reports + CSV export · settings (announcement banner, priority/support/duplicate thresholds, registration on/off, demo mode).

**Also** — issue map (Leaflet + OpenStreetMap) with status-colored markers, popups and district zoom · notifications for support, comments, acceptance, status changes, official responses, resolution, high-priority / high-support issues and disputes · responsive down to phone width · procedurally drawn before/after illustrations so the demo works offline.

### Priority score (0–100)
`support 45 (log-scaled, full at ~40) + comments 15 + age 10 (full at 30 days open) + urgency 20 + affected scope 10`.
Shown as *Ач холбогдол 87/100* with a breakdown on the issue page. Recomputed on every support/comment/status change and on startup.

### Duplicate detection
Titles are lower-cased, stop-words removed, and each word reduced to a 3-letter stem (approximating Mongolian suffixes: *замын → зам*, *эвдэрсэн / эвдрэл → эвд*). Score = 0.6 × Dice similarity + 0.25 same category + 0.15 same khoroo, among unresolved issues in the same district. Shown live while typing; the server also blocks near-exact duplicates (≥ 0.75) unless the user confirms it's different.

## 5. Security

- Passwords hashed with **Argon2id** (`argon2-cffi`); constant-time login checks, no user enumeration.
- Signed session cookie (`HttpOnly`, `SameSite=Lax`, `Secure` via `SESSION_HTTPS_ONLY`), session cleared on login.
- **CSRF token** required on every POST (form field or `X-CSRF-Token` header).
- Role-based access: admin and MP routers are protected at router level; MPs can only act on issues assigned to them.
- Input validated with Pydantic (Mongolian error messages); SQLAlchemy ORM with bound parameters only.
- Uploads: extension + content check with Pillow, 5 MB limit, decompression-bomb guard, re-encoded to JPEG (strips EXIF/metadata; SVG/HTML rejected).
- Jinja2 autoescaping; JS inserts user text via `textContent` only; security headers (`nosniff`, `X-Frame-Options: DENY`, referrer policy).
- In-memory rate limits on login, registration, issue creation, comments and support.
- Secrets come from `.env` (git-ignored), never from source.

## 6. Project structure

```
app/
  main.py            app factory, middleware, error pages, startup (create tables + seed)
  config.py          settings from .env
  database.py        engine, session, Unicode-aware search helper
  constants.py       statuses, categories, urgency, organizations, districts
  seed.py            demo data (python -m app.seed --reset)
  templating.py      Jinja2 env, render(), flash messages
  auth/              password hashing, CSRF, role dependencies
  models/            User, MPProfile, District, Khoroo, Issue, IssueImage, Comment, Support,
                     OfficialResponse, IssueStatusHistory, Resolution, ResolutionConfirmation,
                     Notification, Setting
  schemas/           Pydantic form validation
  services/          issue workflow, priority, duplicates, notifications, uploads, stats,
                     charts, rate limiting, settings, image generator
  routers/           public, auth, issues, citizen, mp, admin
  templates/         Jinja2 pages (home, issues/, mp/, admin/, citizen/, auth/, mps/)
  static/            css/style.css, js/app.js, images/, uploads/
demo_images/         sample photos for the live demo
requirements.txt · .env.example · run.py
```

## 7. Configuration (`.env`)

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | *(random per process, with a warning)* | Signs session cookies |
| `DATABASE_URL` | `sqlite:///./holboos.db` | Any SQLAlchemy URL; PostgreSQL works with a driver installed (e.g. `psycopg`) |
| `DEMO_PASSWORD` | `Holboos2026!` | Password for seeded accounts |
| `DEMO_MODE` | `true` | Demo account cards on login + "simulate support" button (also toggleable in admin settings) |
| `MAX_UPLOAD_MB` | `5` | Image upload limit |
| `SESSION_HTTPS_ONLY` | `false` | Set `true` behind HTTPS |

## 8. Known limitations (prototype scope)

- **Map & fonts need internet** (OpenStreetMap tiles, Leaflet from cdnjs, Google Fonts). Offline, the map page falls back to the district list and fonts fall back to system fonts; everything else works offline.
- Khoroo and issue coordinates are **approximate** (generated around each district's center), not official boundaries.
- Rate limiting is in-memory (resets on restart, single process only).
- No email/SMS delivery — notifications are in-app only. No real identity verification (e.g. ДАН/e-Mongolia).
- Tables are created with `create_all` (no Alembic migrations); after changing models, run `python -m app.seed --reset`.
- Government organizations don't have their own accounts — the MP records forwarding and updates on their behalf.
- All people, issues and responses in the demo data are **fictional**.
