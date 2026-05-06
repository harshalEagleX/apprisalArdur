# Ardur Testing Brain

This folder is the multi-agent testing system around Playwright.

```text
AI Brain -> Scenario Orchestrator -> Admin/Reviewer Agents -> Playwright
        -> Backend State + DOM Snapshots + Logs + Screenshots -> Evaluator
```

It is intentionally not "AI inside Playwright." Playwright executes. The brain decides, evaluates, and records.

## What Is Included

- `src/brain`: planner and evaluator. Uses deterministic heuristics by default, OpenAI when configured.
- `src/orchestrator`: scenario runner, scheduler, event bus, and run reporting.
- `src/agents`: `AdminAgent` and `ReviewerAgent`, each with a separate browser context.
- `src/state`: backend API client and shared scenario store.
- `src/ui`: role-neutral Playwright controller that reads DOM, clicks, fills, screenshots, and logs actions.
- `src/scenarios/full-lifecycle.ts`: first real high-level scenario.
- `src/runners/full-lifecycle.spec.ts`: Playwright entry point.

## Setup

```bash
cd brain
npm install
npm run install:browsers
cp .env.example .env
```

Edit `.env` with real credentials and URLs. To upload a new batch, set:

```bash
BATCH_ZIP_PATH=/absolute/path/to/valid-batch.zip
CLIENT_ID=1
```

If `BATCH_ZIP_PATH` is empty, the admin agent will look for an existing `UPLOADED`, `ERROR`, or `REVIEW_PENDING` batch.

## Run

Start the backend and frontend first, then:

```bash
cd brain
npm run test:full-lifecycle
```

For broader concurrent runs:

```bash
npm run test:parallel
```

## Optional AI Brain

The harness works without an LLM. To let the planner/evaluator use LangChain over OpenAI:

```bash
AI_PROVIDER=langchain
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-5.4-mini
```

`AI_PROVIDER=openai` is also supported through the direct OpenAI SDK. The deterministic path remains the fallback for repeatability and CI.

## Selector Strategy

The current frontend has good accessible labels and text, but limited `data-testid` coverage. Agents therefore use this order:

1. API state from the Java backend.
2. Accessible roles, labels, and visible text.
3. DOM snapshots and screenshots in reports when a fallback is needed.

Future hardening should add stable `data-testid` attributes around batch rows, queue items, rule cards, and sign-off controls.
