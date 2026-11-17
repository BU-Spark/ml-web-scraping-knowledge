# Deploying the MCP server to Heroku

Status: **deployed** Nov 16, 2026 with Brian's approval: one paid Basic web dyno (~$7/month) on
the shared app `bu-research`. Live at https://bu-research-7dc3f331235a.herokuapp.com/mcp.

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

## First deploy (done; one-time setup)

From the repository root, on the branch to deploy:

```
heroku stack:set container -a bu-research
heroku config:set MCP_ALLOWED_HOSTS=bu-research-7dc3f331235a.herokuapp.com -a bu-research
heroku git:remote -a bu-research          # adds the "heroku" git remote
git push heroku HEAD:main                 # Heroku builds the Dockerfile and releases it
heroku ps:scale web=1:basic -a bu-research
heroku logs --tail -a bu-research         # watch startup
```

## Updating the live server

| What changed | What to do |
|---|---|
| Code (`mcp_server/`, `embed/`, `database/`, Dockerfile, `requirements-server.txt`) | Commit, then `git push heroku HEAD:main`. Heroku rebuilds and restarts (1-2 min). |
| Data (new or re-extracted units) | Nothing. Run the uploader; the server reads the DB on every call. |
| Config vars | `heroku config:set ...` restarts the server by itself. |

- Heroku builds the last **commit**, not your working folder: commit first.
- `HEAD:main` sends the branch you are on, so check out the right branch first. Deploy from `dev`
  so that dev is what Brian is using.
- Pushing to GitHub (`origin`) does not deploy.
- Test a change locally first (run `python3 -m mcp_server.server` with `DATABASE_URL` set, then
  open http://localhost:8000/ and connect MCP Inspector to http://localhost:8000/mcp).
- What is live: `git log heroku/main -1 --oneline`; history: `heroku releases -a bu-research`.

## Check it works

Open https://bu-research-7dc3f331235a.herokuapp.com/ in a browser: it shows the status, the
number of units per category and the tool list (HTTP 503 if the database cannot be read). Then:

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
