# Repository Guidelines

## Project Structure & Module Organization

- `mcctl` is the Bash entry point for server, backup, staging, mod, and client-pack operations.
- `compose.yaml` defines production, staging, backup, and Packwiz containers.
- `pack/` is the authoritative Packwiz manifest. Mod metadata lives in `pack/mods/*.pw.toml`; redistribution approvals live in `pack/redistribution.toml`.
- `tools/` contains Python validation/release tooling and the pinned Packwiz image.
- `site/` contains GitHub Pages and release metadata; `docs/` contains administrator documentation.
- `.github/workflows/` validates and deploys. Generated or private state belongs in ignored `dist/`, `runtime/`, `.env`, and `secrets/` paths.

## Build, Test, and Development Commands

- `bash -n mcctl` — check shell syntax.
- `python3 -m py_compile tools/*.py` — check Python syntax.
- `./mcctl mod check` — refresh and validate the Packwiz manifest; review any resulting `pack/` diff.
- `python3 tools/release_pack.py safety --pack-dir pack` — enforce non-Modrinth redistribution approvals.
- `python3 tools/release_pack.py release-check --pack-dir pack --release site/release.json` — verify release metadata.
- `docker compose config --quiet` — validate Compose configuration.
- `./mcctl client build` — build and verify the current `.mrpack` in `dist/`; requires Docker and network access.

Do not run `./mcctl start` as a routine validation step. `mod publish` creates a commit and pushes it, so it is not a local test command.

## Coding Style & Naming Conventions

Use two-space indentation in Bash/YAML, four spaces in Python, and existing HTML/CSS formatting. Prefer `snake_case` for functions, kebab-case for mod metadata (for example, `refined-storage.pw.toml`), and versions such as `26.1.2-r2`. Keep errors actionable.

## Testing Guidelines

There is no unit-test framework or coverage threshold. Match CI with the syntax, Packwiz, release, and Compose checks above. Check site changes at mobile and desktop widths. Mod changes also require staging and client import testing; see `docs/ADMIN_GUIDE.md`.

## Commit & Pull Request Guidelines

History uses Conventional Commit-style subjects: `feat: ...`, `docs: ...`, and `chore(pack): ...`. Keep commits focused. Pull requests should describe behavior and risk, list validation performed, link relevant issues, and include screenshots for visible site changes. Never include generated packs, worlds, backups, `.env`, or real credentials.

## Security & Operational Safety

Keep production data under `runtime/data/` untouched during development. Never accept the EULA on another person’s behalf, expose RCON/staging ports, or bypass redistribution checks. Test destructive world or content-mod changes only against staging copies and verified backups.
