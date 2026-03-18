# TokenScope

### Profile your LLM payloads. Find the waste. Cut the cost.

```bash
pip install llm-tokenscope
```

**Live API:** https://token-scope.onrender.com  
**PyPI:** https://pypi.org/project/llm-tokenscope  
**Status:** 🟡 Backend complete · Web UI in progress

---

## The Problem

You're paying too much for LLM API calls. But you don't know why.

Your payload isn't just your prompt. It's JSON — keys, nested objects, tool schemas, conversation history, metadata, context chunks. By the time it hits the API, your code has assembled something expensive that you've never actually looked at.

There's no tool that shows you _which fields_ are burning your budget. **TokenScope fixes that.**

---

## Two Ways to Use It

### 1. Python SDK — Profile Real Traffic

Wrap your existing LLM client. Zero code changes to your app logic.

```python
from tokenscope import TokenScope
from openai import OpenAI

with TokenScope(OpenAI()) as client:
    response = client.chat.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Hello!"}]
    )
# HTML report opens automatically in your browser
```

Works with any OpenAI-compatible API — OpenAI, Ollama, Together, Anyscale, anything.

### 2. REST API — Analyze Any Payload

```bash
curl -X POST https://token-scope.onrender.com/api/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "payload": {
      "model": "gpt-4o",
      "messages": [{"role": "user", "content": "Hello"}]
    }
  }'
```

### 3. Web UI _(coming soon)_

Paste any payload at `tokenscope.io` — no install, no signup, instant analysis.

---

## The HTML Report

After your session, a self-contained HTML report opens in your browser showing:

**Session Summary**

- Total calls made
- Sent tokens — tiktoken count of what was actually sent to the API
- Analyzed tokens — full payload count including any extra context you attached
- Total cost estimate
- Total tokens saveable across all calls

**Per Call**

- Top cost fields — which specific JSON keys are most expensive (leaf fields only)
- Cost Leaks — detected waste with severity and estimated savings
- Sent vs analyzed vs output token counts
- Cost and duration

---

## Cost Leaks Detected

| Rule                | What It Catches                                      | Severity  |
| ------------------- | ---------------------------------------------------- | --------- |
| `VERBOSE_SCHEMA`    | Tool/function descriptions over 200 tokens           | 🔴 High   |
| `BLOATED_ARRAY`     | Arrays with 3+ similar items that could be trimmed   | 🔴 High   |
| `DUPLICATE_CONTENT` | Same content appearing in multiple fields            | 🔴 High   |
| `REPEATED_KEYS`     | Same key appearing 5+ times across the payload       | 🟡 Medium |
| `LOW_SIGNAL_FIELDS` | UUIDs, timestamps, IDs the model doesn't reason over | 🟡 Medium |
| `DEEP_NESTING`      | Objects nested 4+ levels deep                        | 🟢 Low    |

---

## SDK Usage

### Basic

```python
from tokenscope import TokenScope
from openai import OpenAI

with TokenScope(OpenAI()) as client:
    client.chat.create(model="gpt-4o", messages=[...])
    client.chat.create(model="gpt-4o", messages=[...])
# Report generated on exit
```

### With Ollama (local models)

```python
from tokenscope import TokenScope
from openai import OpenAI

with TokenScope(
    OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
) as client:
    client.chat.create(model="llama3", messages=[...])
# Cost shows $0.00 for local models — all other profiling works normally
```

### Attach Extra Context for Analysis

Profile data that's generated in your app but isn't part of the message:

```python
client.chat.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Summarize"}],
    extra_data={
        "request_id": "abc-123",
        "context": [{"text": chunk} for chunk in retrieved_chunks],
    }
)
# extra_data is stripped before the API call
# but included in the leak analysis and report
```

### Manual Report Control

```python
client = TokenScope(OpenAI(), auto_report=False)

client.chat.create(...)
client.chat.create(...)

# Access session data
print(client.session.total_input_tokens)
print(client.session.total_cost_usd)
print(client.session.total_tokens_saved)

# Generate report whenever you want
client.report()
```

### Context Manager

