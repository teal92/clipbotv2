# ClipBot v2

ClipBot watches Twitch/Kick streams, spots moments worth clipping, asks an AI reviewer ("Davey", powered by the Anthropic API) to judge them, and lets you approve and publish clips to your social accounts.

> **This project is released as-is, with no support and no running service.** The original hosted website has been shut down. Nothing here includes anyone's API keys, accounts or data: you bring your own. Anything marked `YOUR-…` or `your-domain.example` in the code and docs is a placeholder to replace with your own information.

## How it fits together

ClipBot has two programs. You always need both.

| Program | Folder | What it does |
|---|---|---|
| **Server** (website + API) | `server/`, `frontend/` | Accounts, settings, AI spending limits, publishing coordination, the web pages you click around in |
| **Companion** (desktop app) | `worker/` | Runs on your PC. Watches streams, transcribes speech, makes the clips, uploads them. Your video never goes through the server |

The Companion talks to the Server. The question is where you run the Server. That gives you two paths.

## Pick your path

| | **Path A: Everything on your own PC** | **Path B: Server in the cloud** |
|---|---|---|
| Best for | Trying it out, learning, personal use | Running it for yourself on any device, or for other people |
| Server runs on | Your computer (`127.0.0.1`) | A cloud host (guide uses Render + Cloudflare) |
| Cost | Free, plus any AI usage on your own Anthropic key | Hosting fees, plus Anthropic, Stripe, email |
| Difficulty | Easy | Harder: domain, secrets, email, platform developer apps |
| AI review | Limited, advanced "owner test" mode (see Path A, step 4) | Full product, needs live Stripe billing set up |

