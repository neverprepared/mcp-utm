# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Overview

`mcp-utm` is a Model Context Protocol (MCP) server that manages [UTM](https://mac.getutm.app/)
virtual machines on macOS by driving UTM's AppleScript scripting API via `osascript`.

It exposes **22 tools** over stdio. The headline capability is correct MAC-address
randomization for Apple Virtualization Framework clones: Apple VF ignores `MacAddress`
edits written directly into `config.plist` because UTM caches config in memory, so this
server goes through AppleScript's `update configuration` command instead, giving every
clone a unique MAC and therefore a unique IP on `192.168.64.0/24`.

Runtime requirements: **macOS**, **UTM 4.6+**, **Python 3.11+**. Every tool shells out to
`osascript`, so nothing here is exercisable on Linux/CI beyond the unit tests, which mock
`subprocess.run`.

## Architecture

```
src/mcp_utm/
  __main__.py     # entry point -> mcp.run(transport="stdio"); console script `mcp-utm`
  server.py       # FastMCP("utm") instance + 22 @mcp.tool() thin wrappers
  applescript.py  # all AppleScript generation, osascript execution, validation, parsing
  __init__.py     # empty
tests/
  test_server.py      # tool registration (count + names) via mcp._tool_manager
  test_applescript.py # per-function behaviour with subprocess mocked
  test_validation.py  # input validation and AppleScript escaping
```

Two layers, strictly separated:

- **`applescript.py`** — the only place that builds AppleScript or calls `subprocess`.
  Contains `_run()` (the `osascript` runner, raises `RuntimeError` on failure and
  translates "Application can't be found" into "UTM is not running"), the dataclasses
  `VMInfo` / `VMConfig` / `DriveInfo` (each with `to_dict()`), `generate_mac()`
  (locally-administered unicast), and the validators/escaper described below.
- **`server.py`** — declarative MCP surface. Each tool is a small function that validates
  nothing itself, calls the matching `applescript` function, and returns a plain dict or
  list of dicts. Keep it that way: business logic belongs in `applescript.py`.

AppleScript returns are parsed from `||`-delimited, linefeed-separated strings; numbers go
through `_parse_int()` because AppleScript may hand back floats.

## Tools (all in `server.py`)

- **Lifecycle** — `list_vms`, `get_vm`, `clone_vm`, `start_vm`, `stop_vm`, `delete_vm`
- **State** — `suspend_vm`, `wait_for_vm`
- **Networking** — `get_vm_ip` (polls `arp -a` for the VM's MAC), `set_vm_network`
- **Configuration** — `set_vm_resources`, `rename_vm`, `set_vm_display`
- **VirtioFS shares** — `list_vm_shares`, `add_vm_share`, `remove_vm_share`, `set_vm_shares`
- **Drives** — `list_vm_drives`, `attach_drive`
- **Portability** — `export_vm`, `import_vm`
- **Console** — `get_serial_port`

No MCP resources or prompts are exposed — tools only.

## Commands

```bash
uv sync --extra test     # install deps (runtime: mcp[cli]>=1.9; test: pytest>=8)
uv run pytest -q         # run the test suite (106 tests, subprocess mocked)
uv run mcp-utm           # run the server on stdio
uv build                 # build sdist + wheel (hatchling)
```

There is **no linter or formatter configured** (no ruff/black/flake8 config, no `make lint`).
Do not invent a `make lint` invocation; match the existing style by hand.

## CI

`.github/workflows/build-pkg.yml` is the only workflow. It builds a `.deb` (via `fpm`),
publishes to PyPI, and cuts a GitHub Release. It triggers **only on `v*` tags and
`workflow_dispatch`** — **there is no test/lint CI on pull requests**, so run `uv run pytest`
locally before opening one. Note the `.deb` job copies module files individually in
"Assemble package tree"; a new file under `src/mcp_utm/` must be added there too.

Releases are tag-driven: the PyPI job rewrites `version` in `pyproject.toml` from the tag
name, so the committed version and the tag should be kept in step.

## Conventions

- **Security first.** Every value interpolated into AppleScript goes through `_esc()`
  (escapes `\` then `"`), and inputs are validated before use: `_validate_vm_name()`
  (word chars, spaces, hyphens, dots), `_validate_mac()`, `_validate_path()` (absolute,
  no `..` segment), `_validate_timeout()` (clamped to 1–600s), plus bounds on memory
  (64 MiB – 1 TiB) and CPU cores (1–256). A new tool that accepts user input **must**
  validate and escape it — command injection was a fixed bug here, not a hypothetical.
- **Tests are mandatory.** `tests/test_server.py` asserts an exact tool count of 22 and an
  exact name set; adding or renaming a tool requires updating both assertions. New
  `applescript.py` behaviour needs a mocked-subprocess test.
- `from __future__ import annotations` at the top of every module; `str | None` unions.
- Type hints everywhere; dataclasses for structured returns; tools return JSON-friendly
  dicts, never dataclass instances.
- Mutating tools operate on **stopped** VMs — say so in the docstring, since the tool
  docstring is what the MCP client shows the model.
