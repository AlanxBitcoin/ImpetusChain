# Impetus Transmission Chain

AI-assisted financial transmission chain project scaffold.

## Core idea

- Each `chain` is a tree-shaped structure and is treated as one standalone project.
- Each project has its own independent data folder.
- All projects share the same code in `src/impetus_chain`.
- Project data is generated as an AI draft first, then manually adjusted by analysts.

## Project layout

```text
src/impetus_chain/
  main.py
  chain.py
  pipeline.py
  ai_seed.py
  project_store.py
projects/
  <project_name>/
    data/
      chain.json
tests/
```

## Quick start

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
```

## Workflow

1. Initialize a project with AI-generated draft data:

```bash
python -m impetus_chain.main init-project --project macro_chain
```

2. Refine requirements in `projects/macro_chain/data/requirements.md`.

3. Manually edit `projects/macro_chain/data/chain.json`:
- adjust nodes
- adjust edge weights
- keep it as a tree

4. Run propagation:

```bash
python -m impetus_chain.main run --project macro_chain --shock 0.8
```

## Notes

- Tree validation is enforced before running.
- Use `--force` with `init-project` to overwrite existing draft data.
- Top-level design and roadmap live in `design.md`.
