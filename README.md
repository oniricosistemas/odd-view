# AI Reviewer coordinator

A constrained GitHub App service that coordinates one consolidated, multi-pass PR review. It never checks out a repository, executes repository code, follows content-derived URLs, approves, requests changes, merges, or applies fixes. Deterministic CI is a separate system.

## Pipeline and trust boundary

1. The loopback FastAPI endpoint streams at most 1 MiB, verifies `X-Hub-Signature-256` over the raw bytes, accepts GitHub's extensible envelope, then projects required fields into a strict internal schema. Delivery UUID plus body hash detects replay-ID collisions.
2. SQLite durably records deliveries and runs. The unique run key is `(repository_id, pull_number, head_sha, policy_version)`. Webhook order never cancels another head; live GitHub state is authoritative. WAL, fenced renewable leases, bounded retries, and a durable publication lock/outbox are enabled.
3. A worker obtains a short-lived installation token from a locally signed GitHub App JWT, fetches the PR and paginated files from fixed GitHub REST 2022-11-28 endpoints, and never follows redirects.
4. Passes are fixed by local policy: `gemini-rotativo` primary, `OpenCode-Free` adversarial, deterministic-risk `OpenRoute-Free` specialist, and non-authoritative `Ollama` wording suggestions. `auto/*` and every other model ID are rejected.
5. Strict bounded JSON findings/verdicts are checked against repository-relative paths and right-side lines present in the patch. Only explicitly confirmed primary or specialist findings survive; amendments are revalidated. A deterministic reducer deduplicates, fingerprints, sorts, and caps output at eight.
6. The worker checks live PR state around every side effect. It reconciles an HMAC-authenticated marker and Check Run `external_id` only for the configured bot/App and exact commit, producing one `COMMENT` review and one completed successful Check Run. Hostile model text is escaped and remote links/mentions are neutralized.

Untrusted PR titles, bodies, patches, and model responses are data only. They cannot select a model, endpoint, action, token, or publication mode. Logs intentionally exclude webhook payloads, tokens, and diffs.

## GitHub App

Create this outside the repository. Required repository permissions:

- **Contents: read**
- **Pull requests: write**
- **Checks: write**
- Metadata is implicit.

Subscribe only to pull request events. Point the webhook to a TLS reverse proxy that forwards to the default `127.0.0.1:8080`. This repository does not create the App or contain credentials.

## Configuration

Copy `deploy/config.example.json` outside the checkout. Configuration can be overridden with `AI_REVIEWER_APP_ID`, `AI_REVIEWER_REVIEW_AUTHOR_ID`, `AI_REVIEWER_DATABASE_PATH`, `AI_REVIEWER_OMNIROUTE_BASE_URL`, `AI_REVIEWER_POLICY_VERSION`, `AI_REVIEWER_HOST`, and `AI_REVIEWER_PORT`. The API host must be loopback unless `allow_remote_api` is explicitly true.

Remote OmniRoute endpoints and the included example use HTTPS by default. Plain HTTP on a trusted LAN is available only by explicitly setting `allow_insecure_omniroute=true`; this opt-in applies only to the exact configured base URL, redirects remain disabled, and LAN traffic (including prompts and API credentials) is vulnerable to interception.

Secrets are accepted **only** through files:

- `AI_REVIEWER_WEBHOOK_SECRET_FILE`
- `AI_REVIEWER_APP_PRIVATE_KEY_FILE`
- `AI_REVIEWER_MARKER_SECRET_FILE`
- optional `AI_REVIEWER_OMNIROUTE_API_KEY_FILE`

Inline secret environment variables and secret-valued JSON fields are rejected. Secrets must contain at least 32 characters and no surrounding whitespace. `.env.example` contains path placeholders only. The separate systemd units use `LoadCredential=` and least privilege: the API receives only the webhook secret; the base worker receives only the App key and marker secret. Store real credential files under `/etc/ai-reviewer/credentials/` with root-only permissions, never in this repository. Configure `review_author_id` as the GitHub bot user's numeric ID and `app_id` as the GitHub App's numeric ID.

OmniRoute authentication is optional, so the base worker unit deliberately does not reference a credential that may not exist. When the configured router requires authentication, add a systemd drop-in with `systemctl edit ai-reviewer-worker.service`:

```ini
[Service]
Environment=AI_REVIEWER_OMNIROUTE_API_KEY_FILE=%d/omniroute-api-key
LoadCredential=omniroute-api-key:/etc/ai-reviewer/credentials/omniroute-api-key
```

## Development and verification

```text
uv python install 3.11
uv sync --python 3.11 --all-groups
uv run --python 3.11 pytest -q
uv run --python 3.11 python -m compileall -q src tests
```

Tests use real temporary SQLite databases and `httpx.MockTransport`; they need no network, App, or secrets.

## Debian 12 deployment

Install `uv`, create the distinct `ai-reviewer-api` and `ai-reviewer-worker` system users in a shared `ai-reviewer-state` group, and deploy this checkout at `/opt/ai-reviewer`. The shared group is only for `/var/lib/ai-reviewer` (mode `0770`); credential source files remain root-owned and each unit receives only its own `LoadCredential=` entries. Then:

```text
groupadd --system ai-reviewer-state
useradd --system --no-create-home --gid ai-reviewer-state --shell /usr/sbin/nologin ai-reviewer-api
useradd --system --no-create-home --gid ai-reviewer-state --shell /usr/sbin/nologin ai-reviewer-worker
cd /opt/ai-reviewer
uv sync --python 3.11 --all-groups --frozen
install -D -m 0644 deploy/ai-reviewer-api.service /etc/systemd/system/ai-reviewer-api.service
install -D -m 0644 deploy/ai-reviewer-worker.service /etc/systemd/system/ai-reviewer-worker.service
install -D -m 0644 deploy/config.example.json /etc/ai-reviewer/config.json
systemctl daemon-reload
systemctl enable --now ai-reviewer-api.service ai-reviewer-worker.service
```

Replace every placeholder and provision credentials before starting. Multiple workers are fenced by SQLite run leases and the publication CAS lock. The API exposes unauthenticated loopback-only `GET /healthz` and `GET /readyz`; readiness verifies SQLite access. Use a reverse proxy to expose only `POST /webhook` and enforce its own request/time limits.

## Operations

- Back up the SQLite database with the SQLite online backup mechanism while services run.
- Rotate credentials by replacing credential source files and restarting both units.
- Transient failures retry with bounded exponential backoff, then remain durable as `failed`; oversized reviews terminate as neutral `incomplete`. Before any remote side effect, the worker stores one immutable snapshot containing the rendered review/check payloads and local result. Takeover reuses that exact snapshot and reconciles the marker/App/commit before posting.
- GitHub does not provide an idempotency key for review or Check Run creation. If a POST response is lost, the run enters durable ambiguity tracking and uses real deterministic-jitter backoff to look for the exact authenticated object. It never repeats that POST during reconciliation; exhaustion leaves the run terminal as `ambiguous` for manual reconciliation. The authenticated marker, exact App/author and commit checks are the reconciliation boundary; stale-after-publish races are marked in `residual_race`.
- Increment `policy_version` for a deliberate re-review under changed policy.
