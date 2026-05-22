# Turing Research Agent

Multi-agent research assistant: **LangGraph** + **DeepAgents** + **Claude / Groq** + **FastAPI (SSE)** + **Supabase Postgres** + **React/Vite/Tailwind**. Four agents collaborate to research a company, with a human-in-the-loop interrupt, a validator-driven feedback loop, and durable multi-turn memory.

🔗 **Demo**: [https://turing-research-agent-udnc.vercel.app](https://turing-research-agent-udnc.vercel.app) · **Source**: [https://github.com/anubhav-97/turing-research-agent](https://github.com/anubhav-97/turing-research-agent)

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

State flows through a LangGraph `StateGraph` keyed on `thread_id`. Each agent reads/writes specific `ResearchState` fields - they never call each other directly; the graph orchestrates.

---

## The 4 Agents

### 🧠 Clarity - *"is this query specific enough to research?"*

- **Input**: `user_query` + full `messages` history (so follow-ups resolve correctly)
- **Output**: `clarity_status` (`clear` | `needs_clarification`), `company_name`, `clarification_question`
- **Model**: fast LLM (Haiku 4.5 / Llama 8b) with `with_structured_output(ClarityDecision)` for deterministic JSON
- **Routes to**: interrupt node if unclear, else Research
- **File**: `backend/app/agents/clarity.py`

### 🔍 Research - *"go gather facts about this company"*

- **Input**: `company_name`, `user_query`, `validation_feedback` (when looping back), `attempts`
- **Output**: `research_findings` (recent_news, stock_info, key_developments, source, raw_notes), `confidence_score` (0-10)
- **Tools** (cascading fallback):
  1. **DeepAgents harness** (opt-in via `ENABLE_DEEPAGENT=true`) - agent picks tools autonomously
  2. **Informed Tavily search** - when validator gave feedback, query = `"{company} {feedback}"`
  3. **Mock lookup** - instant if company is in the curated dataset
  4. **Generic Tavily** - fallback for unknowns
  5. **Stub** - last resort; low confidence triggers validator
- **Confidence scoring**: separate fast-LLM call with anchored prompt (`≤3 if specific fact missing`)
- **Routes to**: Validator if `confidence < 6`, else Synthesis
- **File**: `backend/app/agents/research.py`

### 🕵️ Validator - *"do the findings actually answer the question?"*

- **Input**: `user_query`, `research_findings`, `confidence_score`, `attempts`
- **Output**: `validation_result` (`sufficient` | `insufficient`), `validation_feedback` (an *actionable* string fed verbatim to the next Tavily search)
- **Reliability features**:
  - **Few-shot prompt** - 3 worked examples for consistent verdicts
  - **Contradiction guard** - regex catches `sufficient + negation in feedback` and auto-flips to `insufficient`
  - **Confidence-anchored** - sees Research's score as prior context
  - **Safe default on error** - returns `sufficient` to prevent infinite loops; the 3-attempt cap is the backstop
- **Routes to**: Research if `insufficient` AND `attempts < 3`, else Synthesis
- **File**: `backend/app/agents/validator.py`

### ✍️ Synthesis - *"write the final user-facing answer"*

- **Input**: `user_query`, `research_findings` (uses `**raw_notes` field** where Tavily data lives), `messages` history, `attempts`
- **Output**: `final_answer` (Markdown), appends `AIMessage` to `messages`
- **Prompt discipline**: leads with direct answer, cites source per bullet, never invents specifics, acknowledges max-attempts caveat
- **Emergency fallback**: if LLM errors (rate limit, etc.), formats raw findings as clean Markdown - user always sees research data, never a stack trace
- **Routes to**: END
- **File**: `backend/app/agents/synthesis.py`

---

## Tools

Only the Research Agent has tools. The other three are pure structured-output LLM calls.


| Tool                           | What it does                                                                                       |
| ------------------------------ | -------------------------------------------------------------------------------------------------- |
| `lookup_mock_company(company)` | Case-insensitive + alias-aware lookup against the 6-company curated dataset. Instant, zero tokens. |
| `tavily_search(query)`         | Live web search via Tavily. Auto-disabled when `TAVILY_API_KEY` is absent.                         |
| `write_todos` *(DeepAgents)*   | Planning tool. Only when `ENABLE_DEEPAGENT=true`.                                                  |
| Virtual FS *(DeepAgents)*      | `read_file` / `write_file` scratch-pad. Only when `ENABLE_DEEPAGENT=true`.                         |


---

## File structure

```
turing-research-agent/
├── backend/                          # FastAPI + LangGraph
│   ├── app/
│   │   ├── agents/                   # The 4 agent classes
│   │   │   ├── base.py               # Provider-aware LLM factory (Claude / Groq)
│   │   │   ├── clarity.py            # 🧠 Disambiguation classifier
│   │   │   ├── research.py           # 🔍 DeepAgents + fallback cascade
│   │   │   ├── validator.py          # 🕵️ Quality gate + contradiction guard
│   │   │   └── synthesis.py          # ✍️ Markdown writer + emergency fallback
│   │   ├── graph/
│   │   │   ├── state.py              # ResearchState TypedDict + add_messages reducer
│   │   │   ├── routing.py            # 3 conditional routing functions
│   │   │   ├── builder.py            # StateGraph composition + interrupt node
│   │   │   └── checkpointer.py       # MemorySaver / AsyncPostgresSaver factory
│   │   ├── tools/research_tool.py    # lookup_mock_company + tavily_search
│   │   ├── data/mock_companies.py    # 6-company curated dataset
│   │   ├── api/
│   │   │   ├── routes.py             # /chat, /chat/resume, /threads/{id}, /health
│   │   │   └── schemas.py            # Pydantic request/response/SSE-event models
│   │   ├── services/chat_service.py  # graph.astream → SSE events
│   │   ├── config.py                 # pydantic-settings (LLM_PROVIDER toggle, etc.)
│   │   └── main.py                   # FastAPI app + startup/shutdown lifecycle
│   ├── tests/                        # 42 passing - routing, state, agents, e2e graph
│   ├── examples/demo_conversation.py # CLI demo of the 2-turn spec scenario
│   ├── Dockerfile + railway.toml     # Railway IaC
│   ├── requirements.txt
│   └── .env.example
├── frontend/                          # React + Vite + TS + Tailwind
│   ├── src/
│   │   ├── api/client.ts             # SSE wrapper (@microsoft/fetch-event-source)
│   │   ├── store/chat.ts             # Zustand: messages, trace, events, theme
│   │   ├── components/
│   │   │   ├── AgentTimeline.tsx     # Live pills with routing-reason labels
│   │   │   ├── ClarificationBanner.tsx
│   │   │   ├── ComposerInput.tsx
│   │   │   ├── DevInspector.tsx      # State / Messages / Events tabs
│   │   │   ├── GraphTopology.tsx     # SVG diagram
│   │   │   ├── Header.tsx
│   │   │   ├── MessageBubble.tsx
│   │   │   ├── SuggestedQueries.tsx  # Two-section chips (Validator + Clarify)
│   │   │   ├── ThinkingBubble.tsx    # Live typing indicator
│   │   │   └── ValidatorFeedback.tsx # Inline note on loopback
│   │   ├── App.tsx
│   │   └── types.ts                  # Mirrors backend Pydantic schemas
│   ├── Dockerfile + nginx.conf       # Container path (docker-compose only)
│   ├── vercel.json                   # Vercel config
│   └── package.json
├── docker-compose.yml                # One-command local stack
├── Makefile                          # make install / dev / test / build / demo
├── .github/workflows/ci.yml          # ruff + pytest + tsc + vite build
└── README.md
```

---

## Quickstart (local)

```bash
make install                              # backend venv + frontend npm
cp backend/.env.example backend/.env      # then add ANTHROPIC_API_KEY (or GROQ_API_KEY)
make dev-backend                          # uvicorn :8765
make dev-frontend                         # vite :5173
```

Open [http://localhost:5173](http://localhost:5173). Required: one LLM key (Anthropic or Groq). Optional: `TAVILY_API_KEY`, `DATABASE_URL` (Supabase Postgres for durable threads).

CLI demo (no frontend): `cd backend && .venv/bin/python -m examples.demo_conversation`

---

## Try in the demo


| Chip type                                                                       | Demonstrates                                                              |
| ------------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| **Validator-loop chips** (stable-fact queries - Apple HQ, NVIDIA founded, etc.) | Research → Validator → Research → Synthesis with informed Tavily loopback |
| **Clarify chips** (vague queries - *"that EV company"*)                         | Clarity interrupts → user clarifies → graph resumes                       |
| **Follow-up question** in same thread                                           | Clarity uses message history; skips re-clarification                      |
| **Refresh browser mid-conversation**                                            | Conversation rehydrates from Supabase (proves persistent checkpointing)   |


---

## Tests

```bash
make test                  # 42 tests, ~0.2s, deterministic
```

Coverage: all 17 routing branches · state schema · mock lookup · agent contracts (mocked LLM) · 4 e2e graph scenarios (happy path, loopback, attempt cap, interrupt/resume).

---

## Tech stack


| Layer         | Choice                                                               |
| ------------- | -------------------------------------------------------------------- |
| Graph         | LangGraph + `AsyncPostgresSaver`                                     |
| Agent harness | DeepAgents (Research only, opt-in)                                   |
| LLM           | Anthropic Claude Sonnet 4.5 + Haiku 4.5 (primary) / Groq Llama (alt) |
| Search        | Tavily (optional)                                                    |
| Backend       | FastAPI + SSE                                                        |
| Frontend      | React + Vite + TypeScript + Tailwind + Zustand                       |
| Persistence   | Supabase Postgres                                                    |
| Hosting       | Railway (backend) + Vercel (frontend)                                |


---

## Deployment

Backend → Railway (Settings → Source → Root Directory = `backend`; add env vars; uses `backend/Dockerfile` + `backend/railway.toml`).
Frontend → Vercel (Root Directory = `frontend`; set `VITE_API_BASE_URL=https://<railway-url>`).
Wire `CORS_ORIGINS` on Railway to include the Vercel URL.

Common gotchas: Root Directory on **service** (not project); `$PORT` needs `sh -c` wrapping; alphanumeric DB password (avoid URL-encoding); `VITE_API_BASE_URL` must include `https://`; Vite bakes env at build time (redeploy after changing).

---

## Beyond expected

Things that go past the spec, grouped by where the work shows up.

**Architecture**
- **Selective DeepAgents** - Research uses the harness for tool selection + planning; classifiers stay simple. Engineering judgment, not framework name-dropping.
- **Provider-switchable LLM** - `LLM_PROVIDER=anthropic|groq` flips the whole stack via one env var; agent code is provider-agnostic.
- **AsyncPostgresSaver + Supabase** - durable threads survive restarts; works with any Postgres URL.
- **Idempotent Postgres setup** - `DuplicateObject` / `UniqueViolation` guard so subsequent boots don't fail.

**Validator + routing**
- **Informed loop** - validator's feedback string becomes the literal next Tavily query, so retries converge instead of cycling.
- **Contradiction guard** - regex catches `sufficient + negation in feedback` and auto-flips to `insufficient`.
- **Few-shot prompt** - 3 worked examples bias small models toward consistent verdicts.
- **Confidence-anchored scoring** - explicit floors (`≤3 if specific fact missing`) prevent score inflation.

**Synthesis quality**
- **Reads `raw_notes`** - Tavily output flows into the final answer instead of being trapped behind structured fields.
- **Emergency Markdown fallback** - rate-limit / LLM-error path produces a clean answer with citations rather than a raw exception.

**Frontend**
- **Live SSE agent timeline** with pulsing active node, attempt counter, validation tick, elapsed ms per step.
- **Routing-decision labels** under each pill (e.g. `route_after_validator → insufficient · attempt 1/3`).
- **Validator feedback inline note** - shows the loopback driver above the chat.
- **Thinking bubble** - live typing indicator with the current node label.
- **Two-section suggested-query chips** - Validator-loop + Clarify-interrupt, color-coded.
- **Dev Inspector** - tabbed State / Messages / Events showing the raw SSE wire protocol.
- **Graph topology SVG**, **collapsible activity** (localStorage-persisted), **conversation export to Markdown**, **dark mode**.

**Reliability + ops**
- **Persistent thread restore** - `GET /threads/{id}` rehydrates the conversation after refresh AND after a backend restart.
- **End-to-end type safety** - Pydantic backend + mirrored TS types.
- **Tested routing matrix** - all 17 branches parametrized + 4 e2e graph scenarios (happy path, loopback, attempt cap, interrupt/resume).
- **Error matrix** - 10 distinct failure modes have explicit code paths (Groq 5xx, Tavily timeout, parse failure, unknown thread, etc.).
- **One-command Docker Compose** for reviewers without Python/Node.
- **Railway IaC + Vercel config** committed; **GitHub Actions CI** runs ruff + pytest + tsc + vite build on every push.

---

## Assumptions

- **Confidence threshold** - `≥6 = sufficient` per spec; LLM-assigned with an anchored prompt, no calibration dataset.
- **Max 3 research attempts** - hard-capped in `route_after_validator` (code, not LLM).
- **`MemorySaver` is default** - Postgres is opt-in via `DATABASE_URL`. Production demos use Postgres for durability.
- **Tavily is optional** - without `TAVILY_API_KEY` the Research agent falls back to mock-only.
- **DeepAgents off by default** (`ENABLE_DEEPAGENT=false`) - the harness's 5-6 LLM calls per Research turn blow through the Groq free tier (12k TPM). Set `true` if you have budget headroom.
- **Two-model strategy** - fast model for classifiers, primary model for generation.
- **Graceful LLM-boundary errors** - Clarity asks user to clarify; Validator defaults to `sufficient` (avoids infinite loops); Research returns low-confidence stub; Synthesis emergency Markdown fallback still cites research data.
- **No auth** - `thread_id` is a client-generated UUID in `localStorage`.
- **macOS port collision** - the ChatGPT desktop app probes `localhost:8000`, so we default to `:8765`.

## License

Interview submission.