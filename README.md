# Turing Research Agent

A **multi-agent research assistant** built on **LangGraph**, the **DeepAgents** harness, a **provider-switchable LLM layer** (Anthropic Claude **or** Groq Llama), **FastAPI** with SSE streaming, persistent **Supabase Postgres** checkpointing, and a **React + Vite + TS + Tailwind** frontend.

Four specialized agents collaborate to research companies, validate findings, and synthesize answers — with a human-in-the-loop interrupt when the query is unclear, durable multi-turn memory across server restarts, and a Validator → Research feedback loop capped at 3 attempts.

> Interview deliverable for the LangGraph multi-agent coding exercise. See [`Beyond Expected Deliverable`](#beyond-expected-deliverable) for choices that go past the spec.

---

## Architecture

```
                       ┌─────────────────┐
              ┌──────► │     Clarity     │ ◄─── (re-evaluates after resume)
              │        │  fast LLM, JSON │
              │        └─────────────────┘
              │                 │
              │   needs_         │  clear
              │   clarification ▼
       ┌──────┴──────┐   ┌─────────────────┐
       │ Clarification│   │    Research    │
       │  (interrupt) │   │ DeepAgents (or │
       └─────────────┘    │ direct fallback)│
            ▲             │  tools: mock,  │
            │             │  tavily, notes │
       human reply via    └─────────────────┘
       Command(resume=…)          │
                       ┌──────────┴──────────┐
                       │ conf<6        conf≥6│
                       ▼                     ▼
                ┌──────────────┐              │
                │  Validator   │              │
                │  fast LLM,   │              │
                │  + regex     │              │
                │  contradiction│              │
                │  guard       │              │
                └──────────────┘              │
                  │       │                   │
        insufficient    sufficient            │
        attempts<3        │                   │
                  │       └──────────────────►│
                  └── informed loop ─────────►│
                  (validator feedback drives  │
                   next Tavily query)         ▼
                                   ┌─────────────────┐
                                   │    Synthesis    │
                                   │  primary LLM,   │
                                   │  reads raw_notes│
                                   │  Markdown out   │
                                   └─────────────────┘
```

The compiled graph is wrapped in a LangGraph checkpointer keyed on `thread_id`. The checkpointer is selected at startup:

- **No `DATABASE_URL`** → `MemorySaver` (zero-config, lost on restart)
- **With `DATABASE_URL`** → `AsyncPostgresSaver` (Supabase / Neon / any Postgres) — threads survive restarts, can be shared across workers

**Key design decisions**

| Decision | Why |
|---|---|
| **Selective DeepAgents** — only the Research agent uses the harness | Research is genuinely open-ended (mock lookup? Tavily? scratch notes?). Wrapping classifier-style agents (Clarity, Validator, Synthesis) in deep agents is overkill. Engineering judgment, not framework name-dropping. |
| **Provider-switchable LLM** — `LLM_PROVIDER=groq \| anthropic` | One env var flips the entire stack. Local dev on free Groq; production on Claude Sonnet 4.5 for quality. Agent code is provider-agnostic via `agents/base.py`. |
| **Async checkpointer** — `AsyncPostgresSaver` with `AsyncConnectionPool` | `graph.astream()` needs async checkpoint methods. Sync `PostgresSaver` raises `NotImplementedError` for `aget_tuple`. We open the pool once at FastAPI startup. |
| **Informed validator loop** — feedback string drives next Tavily query | When the validator marks findings insufficient, its feedback (`"no information on CEO; search 'Apple Tim Cook tenure'"`) is fed verbatim as the next Tavily search query. The loop converges instead of cycling. |
| **Validator contradiction guard** — regex-based `_resolve_contradictions` | Small models occasionally return `sufficient` with feedback that describes a gap. We catch this with a `_NEGATION_PHRASES` regex (e.g. "no information", "missing", "could not find") and flip to `insufficient` automatically. |
| **Anchored confidence scoring** | LLMs drift toward `7-8` for any plausible output. The confidence prompt has explicit anchors (`≤3 if specific fact missing`) and uses the fast model to save tokens. |
| **Two-model strategy** | Fast model (Haiku 4.5 / Llama 3.1 8b) for Clarity, Validator, and confidence scoring. Primary model (Sonnet 4.5 / Llama 3.3 70b) for Research planning + Synthesis. |

---

## Agents in detail

Four specialized agents. Each is a class with a single `__call__(state) -> dict` entry point. **Agents never call each other directly** — the graph orchestrates the handoff and they communicate purely through `ResearchState` mutations. This keeps testing simple (stub one, observe the others) and makes the dataflow auditable.

### 🧠 Clarity Agent — disambiguates the user's request

**Job**: decide whether the query specifies a concrete company. If yes, route to Research. If no, route to the interrupt node so the user can clarify which company they mean.

**Inputs read from state**: `user_query`, `messages` (full conversation history — so follow-ups like "What about their CEO?" resolve correctly without a fresh clarification).

**Outputs written to state**: `clarity_status` (`"clear"` or `"needs_clarification"`), `company_name` (canonical name when clear), `clarification_question` (the prompt shown to the user when not).

**Implementation** — `agents/clarity.py`: fast model + `with_structured_output(ClarityDecision)` for deterministic JSON. The system prompt explicitly allows pulling the company name from prior turns, which is how the multi-turn memory demo short-circuits Clarity straight to the clear path.

**Error handling**: any LLM exception returns `needs_clarification` with a friendly fallback message ("Could you tell me which company you'd like me to research?") — the graph never crashes on Clarity failures.

**Routes to**: `clarification` node (interrupt) if `needs_clarification`, else `research`.

### 🔍 Research Agent — gathers facts about the company

**Job**: produce structured findings about the company (recent news, stock info, key developments) plus a self-rated confidence score (0–10) so the router knows whether to invoke the Validator.

**Inputs read from state**: `company_name`, `user_query`, `validation_feedback` (when looping back — drives the next Tavily query), `attempts`.

**Outputs written to state**: `research_findings` (dict with `company`, `recent_news`, `stock_info`, `key_developments`, `source`, `raw_notes`), `confidence_score`, increments `attempts`, appends an AIMessage to `messages`.

**Tool selection — cascading fallback chain** (see `_run_deep_agent_or_fallback`):

1. **DeepAgents harness** — when `ENABLE_DEEPAGENT=true`, the agent autonomously picks tools, plans with `write_todos`, iterates. Off by default (token-heavy).
2. **Informed Tavily search** — when `validation_feedback` is present, runs Tavily with `"{company} {feedback}"` as the query, then augments the mock baseline. This is the *informed loop*.
3. **Direct mock lookup** — first-attempt path when the company is in the curated dataset.
4. **Generic Tavily search** — fallback when the company isn't in the mock and no validator feedback exists.
5. **Stub** — last resort when no source returns results; sets low confidence so the validator fires.

**Confidence scoring**: a separate fast-LLM call with an anchored prompt (see `_CONFIDENCE_PROMPT` — explicit floors like `≤3 if specific fact missing`, `8-9 only if comprehensive`). The scoring uses the *fast* model so it doesn't burn the primary model's token budget.

**Routes to**: `validator` if `confidence_score < 6`, else `synthesis`.

### 🕵️ Validator Agent — quality gate for findings

**Job**: judge whether the research findings actually answer the user's *specific* question. When insufficient, write an **actionable** feedback string (`"no information on current CEO; search 'Apple Tim Cook tenure'"`) — the next Research pass uses that string verbatim as its Tavily query. The loop is informed, not blind.

**Inputs read from state**: `user_query`, `research_findings`, `confidence_score` (as a prior), `attempts`.

**Outputs written to state**: `validation_result` (`"sufficient"` or `"insufficient"`), `validation_feedback`.

**Reliability features baked in**:

- **Few-shot prompt** — 3 worked examples bias small models toward consistent verdicts (see `_SYSTEM_PROMPT` in `validator.py`).
- **Confidence-anchored** — receives Research's confidence score so it doesn't independently re-judge the same thing from scratch.
- **Contradiction guard** (`_resolve_contradictions`) — small models occasionally return `"sufficient"` paired with feedback that documents a gap. We catch this with a `_NEGATION_PHRASES` regex (`"no information"`, `"missing"`, `"could not find"`, etc.) and **automatically flip** to `insufficient`. A `_POSITIVE_HEDGE` regex prevents false positives like `"no further info needed"`.
- **Safe default on error** — any LLM exception returns `"sufficient"` so the graph doesn't loop infinitely. The 3-attempt cap is the backstop.

**Routes to**: `research` if `insufficient` AND `attempts < 3`, else `synthesis` (cap-hit case is acknowledged in Synthesis's output).

### ✍️ Synthesis Agent — writes the user-facing answer

**Job**: turn raw findings into a polished Markdown answer that **directly addresses** the user's specific question, citing sources inline.

**Inputs read from state**: `user_query`, `research_findings` (both structured fields **and** `raw_notes` — critical because the informed-loop Tavily data lives in `raw_notes`, not the structured fields), `messages` (multi-turn context), `attempts`, `validation_result` (to detect cap-hit cases).

**Outputs written to state**: `final_answer` (Markdown string), appends an `AIMessage(name="synthesis_agent")` to `messages`.

**Prompt discipline** (from `_SYSTEM_PROMPT` in `synthesis.py`):

- Lead with the direct answer in 1-2 sentences. No "Here is what I know about X" preambles.
- 2-4 supporting bullets, each citing the source inline (`"per curated data"` / `"per live web search"`).
- **Never invent specifics** (names, dates, numbers) not in the inputs. If the user asked "who is the CEO" and there's no CEO info, say "I don't have current leadership data" — don't guess.
- Acknowledge cap-hit cases explicitly: *"Some details may be incomplete — here's what's available:"*
- Reference prior turns naturally on follow-ups.

**Emergency fallback** (`_emergency_fallback`): when the LLM itself fails (rate limit, network error, parse exception), formats the raw findings as a clean Markdown answer with citations + a banner explaining what happened. The user always sees research data, never a stack trace.

**Routes to**: `END`.

---

## Tools available to agents

The "tools" here are the LangChain `@tool`-decorated functions exposed to the Research Agent. The other three agents are tool-less — they're pure structured-output LLM calls.

| Tool | Defined in | Used by | What it does |
|---|---|---|---|
| `lookup_mock_company(company: str)` | `tools/research_tool.py` | Research | Case-insensitive + alias-aware lookup against the curated 6-company dataset (Apple, Tesla, NVIDIA, Microsoft, Google, Amazon — plus tickers like AAPL, TSLA, MSFT). Returns `{found, company, recent_news, stock_info, key_developments, source: "mock"}`. Deterministic, instant, zero LLM tokens. |
| `tavily_search(query: str)` | `tools/research_tool.py` | Research | Live web search via Tavily. Active only when `TAVILY_API_KEY` is set. Returns top-5 results plus Tavily's own answer summary. The informed-loop path constructs the query from validator feedback (e.g. `"Apple current CEO Tim Cook tenure"`). Returns `{found: false, source: "stub"}` when Tavily key is absent — the agent gracefully degrades. |
| `write_todos` (built-in) | `deepagents` package | Research (only when `ENABLE_DEEPAGENT=true`) | DeepAgents' planning tool. Lets the Research agent write a checklist of sub-tasks and tick them off as it iterates over multiple tools. |
| Virtual filesystem — `read_file`, `write_file`, `ls`, `edit_file` (built-in) | `deepagents` package | Research (only when `ENABLE_DEEPAGENT=true`) | Scratch-pad workspace for the DeepAgent during multi-step research. Unused in the lightweight fallback path. |

**Tool selection is deterministic in the fallback path** — the code (in `research.py:_run_deep_agent_or_fallback`) walks the cascade `mock → informed-tavily → generic-tavily → stub`. **Tool selection is LLM-driven in the DeepAgents path** — the agent reads its system instructions (`_RESEARCH_INSTRUCTIONS`) and picks tools itself, including chaining them.

---

## Quickstart

You need **one** LLM key — either Groq (free) or Anthropic (paid, higher quality). Recommended: Anthropic for the demo, Groq for free testing.

### Option A — Local Python + Node

```bash
# 1. Install
make install                     # backend venv + frontend npm install

# 2. Configure
cp backend/.env.example backend/.env
# Edit backend/.env, set EITHER:
#   LLM_PROVIDER=anthropic + ANTHROPIC_API_KEY=sk-ant-...
# OR:
#   LLM_PROVIDER=groq + GROQ_API_KEY=gsk-...
# Optional:
#   TAVILY_API_KEY=tvly-...      (live web search fallback)
#   DATABASE_URL=postgresql://... (persistent threads)

# 3. Run (two terminals)
make dev-backend                 # uvicorn on :8765
make dev-frontend                # vite on :5173
```

Open <http://localhost:5173>.

### Option B — Docker Compose

```bash
cp backend/.env.example backend/.env
# Edit backend/.env with your LLM key

docker compose up --build
```

### Option C — CLI demo (no frontend)

```bash
cd backend
.venv/bin/python -m examples.demo_conversation
```

Both example turns from the spec — vague query → interrupt → clarification → answer; follow-up → memory used.

### Why port 8765 (not 8000)?

The macOS ChatGPT desktop app's "Work with Apps" feature aggressively probes localhost:8000 and can intercept browser requests. We moved the backend off 8000 to dodge that conflict. If you want the standard port, change `BACKEND_PORT` in `.env` and `VITE_API_BASE_URL` in `frontend/.env.local` to match.

---

## Try these in the UI

Two sets of suggested-query chips are pinned under the chat — each exercises a different graph path:

### ↻ Validator loop · stable-fact queries

These ask for facts the mock dataset doesn't have, so Research returns low confidence → Validator fires → loops back with Tavily.

| Chip | Demonstrates |
|---|---|
| Apple HQ location | Validator loop · Tavily augmentation |
| NVIDIA founded year | Validator loop · stable historical answer |
| Microsoft + LinkedIn | Validator loop · multi-fact answer (date + amount) |
| Google's parent | Validator loop · entity disambiguation |
| Amazon's founder | Validator loop · biographical |
| Tesla first car | Validator loop · product history |

### ❓ Clarify / interrupt · vague queries

These have no obvious single company — Clarity flags them, the graph interrupts, you reply with a specific company name, the graph resumes.

| Chip | Demonstrates |
|---|---|
| That EV company | Interrupt + resume (could be Tesla, BYD, Rivian, Lucid) |
| The big chip maker | Interrupt + resume (NVIDIA, AMD, Intel, TSMC) |
| That cloud giant | Interrupt + resume (AWS, Azure, GCP) |

### Multi-turn memory demo

After the first turn completes, send a follow-up that omits the company name — *"What about their stock?"* / *"Tell me more"*. The Clarity Agent reads the conversation history, infers the company, and skips the interrupt.

### Persistence demo (requires `DATABASE_URL`)

1. Send a query → wait for answer
2. `pkill uvicorn` → restart the backend
3. Refresh the browser → conversation rehydrates from Supabase

---

## Frontend — visible internals

Every important piece of internal state is surfaced in the UI so reviewers can narrate the system from the screen:

| Surface | What it shows |
|---|---|
| **Agent Activity timeline** (collapsible) | Live pills per node invocation. Each pill carries badges: confidence (`c=8`), attempt counter (`#1`), validation tick (`✓` / `↻`), elapsed ms |
| **Routing decision labels** under each pill | Names the backend routing function + verdict, e.g. `route_after_validator → insufficient · attempt 1/3` |
| **Validator feedback inline note** | When the loop fires, renders the validator's actual feedback string above the chat — proves the loop is *informed*, not blind |
| **Thinking bubble** | Live "typing indicator" with the current node label (🔍 *Researching Tesla · attempt 2*) — bouncing dots, ARIA-busy |
| **Graph topology SVG** (left sidebar) | Static 4-node diagram with the active node pulsing |
| **Dev Inspector** (left sidebar, tabbed) | `State` (full ResearchState snapshot) · `Messages` (LangChain message history) · `Events` (raw SSE event log with timestamps + colors) |
| **Clarification banner** | When `interrupt()` fires, an amber banner appears with the question + inline text input that hits `/chat/resume` |
| **Conversation export** | One button → downloads the entire turn history as Markdown |
| **Dark mode** | `prefers-color-scheme` detection + localStorage override |

---

## Project layout

```
turing_research_agent/
├── backend/                          # FastAPI + LangGraph
│   ├── app/
│   │   ├── graph/
│   │   │   ├── state.py              # ResearchState TypedDict + add_messages reducer
│   │   │   ├── routing.py            # 3 conditional routing functions (pure, fully tested)
│   │   │   ├── builder.py            # StateGraph composition + interrupt node
│   │   │   └── checkpointer.py       # MemorySaver / AsyncPostgresSaver factory
│   │   ├── agents/
│   │   │   ├── base.py               # Provider-aware LLM factories (Groq / Anthropic)
│   │   │   ├── clarity.py            # Structured-output classifier
│   │   │   ├── research.py           # DeepAgents harness + fallback chain
│   │   │   ├── validator.py          # Few-shot prompt + contradiction guard
│   │   │   └── synthesis.py          # Reads raw_notes + emergency Markdown fallback
│   │   ├── tools/research_tool.py    # lookup_mock_company + tavily_search
│   │   ├── data/mock_companies.py    # 6-company curated dataset
│   │   ├── api/
│   │   │   ├── routes.py             # SSE endpoints
│   │   │   └── schemas.py            # Pydantic request/response/event models
│   │   ├── services/chat_service.py  # Wires graph.astream → SSE events
│   │   ├── config.py                 # pydantic-settings
│   │   └── main.py                   # FastAPI app + startup/shutdown lifecycle
│   ├── tests/                        # 42 passing
│   ├── examples/demo_conversation.py # CLI demo
│   ├── Dockerfile + railway.toml     # Railway IaC
│   └── requirements.txt
├── frontend/                          # React + Vite + TS + Tailwind
│   ├── src/
│   │   ├── api/client.ts             # SSE wrapper (@microsoft/fetch-event-source)
│   │   ├── store/chat.ts             # Zustand: thread, trace, events, theme, collapse
│   │   ├── components/
│   │   │   ├── AgentTimeline.tsx     # Pills with routing-reason labels
│   │   │   ├── ClarificationBanner.tsx
│   │   │   ├── ComposerInput.tsx
│   │   │   ├── DevInspector.tsx      # State/Messages/Events tabs
│   │   │   ├── GraphTopology.tsx     # SVG topology diagram
│   │   │   ├── Header.tsx
│   │   │   ├── MessageBubble.tsx
│   │   │   ├── SuggestedQueries.tsx  # Two-section: Validator + Clarify chips
│   │   │   ├── ThinkingBubble.tsx    # Live typing indicator
│   │   │   └── ValidatorFeedback.tsx # Inline note on loopback
│   │   ├── App.tsx
│   │   └── types.ts                  # Mirrors backend Pydantic schemas
│   ├── Dockerfile + vercel.json      # Vercel + Docker deploys
│   └── package.json
├── docker-compose.yml                # One-command local stack
├── Makefile                          # make install / dev / test / build / demo
├── .github/workflows/ci.yml          # ruff + pytest + tsc + vite build
└── README.md
```

---

## API

| Method | Path | Body | Response |
|---|---|---|---|
| `GET` | `/health` | — | `{"status":"ok"}` |
| `POST` | `/chat` | `{thread_id, message}` | **SSE stream** of node events |
| `POST` | `/chat/resume` | `{thread_id, clarification}` | **SSE stream** (resumes interrupted thread) |
| `GET` | `/threads/{thread_id}` | — | Checkpointed history + interrupt status |

### SSE event types

```jsonc
{ "type": "node_start",    "node": "clarity" }
{ "type": "node_end",      "node": "clarity",
  "state_delta": { "clarity_status": "clear", "company_name": "Tesla" } }
{ "type": "interrupt",     "question": "Which company are you asking about?" }
{ "type": "final_message", "content": "## Tesla\n- …" }
{ "type": "error",         "message": "LLM service unavailable" }
```

`node_start` fires for **every** invocation including loopback iterations — so a Research → Validator → Research → Validator → Synthesis pass produces five `node_start` events.

### Manual probe

```bash
curl -N -H "Content-Type: application/json" \
  -d '{"thread_id":"demo-1","message":"Where is Apple HQ?"}' \
  http://localhost:8765/chat
```

---

## Tests

```bash
make test                            # backend pytest + frontend typecheck
```

**42 tests passing in ~0.2s** (deterministic, no network):

| File | Cases | What it covers |
|---|---|---|
| `test_routing.py` | 17 | All branches of all 3 conditional routing functions, parametrized |
| `test_state.py` | 2 | State seeding contract |
| `test_mock_data.py` | 14 | Case-insensitive lookup + alias resolution |
| `test_agents.py` | 5 | Agent contracts with mocked LLM, including LLM-error fallbacks |
| `test_graph_e2e.py` | 4 | Real LangGraph + stub agents: happy path, validator loopback, attempt cap, interrupt/resume |

CI re-runs the same on every push (`.github/workflows/ci.yml`).

---

## Environment variables reference

### Backend (`backend/.env`)

```env
# --- LLM provider ---
LLM_PROVIDER=anthropic                   # "anthropic" or "groq"

# Anthropic (if LLM_PROVIDER=anthropic)
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL_PRIMARY=claude-sonnet-4-5-20250929
ANTHROPIC_MODEL_FAST=claude-haiku-4-5-20251001

# Groq (if LLM_PROVIDER=groq)
GROQ_API_KEY=gsk-...
GROQ_MODEL_PRIMARY=llama-3.3-70b-versatile
GROQ_MODEL_FAST=llama-3.1-8b-instant

# --- Optional integrations ---
TAVILY_API_KEY=tvly-...                  # live web search; empty → mock-only
DATABASE_URL=postgresql://...            # Supabase / any Postgres; empty → MemorySaver
ENABLE_DEEPAGENT=false                   # set true to enable DeepAgents harness (token-heavy)

# --- Server ---
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8765
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

### Frontend (`frontend/.env.local`)

```env
VITE_API_BASE_URL=http://127.0.0.1:8765  # change to Railway URL in production
```

---

## Deployment

**Recommended: Railway (backend) + Vercel (frontend).** Backend needs long-lived SSE connections (Railway containers stay warm); frontend is static React (Vercel's edge CDN excels here).

### Step 0 — Push to GitHub

```bash
git init
git add -A
git status      # ← VERIFY no backend/.env is staged
git commit -m "initial commit"
git remote add origin https://github.com/<YOU>/turing-research-agent.git
git push -u origin main
```

### Step 1 — Backend → Railway (~3 min)

1. <https://railway.app> → New Project → Deploy from GitHub repo → set **Root Directory** = `backend`. Railway auto-detects `Dockerfile` + `railway.toml`.
2. Variables tab — add (use rotated keys, never the ones from shared chat transcripts):

   | Key | Value |
   |---|---|
   | `LLM_PROVIDER` | `anthropic` |
   | `ANTHROPIC_API_KEY` | `sk-ant-...` |
   | `TAVILY_API_KEY` | `tvly-...` (optional) |
   | `DATABASE_URL` | `postgresql://postgres.<ref>:<pw>@aws-X-region.pooler.supabase.com:5432/postgres` |
   | `CORS_ORIGINS` | `https://<your-app>.vercel.app,http://localhost:5173` (update after step 2) |

3. Deploy. Watch the log; success line:
   ```
   Backend started | provider=anthropic | tavily=on | persistence=postgres | models=claude-haiku-4-5-20251001/claude-sonnet-4-5-20250929
   ```
4. Copy the Railway URL (`https://<service>.up.railway.app`).

### Step 2 — Frontend → Vercel (~2 min)

1. <https://vercel.com/new> → Import your GitHub repo
2. Root Directory: `frontend`
3. Framework Preset: Vite (auto-detected)
4. Environment variable: `VITE_API_BASE_URL=https://<your-railway-domain>.up.railway.app`
5. Deploy.

### Step 3 — Update Railway CORS

Back in Railway → Variables → set `CORS_ORIGINS=https://<your-app>.vercel.app,http://localhost:5173`. Railway auto-redeploys.

### Why not Vercel for the backend?

Vercel Serverless Functions cap at 10–30s — kills SSE streams. Vercel Edge supports streaming but is awkward for FastAPI. Railway (or Fly.io) are the right shape.

### Supabase setup (for `DATABASE_URL`)

1. <https://app.supabase.com> → New Project. Region close to Railway.
2. Set a strong DB password — Supabase shows it once. Save it. **Use only alphanumeric** to avoid URL-encoding issues with `@`, `:`, `}`, `%`, etc.
3. Click **Connect** at the top of the dashboard → **Session Pooler** tab (NOT Transaction Pooler — that breaks LangGraph's prepared statements) → copy the URI.
4. Replace `[YOUR-PASSWORD]` with your DB password.
5. Set `DATABASE_URL=postgresql://postgres.<ref>:<pw>@aws-X-region.pooler.supabase.com:5432/postgres` in Railway.
6. On first boot, the checkpointer's `setup()` creates `checkpoints`, `checkpoint_blobs`, `checkpoint_writes` tables in the `public` schema (idempotent; subsequent boots catch the `UniqueViolation` and continue).

### Production hardening (called out, not all in v1)

- ✅ Persistent threads via Supabase Postgres
- ✅ Provider switch (Groq ↔ Anthropic) with one env var
- ✅ Async checkpointer for proper SSE support
- ✅ Emergency fallback when LLM rate-limits or errors
- ⏳ Add `slowapi` rate limiting on `/chat` and `/chat/resume`
- ⏳ Front the API with Cloudflare for caching + abuse blocking
- ⏳ Add Sentry on both sides for error visibility
- ⏳ Restrict CORS to exactly the prod domain; remove `http://localhost:5173`
- ⏳ Scale beyond 1 worker now that the checkpoint is the shared source of truth

---

## Assumptions made

1. **Confidence score is LLM-assigned** with a strict anchored prompt — but no calibration dataset. Threshold `≥6 = sufficient` is spec-driven.
2. **Tavily is optional.** Without `TAVILY_API_KEY` the Research agent falls back to mock-only.
3. **Max 3 research attempts** is enforced in `route_after_validator` (code, not LLM).
4. **`MemorySaver` is the default**; Postgres is opt-in via `DATABASE_URL`. Production demos use Postgres for durability.
5. **Thread IDs are client-generated UUIDs**, no auth/user model.
6. **DeepAgents is off by default** (`ENABLE_DEEPAGENT=false`) — its 5–6 LLM calls per Research turn blow through the Groq free tier (12k TPM). The Research agent has a direct mock + Tavily fallback that uses 1–2 calls per turn. Set `ENABLE_DEEPAGENT=true` to opt in if you have budget headroom.
7. **Two-model strategy**: fast model for classifiers, primary model for generation.
8. **Error handling on LLM boundaries** falls back gracefully — Clarity → asks user to clarify; Validator → defaults to `sufficient` (avoids infinite loops); Research → low-confidence stub; Synthesis → emergency Markdown fallback that still cites the research data.
9. **macOS port collision**: the ChatGPT desktop app probes `localhost:8000`, so we default to `:8765`.

---

## Beyond Expected Deliverable

Items that go past the spec:

1. **Selective DeepAgents harness** — Research uses `deepagents.create_deep_agent`; classifiers don't. Toggleable via `ENABLE_DEEPAGENT`.
2. **Provider-switchable LLM layer** — `LLM_PROVIDER=anthropic|groq`. Same agent code, different provider. Demonstrated by `agents/base.py:_build_chat_model`.
3. **AsyncPostgresSaver + Supabase** — durable threads survive restarts; same code works with any Postgres.
4. **Idempotent Postgres setup** — `_resolve_contradictions`-style guard around `setup()` so subsequent boots don't fail on `UniqueViolation`.
5. **Live SSE agent timeline** with pulsing active-node animation, attempt counter, validation tick, elapsed ms per step.
6. **Routing-decision labels** under each pill — names the routing function + verdict (e.g. `route_after_validator → insufficient · attempt 1/3`).
7. **Validator feedback inline note** — shows the loopback driver right above the chat.
8. **Validator contradiction guard** — regex catches `sufficient + negation in feedback` and flips automatically.
9. **Validator few-shot prompt** — 3 worked examples bias small models toward consistent verdicts.
10. **Informed loop** — validator's feedback string is fed as the next Tavily query, not just appended to context.
11. **Confidence-anchored prompt** — explicit floors (`≤3 if specific fact missing`) prevent score inflation.
12. **Synthesis reads `raw_notes`** — Tavily search results in raw_notes flow into the final answer instead of being lost behind structured fields.
13. **Synthesis emergency fallback** — rate-limit / LLM-error path produces a clean Markdown answer with citations rather than a raw exception.
14. **Thinking bubble** — live "typing indicator" in the chat with node-specific labels.
15. **Two-section suggested-query chips** — Validator-loop chips + Clarify-interrupt chips, color-coded.
16. **Dev Inspector** — tabbed State / Messages / Events panel showing the raw SSE wire protocol.
17. **Graph topology SVG** — visual reinforcement of the routing.
18. **Collapsible Agent Activity** — keep the timeline visible during demos, hide it for max chat real-estate; choice persisted in `localStorage`.
19. **Conversation export to Markdown** — one-button download.
20. **Dark mode** with system-preference detection + override.
21. **Persistent thread restore** — `GET /threads/{id}` rehydrates after refresh AND after backend restart (with Postgres).
22. **End-to-end type safety** — Pydantic backend + mirrored TS types.
23. **Tested routing matrix** — all 17 branches parametrized + 4 e2e graph scenarios.
24. **One-command Docker Compose** for reviewers without Python/Node.
25. **Railway IaC + Vercel config** committed.
26. **GitHub Actions CI** — ruff + pytest + tsc + vite build.
27. **Error matrix** — 10 distinct failure modes have explicit code paths (Groq 5xx, Tavily timeout, structured-output parse failure, unknown thread, etc.).

---

## Tech stack rationale

| Layer | Choice | Why |
|---|---|---|
| Graph | `langgraph` (StateGraph + AsyncPostgresSaver) | Explicit routing, interrupt, checkpointing — the spec's hard requirements |
| Agent harness | `deepagents` (Research only, opt-in) | Open-ended reasoning needs planning + multi-tool; classifiers don't |
| LLM (primary) | `langchain-anthropic` → Claude Sonnet 4.5 | Best generation quality; large daily quota |
| LLM (fast) | Claude Haiku 4.5 | Cheap classifier-tier calls |
| LLM (alt) | `langchain-groq` → Llama 3.3 70b / 3.1 8b | Free tier for local dev / CI |
| Persistence | Supabase Postgres + `langgraph-checkpoint-postgres` | Managed, free tier; standard psycopg connection string |
| Live search | Tavily | Optional; falls back to mock cleanly |
| Backend | FastAPI + SSE (`sse-starlette`) | Long-lived streams; clean async |
| Frontend | React + Vite + TS + Tailwind | Modern, lightweight, fast HMR |
| Frontend state | Zustand | Tiny, no Redux ceremony |
| SSE client | `@microsoft/fetch-event-source` | Handles POST + SSE (native EventSource is GET-only) |
| Hosting BE | Railway | No cold starts; $2/mo on free credit |
| Hosting FE | Vercel | Edge CDN; PR previews; Vite-native |

---

## License

Interview submission. No license; please don't fork-and-publish.

---

## Acknowledgements

- LangChain team for [LangGraph](https://github.com/langchain-ai/langgraph) and [DeepAgents](https://github.com/langchain-ai/deepagents)
- Anthropic for the Claude API
- Groq for fast inference free tier
- Supabase for managed Postgres
- Tavily for the search API
