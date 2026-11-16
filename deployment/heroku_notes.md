# Deploying the MCP server to Heroku

Status: ready to deploy, **not deployed**. Deploying needs Brian's approval: it adds a paid
Basic web dyno (~$7/month) to the shared app `bu-research`.

## What runs where

- **Heroku app `bu-research`**: one web dyno runs the MCP server (`python -m mcp_server.server`).
  The Postgres + pgvector database is already attached, so `DATABASE_URL` is set automatically.
- **Image**: built by Heroku from `Dockerfile` (selected by `heroku.yml`). It holds only
  `mcp_server/`, `embed/`, `database/` and the MiniLM ONNX model; `.dockerignore` keeps
  `data/` and `.env` out. Packages: `requirements-server.txt` (no PyTorch).
- **Embedding**: `EMBED_BACKEND=onnx` (set in the Dockerfile). Same all-MiniLM-L6-v2 weights as
  the pipeline; `RUN_EMBED_PARITY=1 python3 -m pytest tests/test_embed_model.py` proves they match.
- **No login**: anyone with the URL can call the tools (client decision, Nov 10).

Measured locally in a server-only environment (Nov 16): ~215 MB memory, ready in ~2 s,
~0.35 s per question after the first call.

## Configuration

| Variable | Value | Set by |
|---|---|---|
| `DATABASE_URL` | Heroku Postgres URL | Heroku (attached add-on) |
| `PORT` | dyno port | Heroku |
| `MCP_ALLOWED_HOSTS` | `bu-research-7dc3f331235a.herokuapp.com` | us, once |
| `MCP_HOST`, `EMBED_BACKEND` | `0.0.0.0`, `onnx` | Dockerfile |
| `MCP_ALLOWED_VISIBILITY` | optional; default `public,internal` | us, only to narrow |

`MCP_ALLOWED_HOSTS` must list the public hostname, or every request is rejected with HTTP 421
(DNS-rebinding protection).

## Deploy (after approval)

From the repository root, on the branch to deploy:

```
heroku stack:set container -a bu-research
heroku config:set MCP_ALLOWED_HOSTS=bu-research-7dc3f331235a.herokuapp.com -a bu-research
heroku git:remote -a bu-research          # adds the "heroku" git remote
git push heroku HEAD:main                 # Heroku builds the Dockerfile and releases it
heroku ps:scale web=1:basic -a bu-research
heroku logs --tail -a bu-research         # watch startup
```

## Check it works

```
npx @modelcontextprotocol/inspector
```
Transport "Streamable HTTP", URL `https://bu-research-7dc3f331235a.herokuapp.com/mcp`.
List tools (expect 9), then call `get_sales_methodology` with a question.

## Turn off or roll back

```
heroku ps:scale web=0 -a bu-research      # stop the server (stops dyno billing)
heroku releases:rollback -a bu-research   # return to the previous release
```
