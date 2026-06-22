# Impetus Transmission Chain

AI-assisted financial transmission chain project scaffold.

## Core idea

- Each `chain` is a tree-shaped structure and treated as one standalone project.
- Each project keeps runtime/editable data under `data/`.
- Each project also keeps core analysis assets under `core/` (not ordinary data).
- All projects share the same code in `src/impetus_chain`.

## Project layout

```text
src/impetus_chain/
  main.py
  ui_server.py
  ai_gateway.py
  project_store.py
projects/
  <project_name>/
    data/
      chain.json
      requirements.md
    core/
      analysis_strategy.yaml
      ai_prompt.md
tests/
```

## Quick start

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
python -m impetus_chain.main
```

## Workflow

1. Create project in UI or CLI:

```bash
python -m impetus_chain.main init-project --project macro_chain
```

2. Refine project files:
- Data file: `projects/<project>/data/chain.json`
- Core strategy file: `projects/<project>/core/analysis_strategy.yaml`
- Core AI prompt file: `projects/<project>/core/ai_prompt.md`

3. Node analysis in UI:
- Click a node in the tree
- Select AI provider
- Click `Analyze Node / Re-analyze Node`

## AI providers

- OpenAI (`OPENAI_API_KEY`)
- Anthropic (`ANTHROPIC_API_KEY`)
- Gemini (`GEMINI_API_KEY`)
- DeepSeek (`DEEPSEEK_API_KEY`)
- Qwen DashScope (`DASHSCOPE_API_KEY`)

## Notes

- `projects/*/data/` is ignored by git.
- `projects/*/core/` is project core information and should be versioned.
- `projects/*/core/api_keys.enc.json` stores encrypted project API keys and is ignored by git.
- Node analysis now reads API key in this order: project encrypted key -> environment variable.
- Set `IMPETUS_SECRETS_MASTER_KEY` to strengthen local encryption for project keys.
- Top-level design roadmap is in `design.md`.
