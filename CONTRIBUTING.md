# Contributing to trinity-cli

中文：歡迎用中文開 issue 或 merge request。

Thanks for helping. Bug reports, fixes, and docs changes are all welcome.

## Development setup

Python 3.11+ and [uv](https://docs.astral.sh/uv/). The unit tests use fake seats and never start `gbot`, `chatgpt-dot-cli`, or `muse-web-cli`.

```bash
git clone https://gitlab.com/aa22396584/trinity-cli.git
cd trinity-cli
uv venv
uv pip install -e .
.venv/bin/python -m unittest discover -s tests
```

Windows (PowerShell): `.venv\Scripts\python.exe -m unittest discover -s tests`.

`tests/test_contract_muse.py` runs only when `muse-web-cli` is installed; it points `HOME` at a temporary directory.

## Ground rules

- Tests never start a real seat tool or reach a real account. Run them with a temporary `HOME` if you have `gbot` installed.
- Examples use made-up seat and bot names (`researcher`, `Writer`, `example-login`). Do not use your own.
- `tests/test_docs.py` checks that every command is documented in both README sections and in `skills/trinity-cli/SKILL.md`, and that version pins agree.
- Never commit tokens, cookies, credential files, account, chat, or bot ids, message text, emails, IP addresses, host names, or absolute local paths. Use fake values in tests and docs.
- Keep the English and 中文 sections of the README in sync.
- A bug fix comes with a test that fails without it.
- One topic per merge request. Describe how you tested it.

## CI

GitLab CI runs the tests on Linux for every push and on Windows for merge requests (manual), tags, and `main`. A fork uses GitLab.com shared runners by default. Set the `LINUX_RUNNER_TAG` and `WINDOWS_RUNNER_TAG` CI/CD variables to use other runners. There is no macOS CI; maintainers test macOS locally.

## Release process (maintainers)

1. Release the seat tools first if trinity needs their new versions.
2. Bump `version` in `pyproject.toml` and `trinity_cli/__init__.py`, then run `uv lock`.
3. Update the pins in both README sections (`vX.Y.Z pins these versions` / `vX.Y.Z 釘這些版本`) and the release-notes text in `.gitlab-ci.yml`. `tests/test_docs.py` fails until they all agree.
4. Add a `## X.Y.Z - YYYY-MM-DD` heading at the top of `CHANGELOG.md`.
5. Merge to `main` and wait for a green pipeline.
6. Tag `vX.Y.Z` on `main` and push the tag. The tag pipeline checks the version and creates the GitLab Release.

Never move or delete a published tag. Fix forward with a new version.
