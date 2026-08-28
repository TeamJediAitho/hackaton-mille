# CLAUDE.md

## Project

**Il caso dei Mille** — a hackathon RAG pipeline over a 1860 Garibaldi archive. `README.md` is the
participant-facing guide (Italian) and stays the source of truth for rules and deadlines; this file
is the agent-facing summary.

The repo ships a working **naive dense RAG baseline**. The job is to improve retrieval and
generation *without breaking the submission contract*.

* Entrypoint: `baseline_naive_rag.py` — ingest, RAG, submission writing and validation, all in one
  file, driven by `argparse`.
* Stack: `datapizza-ai` (`DagPipeline`), `OpenAIEmbedder` (`text-embedding-3-small`, 1536 dim),
  local Qdrant under `outputs/qdrant`, `DoclingParser` for PDFs.
* Corpus: `data/act_1/` and `data/act_2/`. Act 2 is the hard one — scans, maps, propaganda,
  conflicting versions. There is no act 3: the Gold Run asks new questions over the same archive.
* `data/manifest.json` is the **source of truth**. A file in `data/` that is not in the manifest
  does not exist for ingest, indexing or `document_id` validation.

### Layout

| Path | Purpose |
| --- | --- |
| `baseline_naive_rag.py` | Entrypoint: ingest, RAG, submission write + validate |
| `data/act_1/`, `data/act_2/` | The archive documents |
| `data/manifest.json` | Mandatory catalogue; validates `document_id` |
| `data/checksums.sha256`, `data/license_manifest.csv` | Integrity and source licences |
| `eval/` | `sample_questions.json`, `sample_annotations.json`, submission example + JSON schema |
| `scripts/install_release.py` | Installs an Act 2 release pack and updates the manifest |
| `outputs/` | Qdrant index and submissions — generated, not versioned |
| `tests/test_submission_schema.py` | Submission contract tests |
| `TEAM_NOTES.md` | Problem / fix / lesson log, one block per problem |

### Commands

```bash
source .venv/bin/activate
make setup          # pip install -r requirements.txt
make sample         # baseline on eval/sample_questions.json -> outputs/submission_sample.json --rebuild
make test           # pytest -q
make clean          # drops outputs/qdrant, submissions, caches
```

A round run (official questions come from the dashboard, never from the repo):

```bash
python baseline_naive_rag.py \
  --questions path/to/questions_round_1.json \
  --round-id round_1 \
  --output outputs/submission_round_1.json
```

Re-validate a file locally without calling any API (does not consume the attempt):

```bash
python baseline_naive_rag.py --validate-only \
  --submission outputs/submission_round_1.json \
  --questions path/to/questions_round_1.json \
  --manifest data/manifest.json \
  --round-id round_1
```

`--rebuild` is all-or-nothing: it deletes the Qdrant collection and reprocesses the whole archive.
Use it after changing chunking/embedding/ingest logic or after installing Act 2 — **not** for new
questions or prompt-only changes.

### Submission contract — do not break

Validated by `eval/submission.schema.json` and `tests/test_submission_schema.py`:

* top-level `schema_version` (`"1.0"`), `round_id`, `answers`;
* per answer: `question_id`, `question`, `answer`, `contexts`, `telemetry`;
* at most **5** contexts, `rank` 1..N consecutive, with `document_id` (in the manifest) and `content`;
* `telemetry`: `latency_ms`, `declared_cost_eur`, `model_calls`.

Hard rules:

* `contexts` are the evidences **actually passed to the generator**, in top-k order. Never add
  citations after generation, never invent content to make a source look better. A context not
  traceable to the corpus zeroes Faithfulness for that question.
* No extra fields (`chunk_id`, `page`, `location_label`, `confidence`, `repository_url`,
  `commit_hash`, …).
* Abstention is a valid, rewarded answer when the evidence is thin.
* `.env` holds the API key — it is gitignored, keep it out of commits and out of any output.

## Prior art — the `corso-datapizza` skill

Before implementing a RAG technique from scratch, invoke the **`corso-datapizza`** skill
(`.claude/skills/corso-datapizza/`). It navigates the AITHO/Datapizza course archive, which is built
on the *same stack as this repo* and already has runnable, measured solutions for most of what this
hackathon asks:

* chunking strategies, hybrid search / BM25+RRF, reranking, query rewrite, HyDE, parent-child,
  RAPTOR;
* Docling parsing, OCR and multimodal PDFs (the `garib_*` scans and the map);
* Qdrant payload filtering — index `act`, `reliability`, `modality` as payload and filter on them;
* eval harnesses: recall@k, MRR, hit@k, RAGAS faithfulness, LLM-as-judge calibration,
  don't-know rate, gold datasets;
* cost/latency telemetry, caching, tracing, Streamlit demos.

The skill's routing table maps a problem to the exact file; `references/rag-playbook.md` carries the
ported code patterns and the course's measured results. The archive is in Italian. **Do not
re-derive what the course already solved**, and never copy the archive's `.env` files into this repo.

## Core Principles

* Before modifying code, understand the project structure and existing conventions.
* Do not invent frameworks, libraries, commands, or conventions when they can be verified from the repository.
* Prefer simple, focused changes that are consistent with the existing codebase.
* Do not modify files that are not necessary to complete the task.
* Do not introduce new dependencies without a valid reason.
* Before considering a task complete, run the relevant tests and checks available in the project.
* One experiment at a time: state the hypothesis, change one component, compare on the sample, then
  keep or discard. Record what happened in `TEAM_NOTES.md`.

