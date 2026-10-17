# P0 runbook: infrastructure

P0 is done when the three acceptance checks in Plan §13 pass (the checklist is at the end). The code for P0 is in the repo. The remaining steps happen in your own Alpaca, Oracle and Cloudflare accounts, and only you can do them.

Use personal accounts only. Nothing goes on company hardware or tenants (Plan §1).

Notifications appear on the portal (the board website). Telegram is not needed; it's an optional extra described in the appendix.

Placeholders used below: `board.example.com` is your board hostname, `myteam` is your Zero Trust team name.

---

## 1. Alpaca: the free market-data source

**What it is.** [Alpaca](https://alpaca.markets) is a US broker with a developer API. MarketBoard uses it **only as a free source of stock-market data**: price bars, volume, live prices, the most-active/movers screener, and the trading calendar. That data is what the board ranks and draws zones from.

**What you sign up for.** A **paper trading** account, which is a simulated account with pretend money:
- it is free and open to anyone;
- you don't deposit money, link a bank, or complete the live brokerage application;
- the free **Basic** market-data plan comes with it by default. Basic is all MarketBoard needs: 15-minute-delayed full-market data, real-time IEX prices, and 200 requests per minute.

**Why it's safe.**
- MarketBoard never trades. The code can only read data, and a test fails the build if any order or position call ever appears.
- The scanner refuses to start unless it is pointed at the paper (pretend-money) endpoint, so live keys can't be used by mistake.

**Get the keys**
1. Go to <https://alpaca.markets> → *Sign up*. Enter your email and a password, then verify your email.
2. In the dashboard, make sure the account switcher (top-left) says **Paper**, not Live.
3. Find the **API Keys** panel on the paper dashboard home page → *Generate New Keys*.
4. Copy the **Key ID** and **Secret Key** somewhere safe for now. The secret is shown only once; if you lose it, generate new keys. You'll put both into the VM's env file in §5.
5. The endpoint shown next to the keys should be `https://paper-api.alpaca.markets`.

Don't buy a data subscription. The $99/month plan is only for intraday real-time trading, which this project deliberately does not do (Plan §14).

## 2. Oracle Cloud: account and VM

1. **Convert the account to Pay As You Go** so the idle A1 VM is not reclaimed (Plan §11):
   Console → *Billing & Cost Management* → *Upgrade and Manage Payment* → *Upgrade to Pay As You Go*.
   Always Free shapes stay $0.
2. **Budget alert at $1**: *Billing & Cost Management* → *Budgets* → *Create Budget*.
   Target the root compartment, monthly, amount `1` USD. Add an alert rule on **Actual** spend at 100% that emails you.
3. **Create the VM**: shape `VM.Standard.A1.Flex` (for example 2 OCPU / 12 GB, inside the Always Free 4 OCPU / 24 GB), image **Canonical Ubuntu 24.04 (aarch64)**, and your SSH public key.
   If you get "Out of host capacity", retry later or pick another availability domain.
4. **Network, inbound**: in the subnet's Security List or an NSG, allow only `TCP 22` from `<your-ip>/32`. Delete the default `0.0.0.0/0` SSH rule. Add no other inbound rules, because the scanner is outbound-only.

## 3. VM hardening and scanner install

SSH in as `ubuntu`. Keep this session open until you have confirmed that a second SSH login still works.

```bash
# Key-only SSH, no root login
sudo tee /etc/ssh/sshd_config.d/99-marketboard.conf >/dev/null <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
EOF
sudo sshd -t && sudo systemctl reload ssh

# Automatic security updates
sudo apt update && sudo apt install -y unattended-upgrades git python3.12-venv
sudo dpkg-reconfigure -plow unattended-upgrades
```

Clone the repo to `/opt/marketboard` with a **read-only deploy key** (GitHub → repo *Settings* → *Deploy keys* → *Add*, leave "Allow write access" off):

```bash
sudo ssh-keygen -t ed25519 -N "" -C marketboard-vm -f /root/.ssh/marketboard_deploy
sudo cat /root/.ssh/marketboard_deploy.pub         # paste into GitHub as a deploy key
# Check the github.com host key fingerprint against GitHub's published fingerprints before accepting
sudo git clone -c core.sshCommand="ssh -i /root/.ssh/marketboard_deploy" \
  git@github.com:pgouda21/Order-block.git /opt/marketboard
sudo /opt/marketboard/scanner/deploy/install.sh
```

`install.sh` does the following and is safe to re-run after each `git pull`:
- creates the unprivileged `marketboard` user and `/var/lib/marketboard` (0700);
- creates the venv;
- creates `/etc/marketboard/env` (0600, owned by `marketboard`) from `.env.example`, and never overwrites it once it exists;
- installs the systemd units.

**Do not enable `marketboard.service` yet.** The scheduler arrives in P1.

## 4. Cloudflare: D1, Worker, Access

Prerequisites: your domain is on Cloudflare, and Zero Trust is set up on the Free plan. Your team domain is `myteam.cloudflareaccess.com` (Zero Trust → *Settings*).

Do the following from a checkout on your laptop:

```bash
cd worker && npm ci
npx wrangler login
npx wrangler d1 create marketboard          # copy database_id into wrangler.toml
```

Edit `worker/wrangler.toml`:
- set `database_id`;
- uncomment `routes` and set your hostname (`board.example.com`).

`workers_dev` and `preview_urls` stay `false`, so the Worker has no address outside Access.

```bash
(cd ../web && npm ci && npm run build)
npx wrangler d1 migrations apply marketboard --remote
npx wrangler deploy
```

Until the secrets below are set, every request gets a 500. That is intentional: the Worker refuses to run without them.

**Access application**: Zero Trust → *Access* → *Applications* → *Add* → *Self-hosted*.
- Domain: `board.example.com`, path empty (covers the UI and all of `/api`).
- Policy 1, *Allow*: Include → Emails → you plus your allowlist.
- Policy 2, *Service Auth*: Include → Service Token → `marketboard-scanner` (create it first, see below).
- Copy the application's **AUD tag**.

**Service token**: Zero Trust → *Access* → *Service credentials* → *Service Tokens* → *Create* `marketboard-scanner`. A 1-year duration is suggested; set a renewal reminder. Save the Client ID and Client Secret; the secret is shown only once.

**Worker secrets** (from `worker/`):

```bash
npx wrangler secret put ACCESS_TEAM_DOMAIN               # myteam.cloudflareaccess.com
npx wrangler secret put ACCESS_AUD                       # the AUD tag
npx wrangler secret put INGEST_SERVICE_TOKEN_CLIENT_ID   # the service token Client ID (ends in .access)
```

## 5. Fill the env file and run the self-test

```bash
sudo nano /etc/marketboard/env    # install.sh re-applies 0600 / marketboard ownership if you re-run it
```

| Key | Value |
|---|---|
| `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` | the paper Key ID and Secret Key from §1 |
| `ALPACA_BASE_URL` | `https://paper-api.alpaca.markets` (do not change) |
| `CF_INGEST_URL` | `https://board.example.com/api/ingest` |
| `CF_ACCESS_CLIENT_ID`, `CF_ACCESS_CLIENT_SECRET` | the service token from §4 |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | leave blank (Telegram off) |

```bash
sudo systemctl start marketboard-selftest
journalctl -u marketboard-selftest -n 20 --no-pager
```

Expected:

```
PASS  config    paper endpoint enforced, settings.yaml valid
PASS  alpaca    market closed; next open 2026-10-19 09:30 EDT
PASS  ingest    service-token ingest returned 200
SKIP  telegram  off; alerts and digests show on the portal
```

The self-test runs as `marketboard` under the same sandbox as the real service, so a PASS also proves the env file permissions and outbound network work.

If a check fails:
- `alpaca: … forbidden` or `unauthorized`: the keys are wrong or mistyped, or they are live keys instead of paper keys.
- `ingest: HTTP 302 … service token was not accepted`: Policy 2 is missing or is not of type *Service Auth*, or the client ID/secret is wrong.
- `ingest: HTTP 403`: the token's Client ID doesn't match `INGEST_SERVICE_TOKEN_CLIENT_ID`.
- `ingest: HTTP 500`: the Worker secrets are not set.
- `ingest: HTTP 401`: `ACCESS_AUD` or `ACCESS_TEAM_DOMAIN` is wrong.

---

## P0 acceptance checklist (Plan §13)

| # | Criterion | How to verify | Expected |
|---|---|---|---|
| 1 | Access blocks unauthenticated requests | `curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' https://board.example.com/api/board/latest` (repeat for `/` and `-X POST …/api/ingest/ping`) | `302` to `myteam.cloudflareaccess.com`, never `200` |
| 1b | The Worker rejects requests without a valid JWT, even if Access is misconfigured | `cd worker && npm run check` (also runs in CI) | all tests pass; every route returns 401 without a JWT |
| 2 | Service-token ingest returns 200 | self-test `ingest` line, or `curl -s -X POST -H "CF-Access-Client-Id: $ID" -H "CF-Access-Client-Secret: $SECRET" https://board.example.com/api/ingest/ping` | `PASS` / `{"ok":true}` |
| 3 | Oracle PAYG + budget alert | OCI console: account type and *Budgets* | PAYG; $1 budget with an email alert rule |
| — | Phone sanity check (not a P0 criterion) | open `https://board.example.com` on your phone and sign in | "Signed in. API reachable. No board published yet." |

When all rows pass, report the results and move to P1 (data).

---

## Appendix: Telegram (optional, off)

You don't need this. Alerts and digests appear on the portal. If you ever want them pushed to your phone as well:

1. In Telegram, message `@BotFather` → `/newbot` and save the token.
   Then `/setjoingroups` → *Disable*, so nobody can add the bot to a group.
2. Send any message to your new bot from your own account.
3. On the VM, read your chat id without leaving the token in shell history:
   ```bash
   read -rs TOKEN && curl -s "https://api.telegram.org/bot$TOKEN/getUpdates" | python3 -m json.tool | grep -A3 '"chat"'
   unset TOKEN
   ```
4. Put the token and `chat.id` into `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` in `/etc/marketboard/env`, then re-run the self-test. The `telegram` line turns into `PASS` and a test message arrives.

The scanner only ever sends to that one chat and never reads incoming messages.
