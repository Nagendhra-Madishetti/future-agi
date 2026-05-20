# Commit Checks

The repo uses Husky and lint-staged for fast commit-level checks. The hook only
checks staged files, which keeps normal commits quick while still catching the
highest-signal failures before CI.

## What Runs On Commit

- Backend Python files under `futureagi/`: `ruff check --fix`, then
  `ruff format`.
- Frontend files under `frontend/`: `eslint --fix` for JS/TS, then `prettier`.
- Repo-level JSON/YAML/Markdown and docs: `prettier`.
- `api_contracts/filter_contract.json`: prettier plus frontend contract checks.

Generated frontend contract files and generated OpenAPI JSON are intentionally
excluded from formatting hooks. They should be updated through the contract
generation commands.

## Install

```bash
yarn install
yarn --cwd frontend install
cd futureagi && uv sync --dev
yarn prepare
```

## Run Manually

```bash
yarn lint-staged
yarn contracts:check
cd futureagi && uv run ruff check .
cd futureagi && uv run ruff format --check .
```

## What Belongs In CI Instead

Keep slow or environment-heavy checks in CI or pre-push, not pre-commit:

- Full backend pytest matrix.
- Full frontend Vitest and browser tests.
- Full OpenAPI generation and drift check.
- Django migrations/system checks.
- Security scans and dependency audits.
