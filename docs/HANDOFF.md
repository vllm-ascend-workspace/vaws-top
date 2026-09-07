# HANDOFF: rewiring the scaffold to the standalone vaws-top repository

This document lists exactly what has to change in `vllm-ascend-workspace`
(the scaffold) now that the monitor lives in its own repository at
`https://github.com/vllm-ascend-workspace/vaws-top`. It is written for the
person or agent doing the scaffold-side change; nothing here modifies the
scaffold by itself.

## What changed on the vaws-top side

- The application is no longer a branch of the scaffold. `origin/vaws-top`'s
  history was pushed as `main` of the new repository unchanged, so every commit
  that existed on the branch exists in the new repo with the same hash.
- `backend/npu_fleet_monitor/workspace_adapter.py` is gone. The monitor no
  longer looks for `.agents/skills/machine-management` by walking parent
  directories or `git rev-parse --git-common-dir`, no longer imports
  `npu_occupancy.py` from the scaffold, and no longer reads
  `.vaws-local/machine-inventory.json` or `hosts.txt` from a guessed
  workspace root. Replacement: `device_adapter.py`, `ssh_access.py`,
  `npu_smi.py`, `inventory.py`, configured through three environment
  variables (`NFM_INVENTORY_FILES`, `NFM_HOST_POOL_FILES`,
  `NFM_BOOTSTRAP_COMMAND`). `NFM_SOURCE_WORKSPACE` is not read any more.
- The systemd unit loads `<clone>/.env` via `EnvironmentFile=-`. The Windows
  installer takes `-InventoryFiles`, `-HostPoolFiles`, `-BootstrapCommand`
  instead of `-SourceWorkspace`.
- Every agent-facing payload carries an `observation` envelope with
  `allocation_authority: false`. See `docs/architecture.md`, section
  "Observation-only contract".
- `.agents/skills/vaws-top/` stays in this repository (rationale below). The
  scaffold's `npu-fleet-monitor` skill keeps pointing at
  `<clone>/.agents/skills/vaws-top/SKILL.md`.

## Boundary decision: where the agent skill lives

`.agents/skills/vaws-top/` ships **here**, not in the scaffold. The skill
documents this repository's CLI flags, MCP tool names, JSON fields and the
observation-only contract; all of those change with this code, so the skill
must be versioned with it. The scaffold keeps only the *consumer* skill
(`npu-fleet-monitor`) whose job is to obtain a working local service and hand
the agent the path to the project-local skill. That is the split that already
existed; the only difference is that "obtain" now means "clone and check out"
rather than "fetch a branch and add a worktree".

## Files to change in the scaffold

### `.agents/skills/npu-fleet-monitor/scripts/manage_monitor.py`

Replace the worktree machinery with clone management.

Remove:

- `DEFAULT_BRANCH = "vaws-top"`
- `parse_worktrees()`, `discover_worktree()`, `ref_exists()`,
  `ensure_local_branch()`, `resolve_worktree()`
- the `--branch` and `--worktree` arguments in `main()`
- the `"branch"` key in `payload_for()` and in the `ensure` result

Add:

```python
DEFAULT_REPO_URL = "https://github.com/vllm-ascend-workspace/vaws-top.git"
DEFAULT_REF = "main"          # or a pinned tag/commit once releases exist

def default_clone_dir() -> Path:
    # Keep the old location so existing deployments (and their ignored data/)
    # are picked up instead of duplicated.
    return Path.home() / "vaws-worktrees" / REPO_ROOT.name / "npu-fleet-monitor"

def ensure_clone(url: str, ref: str, target: Path, *, create: bool) -> Path:
    # If target/.git exists: `git -C target remote get-url origin` must equal
    # url; then `git -C target fetch --tags origin` and
    # `git -C target checkout --detach <ref>` (or `git switch ref` when ref is
    # a branch and the caller wants to track it). Refuse if the tree is dirty.
    # If target does not exist and create is True:
    #   git clone --branch <ref> <url> <target>   (tag or branch)
    #   or git clone <url> <target> && git -C target checkout --detach <sha>
    ...
```

Change:

- `validate_project(worktree, branch)` → `validate_project(clone)`. Drop the
  `git branch --show-current == branch` check. Keep the required-files check
  (`package.json`, `scripts/install-user-service.sh`,
  `deploy/npu-fleet-monitor.service`, `.agents/skills/vaws-top/SKILL.md`) and
  the clean-tree check. Additionally assert
  `git -C clone remote get-url origin` equals `DEFAULT_REPO_URL` (or the
  `--repo-url` override) so an unrelated checkout is never deployed.
- `build_if_needed(worktree, commit)` — unchanged logic, rename the parameter.
  It already runs `npm ci`, `npm run test:backend`, `npm run build` and stores
  `data/.deployed-commit`.
- `install_and_restart(worktree)` — before calling
  `scripts/install-user-service.sh`, write `<clone>/.env` (see next section).
  `.env` is ignored by vaws-top's `.gitignore`, so the clean-tree check still
  passes.
- `payload_for(action, branch, worktree, commit, built)` →
  `payload_for(action, clone, commit, built)`. Rename `worktree` → `clone`
  and `branch` → `ref` in the output JSON; keep `agent_skill` exactly as
  `str(clone / ".agents/skills/vaws-top/SKILL.md")`.