Both paths can use the Companion run **from source** (easy, no build) or as a **built `.exe`** (Windows installer, see [Building the .exe](#building-the-windows-exe)).

## The stack

| Layer | Technology |
|---|---|
| Web frontend | Vanilla JavaScript (ES modules), HTML, CSS. No framework, no build step |
| Backend API | Python, FastAPI, Pydantic, Uvicorn |
| Database | SQLite (WAL mode) on a persistent disk. **Single instance only** |
| AI review | Anthropic API (model set in `server/claude_connection.py`) |
| Billing | Stripe (subscriptions, customer portal, signed webhooks) |
| Email | Resend over SMTP (verification, recovery, support reports) |
| Hosting (Path B) | Render web service with a 1 GB persistent disk (`render.yaml`) |
| Edge / DNS (Path B) | Cloudflare proxy, Full (strict) TLS |
| Companion | Python, FastAPI on loopback, pystray (tray icon), yt-dlp, faster-whisper (Whisper base), CTranslate2, ONNX VAD, PyAV, FFmpeg |
| Packaging | PyInstaller, Inno Setup (Windows installer) |
| Tests | pytest (backend), Node's built-in test runner (frontend) |

Dependencies are pinned with hashes (`requirements.txt`, `packaging/worker-build.lock`). Please keep it that way, and do not add packages you have not verified on the official package index.

## Before either path: install the basics

You need **Python 3.12** and **Node 20+** (Node is only for the tests). Commands below are Windows PowerShell; on macOS/Linux use `source .venv/bin/activate` and `python` in place of `.venv/Scripts/python.exe`.

```powershell
git clone https://github.com/teal92/clipbotv2.git
cd clipbotv2
python -m venv .venv
.venv/Scripts/python.exe tools/dependency_policy.py
.venv/Scripts/python.exe -m pip --isolated install -r requirements.txt
```

## Path A: everything on your own PC

**1. Start the server.**

```powershell
.venv/Scripts/python.exe -m ops.local_staging
```

Open http://127.0.0.1:8766 and create a local account. This preview listens only on your own PC, keeps its data in `.staging/clipbot.db`, and has billing, email and paid AI **switched off**. It is safe to experiment with.

**2. Install and run the Companion.**

```powershell
.venv/Scripts/python.exe -m pip --isolated install -r worker/requirements.txt
.venv/Scripts/python.exe -m worker.download_model        # downloads the Whisper base model (~150 MB)
$env:CLIPBOT_SERVICE_ORIGIN = 'http://127.0.0.1:8766'    # point it at your local server
.venv/Scripts/python.exe -m worker.companion
```

When running from source you also need `ffmpeg`, `ffprobe` and `yt-dlp` on your PATH (the installed `.exe` bundles its own).

**3. Pair them.** In the website, open the **Companion** page, create a pairing code, and enter it on the Companion's local page (tray icon, then Connection status). Then use **Start ClipBot**.

**4. Turn on AI review (advanced, bring your own key).** The preview ships with AI off. The server only sends a clip to the AI when one of two gates is open: a live-billed paid customer account (Path B), or a time-limited **owner test** switch, which is the one that fits your own PC. There is no button for it in the website, so this path needs some comfort with the command line. It is provided as-is, and AI usage and cost on your own machine are your responsibility.

- Create an Anthropic API key in your own Anthropic account and keep it private.
- Create your account in the preview once, then look up its ID: `.venv/Scripts/python.exe -c "import sqlite3;print(sqlite3.connect('.staging/clipbot.db').execute('select id,email from users').fetchall())"`
- Stop the preview and start the server yourself with these set in the same terminal: `CLIPBOT_ORIGIN=http://127.0.0.1:8766`, `CLIPBOT_LOCAL_SIGNUP=1`, `CLIPBOT_DB_PATH=.staging/clipbot.db`, `ANTHROPIC_API_KEY=<your key>`, `CLIPBOT_ADMIN_USER_ID=<your account ID>`, and non-zero `CLIPBOT_GLOBAL_DAILY_USD` / `CLIPBOT_GLOBAL_MONTHLY_USD` (hard spending stops). Leave `CLIPBOT_DEV_BYPASS` off and sign in with your normal account.
- Start command: `.venv/Scripts/python.exe -m uvicorn server.app:create_app --factory --host 127.0.0.1 --port 8766 --no-proxy-headers`
- Check your key works without spending anything: `.venv/Scripts/python.exe -m server.claude_connection`
- Accept the beta notice in the Davey page, then switch on the owner test by sending `POST /api/admin/pipeline-test` with body `{"enabled": true}` and your session's `x-csrf-token` header (`server/analysis_api.py`). It lasts one hour per switch and has a small built-in spending ceiling. `LIVE-PIPELINE-TEST.md` describes the intended flow.

Without AI you can still use capture, local transcription and preview. Never put your API key in a file that goes into git.

## Path B: server in the cloud

Reference setup: **Render + Cloudflare**, defined in `render.yaml`. Other hosts are not supported out of the box: the trusted-edge code in `server/client_ip.py` only activates on Render (`RENDER=true`) behind a verified Cloudflare. On another host, public signup stays closed until you review and adapt that design. Do not work around it with generic proxy-header trust, which would let anyone fake an IP address and dodge abuse limits.

**Costs.** A Render web service with a disk is a paid plan. Anthropic, Stripe and Resend usage is billed to *you*. Nothing is created until you create the service.

**Steps**

1. **Fork or push this repo** to your own GitHub account.
2. **Create the Render service.** New, then Blueprint, pointing at your repo. It reads `render.yaml`:
   - Build: checks the dependency policy, installs a hash-pinned pip, then installs `requirements.txt`
   - Start: `uvicorn server.app:create_app --factory --no-proxy-headers`
   - Health check: `/healthz`
   - A 1 GB disk mounted at `/var/data` (holds the SQLite database)
3. **Add secrets in the Render dashboard** (never in git). `.env.example` lists every name:

   | Variable | Purpose |
   |---|---|
   | `CLIPBOT_ORIGIN` | Your public `https://` address, exactly. Used for Host/Origin checks |
   | `CLIPBOT_DB_PATH` | `/var/data/clipbot.db` |
   | `CLIPBOT_GLOBAL_DAILY_USD`, `CLIPBOT_GLOBAL_MONTHLY_USD` | Hard AI spending stops across all users. **Set these to what you can afford** |
   | `ANTHROPIC_API_KEY` | Your own key. Leave unset to keep AI off |
   | `CLIPBOT_TOKEN_ENCRYPTION_KEY` | Encrypts stored social-account tokens. Generate once and back it up |
   | Stripe key, webhook secret (`whsec_…`), price IDs | Only to charge for plans. Create your own products in your Stripe account |
   | `CLIPBOT_REPORT_SMTP_*`, `CLIPBOT_REPORT_EMAIL`, `CLIPBOT_REPORT_FROM` | Email delivery |
   | Twitch/Kick/Meta/TikTok app IDs and secrets | From your own developer accounts. See `OAUTH-SETUP.md` |
   | `CLIPBOT_PUBLIC_SIGNUP` | `1` opens signup. Needs working email and a verified edge |

   Keep `CLIPBOT_DEV_BYPASS` and `CLIPBOT_LOCAL_SIGNUP` at `0` in production.
4. **Put the domain behind Cloudflare** with SSL/TLS on *Full (strict)*. See `docs/LAUNCH-EDGE-DESIGN.md`.
5. **Check it:** open `/healthz`, confirm an unauthenticated API call is rejected, create an account, and pair a Companion with `CLIPBOT_SERVICE_ORIGIN` set to your site's address.
6. **Verify your Anthropic key** in the Render shell: `python -m server.claude_connection`. It reads model info only and sends no billable request.
7. **Fill in the placeholders** for your business: search the repo for `YOUR COMPANY NAME`, `YOUR STATE`, `your-domain.example` and `YOUR-` (legal pages in `server/legal.py`, support email in `server/report_delivery.py`, download repository in `server/companion_remote_download.py`, and so on). The bundled Terms and Privacy text is a starting draft, not legal advice; have your own counsel review it.

**Rules of the road**

- **One instance only.** Locking and rate limits assume a single process. Do not add instances or workers without redesigning storage and the shared spending budget.
- **Back up** the database. See `docs/ENCRYPTED-BACKUP-RUNBOOK.md` and `OPERATOR-GUIDE.md`.
- **Keep the spending caps.** AI cost is reserved before each call and capped per user, per day and per month.

## Building the Windows `.exe`

Optional for both paths. It produces a PyInstaller bundle and then an Inno Setup installer. The build is strict: it refuses to run unless every bundled tool, the model and the lock files match recorded SHA-256 hashes in `packaging/release-inputs.json`. That keeps builds reproducible, but you must supply the exact files it lists.

**Requirements:** Windows 10/11 x64, CPython **3.12.14** x64 exactly, Git with a clean working tree, PowerShell.

1. **Create the build environment from the hashed lock** (not a fresh resolve):

   ```powershell
   python -m venv .venv
   .venv/Scripts/python.exe -m pip --isolated install --require-hashes -r packaging/worker-build.lock
   ```

2. **Download the transcription model** into `worker/data/models/base/`:

   ```powershell
   .venv/Scripts/python.exe -m worker.download_model
   ```

3. **Place the pinned tools under `packaging/tools/`** (git-ignored). Each file must match its hash in `packaging/release-inputs.json`:
   - `ffmpeg.exe`, `ffprobe.exe`, `yt-dlp.exe`
   - `runtime/`: `msvcp140.dll`, `msvcp140_1.dll`, `vcruntime140.dll`, `vcruntime140_1.dll`
   - `wheels/av-18.0.0-cp311-abi3-win_amd64.whl`
   - `compiler/`: an Inno Setup compiler folder (contains `ISCC.exe`)
   - `packaging/native/corresponding-source.zip`: source bundle for the bundled FFmpeg/PyAV libraries (see `docs/COMPANION-SELF-BUILD.md` and `tools/native_source_bundle.py`)

4. **Commit, then build:**

   ```powershell
   git status                          # must be clean
   ./packaging/build-companion.ps1
   ```

   It verifies inputs, runs PyInstaller (`packaging/companion.spec`), audits the bundle, compiles the installer (`packaging/clipbot-companion.iss`) and writes `packaging/dist/ClipBotCompanionSetup.exe` plus a `manifest.json` with its SHA-256.

**Different tool versions:** the hash check will stop you on purpose. Update the matching entries in `packaging/release-inputs.json` and the notices in `packaging/licenses/`, keep the source records accurate, and review the change. Do not remove the check to make a build pass.

**Before sharing a build:** install it on a clean PC and confirm it opens, pairs, updates and uninstalls. Your build will be unsigned, so Windows SmartScreen will warn; code signing needs your own certificate. The macOS build (`packaging/build-native.py`, notes in `MACOS-LINUX-COMPANION-DESIGN.md`) is experimental; Linux is unfinished.

To point an installed Companion at your server, set `CLIPBOT_SERVICE_ORIGIN` (HTTPS, or `http://127.0.0.1:PORT`) for your Windows user: `setx CLIPBOT_SERVICE_ORIGIN "https://your-site.example"`. An invalid value stops the Companion with a message instead of silently using another server.

## Tests

```powershell
.venv/Scripts/python.exe -m pytest tests -q
node --test tests/*.test.mjs      # PowerShell: list the .test.mjs files explicitly if the glob fails
```

Some companion tests need Windows or a working system keyring and fail elsewhere.

## Security

- Never commit `.env` files, database files, API keys or tokens. `.env.example` has names only.
- Treat transcripts, model output and chat text as data; never execute or evaluate them.
- Each person should use their own API keys, accounts and developer apps.

## More docs

[OPERATOR-GUIDE.md](OPERATOR-GUIDE.md) (reports, backups, restore) · [LIVE-PIPELINE-TEST.md](LIVE-PIPELINE-TEST.md) · [OAUTH-SETUP.md](OAUTH-SETUP.md) · [docs/STAGING-WORKFLOW.md](docs/STAGING-WORKFLOW.md) · [docs/COMPANION-SELF-BUILD.md](docs/COMPANION-SELF-BUILD.md) · [CHANGELOG.md](CHANGELOG.md)

## License

No license is attached. By default, that means others do not have legal permission to copy, change or share the code. If you want people to be free to use it, add a license file such as the Unlicense or MIT.
