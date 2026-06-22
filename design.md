# Design: AI Financial Impetus Transmission Chain

## 1. Vision
Build a shared codebase where each transmission chain is an independent project with its own data folder, while all projects reuse the same engine and tooling.

This supports a practical workflow:
1. AI + code generate a first draft chain.
2. Human analysts review and adjust nodes, edges, and weights.
3. The engine runs propagation and evaluation repeatedly.

## 2. Product Principles
- Project-level isolation: each project has independent data files and iteration history.
- Shared engine: parsing, validation, propagation, and evaluation logic are common code.
- Human-in-the-loop by default: generated data is draft only, final authority is manual review.
- Deterministic core: same input data should produce reproducible outputs.

## 3. Current Scope (Implemented)
- Tree-based chain structure and validation (`validate_tree`).
- Project initialization from AI seed template (`init-project`).
- Project-level run command (`run`).
- Independent project data storage under `projects/<project>/data`.
- Project requirements template generation (`requirements.md`) for iterative requirement capture.

## 4. Data Contract
Primary file:
- `projects/<project>/data/chain.json`

Suggested companion file:
- `projects/<project>/data/requirements.md`

`chain.json` minimal fields:
- `project`: project id
- `schema_version`: schema version
- `root`: root node name
- `generated`: generation metadata
- `nodes`: node list with `name`, `layer`, optional `metadata`
- `edges`: edge list with `src`, `dst`, `weight`

## 5. Workflow (Requirement + Development Loop)
1. Capture or update business requirements in project `requirements.md`.
2. Generate or refresh chain draft (`init-project --force` if needed).
3. Human edits `chain.json`.
4. Run propagation and inspect outputs.
5. Record decisions and unresolved questions in `requirements.md`.
6. Implement code changes only when repeated manual pain points appear.

## 6. Architecture
- `main.py`: CLI orchestration (`init-project`, `run`)
- `project_store.py`: project data pathing and persistence
- `ai_seed.py`: AI seed draft generation
- `chain.py`: propagation engine + tree validation
- `pipeline.py`: project loading + runtime execution

## 7. Near-term Roadmap
- Add schema validation command (`validate-project`).
- Add versioned snapshots for manual edits.
- Add factor metadata taxonomy and constraints.
- Add backtest and scoring modules.
- Add multi-project comparison reports.

## 8. Open Decisions
- Weight semantics: bounded in `[-1, 1]` or extensible?
- Layer taxonomy: fixed enum vs project-defined vocabulary?
- Manual review status: file flag only vs richer approval workflow?
- Data source strategy: local files first vs connector interfaces now?

## 9. Change Log
- 2026-06-23: Introduced projectized workflow and tree validation.
- 2026-06-23: Added per-project requirements template generation.