- `main()`: replace `--branch/--worktree` with `--repo-url`, `--ref`,
  `--clone-dir`.

### `.env` written by `manage_monitor.py`

The scaffold is the only party that knows its own layout, so it must tell the
monitor where its files are. Generate `<clone>/.env` from these scaffold paths:

```text
NFM_INVENTORY_FILES=<REPO_ROOT>/.vaws-local/machine-inventory.json
NFM_HOST_POOL_FILES=<REPO_ROOT>/hosts.txt
NFM_BOOTSTRAP_COMMAND={python} <REPO_ROOT>/.agents/skills/machine-management/scripts/manage_machine.py bootstrap-host-key --host {host} --host-port {port} --user {user} --public-key-file {public_key_file} --password-stdin
```

Notes:

- `REPO_ROOT` in `manage_monitor.py` is `Path(__file__).resolve().parents[4]`.
  If the scaffold is used from a linked worktree and the shared inventory lives
  next to the Git common dir, resolve that here (as the old
  `discover_workspace_servers()` did) and pass *both* paths separated by
  `os.pathsep`. The monitor merges them in order and de-duplicates endpoints.
- `manage_machine.py bootstrap-host-key` still has to read the password from
  stdin and exit 0 on success; vaws-top only checks the exit status and then
  verifies key login itself.
- `NFM_HOST_POOL_FILES` is optional; omit the line when `hosts.txt` does not
  exist.
- Do not write anything else secret into `.env`. Passwords never go there.

### `.agents/skills/npu-fleet-monitor/tests/test_manage_monitor.py`

- Delete `test_parse_worktrees_preserves_branch_mapping`,
  `test_default_branch_is_standalone_project_branch`,
  `test_missing_local_branch_tracks_origin_branch`.
- Add: `DEFAULT_REPO_URL` points at
  `https://github.com/vllm-ascend-workspace/vaws-top.git`; `ensure_clone()`
  refuses a dirty tree and a mismatched `origin` URL; the generated `.env`
  contains the three `NFM_*` lines and no password material.
- Update `test_validate_project_rejects_missing_contract` and
  `test_payload_exposes_project_local_agent_skill` for the new signatures.

### `.agents/skills/npu-fleet-monitor/SKILL.md`

- Frontmatter `description`: replace "Bootstrap or locate the standalone
  vaws-top worktree" with "Clone or locate the standalone vaws-top repository".
- Body: the returned JSON key is `clone` instead of `worktree`; commands are
  otherwise unchanged. Replace the closing line "preserve the worktree's
  ignored `data/`" with "preserve the clone's ignored `data/` and `.env`".
- Keep the observation-only statement ("Capacity is observed availability, not
  a reservation") and add: "vaws-top output must not be used to decide device
  allocation; use the coordinator's host queue."

### `.agents/skills/npu-fleet-monitor/agents/openai.yaml`

`short_description`: "Locate or deploy the standalone vaws-top service" is
still accurate; no change required.

### `docs/npu-fleet-monitor.md`

- Paragraph 1: the app lives in the separate repository
  `vllm-ascend-workspace/vaws-top`, not on a `vaws-top` branch.
- Step 1 of "一键拉起": "首次使用时克隆
  `https://github.com/vllm-ascend-workspace/vaws-top` 到
  `~/vaws-worktrees/<仓库名>/npu-fleet-monitor`（或 `--clone-dir`），之后
  `git fetch` 并检出 `--ref`".
- "数据与设备发现": replace the Git common-dir discovery paragraph with the
  `.env` contract above and drop `NFM_SOURCE_WORKSPACE`.

### `AGENTS.md`, `README.md`, `.agents/README.md`

Replace "from its standalone worktree" / "独立 worktree" / "独立的
`vaws-top` 分支" wording with "from the standalone vaws-top repository". The
`AGENTS.md` skill table row for `npu-fleet-monitor` and README lines 32, 47
and 177 (as of the current `main`) are the ones that mention the branch or
worktree.

### `.gitignore`

No change: the clone lives outside the scaffold tree.

### The `vaws-top` branch in the scaffold repository

Leave `origin/vaws-top` in place until the scaffold-side change has landed
and been exercised once (`manage_monitor.py ensure` against the new repo).
Then delete the branch from the scaffold remote; the new repository's `main`
contains the identical commits. Do not delete it first.

## What remains coupled after this handoff

- The inventory JSON schema (`{"machines": [{"alias", "host": {"ip", "port",
  "user", "machine_type"}}]}`) and the "first field of a `hosts.txt` line" rule
  are formats that originated in the scaffold. vaws-top reads them from
  explicitly configured paths but still assumes those shapes.
- `manage_machine.py bootstrap-host-key` is the only known implementation of
  the bootstrap command contract (password on stdin, exit 0 on success).
- The derived `低优先级` tag encodes the scaffold's notion of "in the active
  inventory vs only in the host pool".
- The scaffold's `manage_monitor.py` stays responsible for Node.js version
  checks, `npm ci`, backend tests, `npm run build`, systemd installation and
  the health probe; vaws-top only ships the scripts it calls.