## Git Workflow

### Dedicated branch for every new feature

Every new feature must be developed on a **dedicated Git branch**.

Never develop a new feature directly on `main` or `master`.

Before making any changes related to a new feature, the agent must:

1. Run `git status`.
2. Check the current branch with `git branch --show-current`.
3. If the current branch is `main` or `master`, create a new branch.
4. If the current branch belongs to a different feature, create a new branch.
5. Do not modify files until the correct feature branch has been selected.

### Branch naming

Use:

```text
feature/<short-description>
```

Examples:

```text
feature/hybrid-search
feature/ocr-scans
feature/incremental-ingest
```

### Existing branches

If the user explicitly specifies a branch to use, use that branch instead of creating a new one.

Do not create, delete, or switch branches without a reason related to the task or explicit user direction.

### Pull Requests

Every feature is integrated into `main` through a **Pull Request opened from its feature branch**. Features are never merged locally or pushed directly to `main`.

For each feature:

1. Push the feature branch to the remote.
2. Open a PR from `feature/<short-description>` into `main` using the **GitHub CLI** (`gh`), which is expected to be already authenticated. If `gh auth status` shows it is not logged in, run `gh auth login` (or ask the user to run `! gh auth login` if interactive auth is required) before proceeding.
3. The PR is **reviewed manually by the maintainers** — do not merge it yourself. Leave it open for review unless the user explicitly asks to merge.

#### PR description

Every PR body must include:

* **Feature description** — what the feature does, why it is needed, and a summary of the approach and the main changes.
* **Testing checklist** — a concrete, ordered checklist a reviewer can follow to exercise and verify the feature (setup steps, commands to run, expected results, edge cases to check).

Use a `gh pr create` invocation with a heredoc body, for example:

```bash
gh pr create --base main --head feature/<short-description> \
  --title "<concise feature title>" \
  --body "$(cat <<'EOF'
## Feature description

<what and why, summary of changes>

## Testing checklist

- [ ] <step 1 — command / action and expected result>
- [ ] <step 2>
- [ ] <edge case>
EOF
)"
```

#### Dependencies between PRs

Before opening a PR, check for other open PRs with `gh pr list`. If the new feature depends on changes still under review in another open PR:

* State the dependency explicitly in the PR description (e.g. "Depends on #123 — should be merged after it").
* Base the feature branch on the dependency branch rather than on `main` when the code genuinely needs it, and note this in the PR.
* Flag to the user any ordering or merge-conflict risk between the open PRs.

## Python

### Environment

Python 3.13 (`.python-version`), standard virtual environment in `.venv`. Setup:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements.txt
cp .env.example .env      # then add OPENAI_API_KEY
```

Always activate the virtual environment before running project commands.

The `garib_*` scans additionally need Tesseract and an OCR backend supported by Docling. The OCR is
noisy and the layout irregular on purpose — that is part of the challenge, not an invitation to fill
the gaps by guessing.

### Environment variables

`.env.example` documents them: `OPENAI_API_KEY` (required), `OPENAI_MODEL` (or `DATAPIZZA_MODEL`),
`QDRANT_PATH`, `COLLECTION_NAME`, `MAX_CONTEXTS`, and the `COST_*_PER_MILLION_EUR` rates used to
compute `declared_cost_eur`.

### Dependencies

Project dependencies are declared in `requirements.txt`.

To install or update dependencies:

```bash
pip install -r requirements.txt
```

Do not add dependencies without first checking the project already provides an equivalent solution.

## Testing

Before considering a feature complete:

1. Run `make test` (`pytest -q`, configured in `pytest.ini`, `testpaths = tests`).
2. Run `make sample` end-to-end when the change touches ingest, retrieval or generation, and check
   the run ends with `Submission valida: outputs/submission_sample.json`.
3. Add appropriate tests for new functionality when necessary.

There is no linter, formatter or type checker configured — do not introduce one as part of a feature.

## Code Quality

* Follow the existing style of the repository.
* Prefer readable and straightforward code over unnecessary abstractions.
* Avoid duplication when a shared solution is clearly appropriate.
* Do not perform unrelated refactoring as part of a feature.
* Preserve existing API compatibility unless explicitly instructed otherwise.
* Handle errors consistently with the rest of the project.
* Keep the CLI contract of `baseline_naive_rag.py` (flags, `--validate-only` behaviour, exit codes)
  backward compatible.

## Dependencies

Before adding a new dependency:

1. Check whether the project already provides an equivalent solution.
2. Consider whether the functionality can be implemented without a new dependency.
3. Verify compatibility with the project's Python version and existing dependencies.
4. Add the dependency to `requirements.txt`.

Do not add dependencies solely for convenience when the requested functionality can be implemented easily with the standard library.

## Completion Checklist

Before declaring a task complete, verify:

* [ ] The work was developed on a dedicated feature branch.
* [ ] `git status` shows no unintended changes (no `.env`, no `outputs/` artefacts).
* [ ] A PR from the feature branch into `main` has been opened via `gh`, with a feature description and a testing checklist.
* [ ] Dependencies on other open PRs have been checked (`gh pr list`) and documented in the PR.
* [ ] The PR has been left open for manual review (not self-merged).
* [ ] `make test` passes; `make sample` still produces a valid submission when the pipeline changed.
* [ ] The submission contract is intact: ≤ 5 contexts, consecutive ranks, `document_id` in the manifest, no extra fields.
* [ ] No unrelated changes have been introduced.
* [ ] The implementation follows the existing project conventions.