```python
with TokenScope(OpenAI(), auto_report=True) as client:
    client.chat.create(...)
# Report auto-opens when block exits
```

---

## REST API

**Base URL:** `https://token-scope.onrender.com`

### `POST /api/v1/analyze`

**Request:**

```json
{
  "payload": {},
  "model_id": "gpt-4o",
  "requests_per_day": 100,
  "encoding": "cl100k_base"
}
```

**Response includes:**

- `total_tokens` — exact tiktoken count
- `fields` — per-field token attribution (leaf fields only)
- `top_contributors` — top 5 most expensive fields
- `leaks` — detected cost leaks with severity and savings estimate
- `optimization` — cleaned payload with tokens saved
- `cost` — per-request cost breakdown
- `monthly` — projected monthly cost at given request volume
- `all_models` — cost comparison across all supported models

### `GET /api/v1/health`

```json
{ "status": "ok", "version": "1.0.0" }
```

---

## Supported Models for Cost Calculation

| Model             | Provider  | Input (per 1M) | Output (per 1M) |
| ----------------- | --------- | -------------- | --------------- |
| GPT-4o            | OpenAI    | $2.50          | $10.00          |
| GPT-4o mini       | OpenAI    | $0.15          | $0.60           |
| GPT-4 Turbo       | OpenAI    | $10.00         | $30.00          |
| Claude 3.5 Sonnet | Anthropic | $3.00          | $15.00          |
| Claude 3 Haiku    | Anthropic | $0.25          | $1.25           |
| Gemini 1.5 Pro    | Google    | $1.25          | $5.00           |

Any model not in this list (Ollama, local models, etc.) shows `$0.00` — all other profiling works normally.

---

## How Token Counting Works

TokenScope uses `tiktoken` — OpenAI's own tokenizer. Token counting is deterministic math, not inference. No API calls. No data leaves your machine.

**Accuracy:** Exact for OpenAI models. ~95% for Claude. ~90% for Gemini.

**Two token counts per call:**

- **Sent tokens** — tiktoken count of what was actually sent to the API. Your billing estimate.
- **Analyzed tokens** — full payload count including `extra_data`. What leak detection works against.

---

## Architecture

```
core/                     ← pure Python, zero framework dependencies
        ↓                              ↓
api/                               sdk/
(FastAPI → Web UI)         (direct import, no HTTP)
```

One core engine. Two consumers. The SDK imports `core/` directly — no server needed, works fully offline.

---

## Project Structure

```
token-scope/
├── core/
│   ├── tokenizer.py         ← per-field token counting
│   ├── parser.py            ← JSON tree walker
│   ├── leak_detector.py     ← 6-rule waste detection engine
│   ├── payload_optimizer.py ← applies fixes, outputs clean payload
│   └── calculator.py        ← token → dollar cost
│
├── api/
│   ├── main.py              ← FastAPI + CORS
│   ├── routes.py            ← /analyze, /health
│   └── models.py            ← Pydantic models
│
├── sdk/
│   ├── client.py            ← wraps OpenAI-compatible clients
│   └── reporter.py          ← generates HTML report
│
├── web/                     ← React + Vite (in progress)
├── Dockerfile
├── render.yaml
└── requirements.txt
```

---

## Running Locally

```bash
git clone https://github.com/DevelopedBy-Siva/token-scope
cd token-scope
pip install -r requirements.txt

# Start the API
cd api && uvicorn main:app --reload

# Use the SDK from source
from sdk import TokenScope
```

---

## Why Not Existing Tools?

| Tool       | What It Does                  | What It Misses                   |
| ---------- | ----------------------------- | -------------------------------- |
| Helicone   | Logs calls, tracks total cost | No field-level attribution       |
| LangSmith  | Observability for LangChain   | LangChain-only, not cost-focused |
| Braintrust | Evaluation and logging        | Not cost optimization focused    |
| Portkey    | LLM gateway with analytics    | Broad but shallow                |

**TokenScope is the only tool that attributes token costs to individual JSON fields, detects structural waste, and shows you the optimized version.**

---

## License

MIT — use it, fork it, learn from it.

---

_Built to understand LLM costs, not guess at them._
