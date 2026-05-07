# Anuma 2API Gateway

A self-hosted gateway that provides OpenAI/Anthropic-compatible APIs backed by [Anuma AI](https://anuma.ai) accounts. Includes automated account registration via temporary email, account pool management, and a load-balanced API server with automatic failover.

> **Credits**: Temporary email service is powered by [小辣椒的临时邮箱](https://vip.215.im) (vip.215.im) — a fast, reliable temp mail API with generous free tier.

## Features

- **Batch Account Registration** — Automated signup using temporary email, Privy authentication, and embedded wallet creation. Web UI for monitoring progress.
- **OpenAI & Anthropic Compatible** — Works with Claude Code, Cherry Studio, ChatBox, and any client that speaks the OpenAI or Anthropic API protocol.
- **Smart Load Balancing** — Round-robin across available accounts. Automatically disables accounts that run out of credits or have expired tokens.
- **Token Auto-Refresh** — Proactively refreshes JWT identity tokens before expiry. Background daemon keeps the account pool healthy.
- **Streaming Support** — Full SSE streaming for both OpenAI and Anthropic response formats.
- **Tool Use** — Translates tool-call requests for Claude Code compatibility.
- **SOCKS5 Proxy** — Optional proxy support for environments that need it.

## Architecture

```
┌──────────────┐     ┌──────────────────┐     ┌─────────────┐
│  AI Client   │────▶│  api_server.py   │────▶│  Anuma API   │
│ (Claude Code,│     │  (FastAPI :7895)  │     │  portal.anuma│
│  Cherry St.) │     └────────┬─────────┘     └─────────────┘
└──────────────┘              │
                              │ reads
                              ▼
┌──────────────┐     ┌──────────────────┐
│  Web UI      │────▶│ privy_manager.py │
│  (Flask)     │     │  (Flask :7894)    │
└──────────────┘     └────────┬─────────┘
                              │
                              ▼
                     ┌──────────────────┐     ┌──────────────────┐
                     │  anuma_client.py │────▶│  小辣椒 临时邮箱    │
                     │  (SDK)           │     │  (vip.215.im)     │
                     └──────────────────┘     └──────────────────┘
```

## Project Structure

| File | Purpose |
|------|---------|
| `config.py` | Centralized configuration from environment variables |
| `anuma_client.py` | Low-level SDK: Privy auth, Anuma chat, temporary email client |
| `privy_manager.py` | Flask web UI + batch registration engine |
| `api_server.py` | FastAPI gateway with OpenAI/Anthropic compatible endpoints |
| `templates/index.html` | Web dashboard template |
| `docker-compose.yml` | Docker deployment orchestration |

## Quick Start

### 1. Prerequisites

- Python 3.10+
- A mail API key from [小辣椒临时邮箱](https://vip.215.im)
- Optional: SOCKS5 proxy if Anuma is blocked in your region

### 2. Configuration

```bash
cp .env.example .env
# Edit .env and fill in your MAIL_API_KEY
```

Required: `MAIL_API_KEY` — your temp mail API key from vip.215.im.
Optional: `SOCKS5_PROXY` — proxy string for API requests.

### 3. Install

```bash
pip install -r requirements.txt
```

### 4. Start the Registration Manager (Web UI)

```bash
python3 privy_manager.py
```

Open http://localhost:7894 — configure registration count, concurrency, and click "Start" to batch-register accounts.

### 5. Start the API Gateway

```bash
python3 api_server.py
```

The gateway runs on `http://localhost:7895/v1` by default (configurable via `API_PORT`).

### 6. Connect Your Client

**Claude Code:**
```bash
export ANTHROPIC_BASE_URL=http://localhost:7895/v1
export ANTHROPIC_API_KEY=sk-no-auth-needed
claude
```

**Cherry Studio:**
Add an OpenAI-compatible provider with:
- Base URL: `http://localhost:7895/v1`
- API Key: any value (not validated)

## API Endpoints

### `GET /v1/models`

Returns available model list.

### `POST /v1/chat/completions`

OpenAI-compatible chat completions. Supports streaming.

### `POST /v1/messages`

Anthropic-compatible messages endpoint. Supports streaming and tool use.

### Model Mapping

| Client model name | Anuma upstream |
|-------------------|----------------|
| `gpt-5.4` | `openai/gpt-5.4` |
| `gpt-4` | `openai/gpt-4` |
| `claude-opus` / `claude-3-7` | `anthropic/claude-opus-4-7` |
| `claude-sonnet` | `anthropic/claude-sonnet-4-6` |

## Docker Deployment

```bash
# Build and start
docker compose up -d

# View logs
docker compose logs -f api-server
```

Both services share a SQLite database mounted at `./data`. Create a `.env` file before starting.

## Environment Variables

A complete reference is in [`.env.example`](.env.example).

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MAIL_API_KEY` | **Yes** | — | Mail API key from vip.215.im |
| `MAIL_API_BASE_URL` | No | `https://maliapi.215.im/v1` | Custom mail API URL |
| `SOCKS5_PROXY` | No | — | SOCKS5 proxy for upstream requests |
| `DB_PATH` | No | `./privy_manager.db` | SQLite database path |
| `MANAGER_PORT` | No | `7894` | Web UI port |
| `API_PORT` | No | `7895` | API gateway port |
| `API_HOST` | No | `0.0.0.0` | API bind address |
| `DEFAULT_TOTAL` | No | `10` | Default registration batch size |
| `DEFAULT_CONCURRENCY` | No | `3` | Default concurrent threads |

## Notes

1. Recommended concurrency: 2-3. Higher values may trigger rate limits or IP blocks.
2. The gateway automatically disables accounts with zero credits or expired tokens.
3. Token refresh happens both proactively (before requests) and via a background daemon (every 10 minutes).
4. The `identity_token` is session-critical — the client handles complex token exchange logic internally.

## License

[MIT](LICENSE)