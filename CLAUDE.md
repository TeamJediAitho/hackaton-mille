# CLAUDE.md

## Core Principles

* Before modifying code, understand the project structure and existing conventions.
* Do not invent frameworks, libraries, commands, or conventions when they can be verified from the repository.
* Prefer simple, focused changes that are consistent with the existing codebase.
* Do not modify files that are not necessary to complete the task.
* Do not introduce new dependencies without a valid reason.
* Before considering a task complete, run the relevant tests and checks available in the project.

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
feature/user-authentication
feature/export-pdf
feature/payment-integration
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

### Package manager

The project uses **uv** as its Python package and project manager.

Do not use `pip` directly to install or update project dependencies.

Use:

```bash
uv add <package>
uv remove <package>
uv sync
```

To execute Python or project tools, prefer:

```bash
uv run python ...
uv run <command>
```

There is no need to manually activate `.venv` when using `uv run`.

### Dependencies

Project dependencies must be declared in `pyproject.toml`.

Use `uv add` to add dependencies instead of manually editing `pyproject.toml` whenever possible.

The `uv.lock` file must remain synchronized with `pyproject.toml`.

Do not manually edit `uv.lock`.

After changing dependencies, run:

```bash
uv sync
```

### Environment

Do not manually create virtual environments with:

```bash
python -m venv ...
```

when the project is already configured to use `uv`.

Do not install project dependencies globally.

## Testing

Before considering a feature complete:

1. Run the existing tests.
2. Run linting and formatting if configured.
3. Run type checking if configured.
4. Add appropriate tests for new functionality when necessary.

Prefer commands defined by the project in `pyproject.toml`, `Makefile`, `README`, or CI configuration.

For example:

```bash
uv run pytest
```

Do not assume that `pytest` is the project's test runner without first checking the repository configuration.

## Code Quality

* Follow the existing style of the repository.
* Prefer readable and straightforward code over unnecessary abstractions.
* Avoid duplication when a shared solution is clearly appropriate.
* Do not perform unrelated refactoring as part of a feature.
* Preserve existing API compatibility unless explicitly instructed otherwise.
* Handle errors consistently with the rest of the project.

## Dependencies

Before adding a new dependency:

1. Check whether the project already provides an equivalent solution.
2. Consider whether the functionality can be implemented without a new dependency.
3. Verify compatibility with the project's Python version and existing dependencies.
4. Add the dependency using `uv add`.

Do not add dependencies solely for convenience when the requested functionality can be implemented easily with the standard library.

## Completion Checklist

Before declaring a task complete, verify:

* [ ] The work was developed on a dedicated feature branch.
* [ ] `git status` shows no unintended changes.
* [ ] A PR from the feature branch into `main` has been opened via `gh`, with a feature description and a testing checklist.
* [ ] Dependencies on other open PRs have been checked (`gh pr list`) and documented in the PR.
* [ ] The PR has been left open for manual review (not self-merged).
* [ ] Dependencies are managed through `uv`.
* [ ] `pyproject.toml` and `uv.lock` are synchronized.
* [ ] Relevant tests have been run.
* [ ] Linting, formatting, and type checking have been run if configured.
* [ ] No unrelated changes have been introduced.
* [ ] The implementation follows the existing project conventions. 