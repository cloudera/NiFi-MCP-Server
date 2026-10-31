# NiFi MCP Server modernisation — local verification receipt

## Scope

This working branch combines the two existing fork improvements for standalone NiFi authentication and flowfile/provenance diagnostics, then adds safety and reliability guardrails. It does not modify Kevin Talbert's upstream repository.

## Changes in this branch

- **Secret redaction:** normalize key names across camelCase, snake_case, hyphenated and mixed-case variants; cover API keys, authorization, cookies, access/refresh tokens, private keys, keytabs and keystore/truststore passwords.
- **Mutation retry safety:** automatic retries remain for read-only GET calls and only for transient connection/timeouts, HTTP 429 and 5xx responses. POST/PUT/DELETE are not retried automatically because a timeout can occur after the server has applied the mutation.
- **Version detection:** remove the silent fallback to NiFi 1.0.0. Parse normal and snapshot versions; fail explicitly when `/flow/about` cannot establish a version.
- **Health confidence:** record check coverage for processors, connections, controller services and bulletins. Failed optional checks are surfaced as errors and the overall result becomes `UNKNOWN`, not falsely `HEALTHY`.
- **Dependency compatibility:** constrain the existing FastMCP implementation to MCP SDK v1 (`mcp<2`) rather than permitting v2, which removes/renames the imported API and currently breaks server startup. Test dependencies are available via the `test` extra.
- **Regression tests:** add tests for redaction, unknown/version parsing, mutation timeout retry behaviour, non-retryable read errors and incomplete health-check coverage.

## Verification performed locally

- `PYTHONPATH=src python -m unittest discover -s tests -v`: 9 tests passed in the current checkout.
- `PYTHONPATH=src python -m compileall -q src tests scripts`: passed.
- `git diff --check`: passed after whitespace cleanup.
- No Docker used and no live NiFi/Knox cluster contacted.

## Not yet verified / blocked

- No live NiFi endpoint was available for end-to-end integration tests.
- No write operation was exercised against a real NiFi instance.
- The local GitHub connector reports `push: false` for the `Vinz2168/NiFi-MCP-Server-cloudera` fork; this branch has not been published or opened as a PR.
- Ruff reports numerous pre-existing project-wide modernization/style findings (including legacy `typing` aliases); these were not mass-rewritten because that would create unrelated churn.

## Reproducible setup

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
python -m unittest discover -s tests -v
python -m compileall -q src tests
```


## Repeatable MCP protocol smoke checks — 2026-10-28

Verified again on the connected Mac using `/tmp/nifi-mcp-modernise/.venv/bin/python`:

- `python -m unittest discover -s tests -v`: **5/5 passed**.
- `python -m compileall -q src tests scripts`: passed.
- `git diff --check`: passed.
- `PYTHONPATH=src python scripts/smoke_mcp.py`: passed; MCP protocol `2025-11-25`, server `nifi-mcp-server 1.30.0`, 35 tools registered; all four required tools found.
- Started Streamable HTTP locally on `127.0.0.1:8000`, then ran `scripts/smoke_mcp.py --transport streamable-http --url http://127.0.0.1:8000/mcp`: passed with the same 35 tools; MCP HTTP requests returned 200/202 as expected. The temporary server was terminated after the test.

**Scope limitation remains:** both protocol tests use `NIFI_API_BASE=http://127.0.0.1:1/nifi-api`, an intentionally unreachable placeholder, and `NIFI_READONLY=true`. They do not call NiFi tools or prove live API connectivity/authentication. Safe config discovery found no NiFi entry in Claude Desktop's MCP server list, no NiFi-related environment variables, and no local listeners on ports 8000, 8080, 8443 or 9090 after the test. The only discovered `.env` file contains unrelated MCP-governance settings; its values were not displayed. A real authorised NiFi endpoint and approved authentication method remain required for end-to-end acceptance.



Additional MCP transport check after allowlist implementation:

- A real stdio MCP client session launched the server with NIFI_READONLY=false and NIFI_ALLOWED_ACTIONS=start_processor.
- MCP tools/list returned 36 tools: start_processor was exposed, create_processor and empty_connection_queue were absent, and read-only get_controller_service_details remained available.
- No NiFi tool was invoked; this proves MCP-level tool exposure only, not NiFi API connectivity or a write operation.

## Action allowlist enforcement — 2026-10-28

A follow-up audit found that ServerConfig parsed NIFI_ALLOWED_ACTIONS, but the server did not apply the setting when registering mutation tools. This meant the configuration looked available without actually limiting the tool surface. That gap is now fixed in this branch:

- With NIFI_READONLY=true, no mutation tools are registered.
- When NIFI_READONLY=false and NIFI_ALLOWED_ACTIONS is non-empty, only exact comma-separated mutation-tool names are registered (case-insensitive; surrounding whitespace ignored).
- Unknown names fail startup rather than silently enabling an unintended tool set.
- An empty allowlist preserves backward compatibility: explicitly setting NIFI_READONLY=false exposes the full mutation tool set.
- Read-only tools remain available regardless of the write allowlist.

Three regression tests cover allowlist filtering, unknown action rejection, and backward-compatible explicit write enablement. Current checkout suite: 8/8 tests pass. The allowlist is an MCP tool-exposure guardrail, not a substitute for NiFi's own authentication/authorisation policies.

---

## Independent audit reconciliation — current authoritative state, 2026-10-28

This section supersedes any earlier checkpoint in this receipt that says the branch was unpublished or reports an earlier test count. Earlier counts are retained above as historical checkpoints, not the current result.

### Source and reproducible code checks

- Published source: `trojan-oz/NiFi-MCP-Server`, branch `modernise/evidence-first-guardrails`, audited head before this receipt update: `2dedf8726c58e8ce873846c35d0a03bfc0e278b1`.
- Working Mac checkout matched that exact commit and branch.
- Command: `PYTHONPATH=src /tmp/nifi-mcp-modernise/.venv/bin/python -m pytest -q` — **9 passed in 2.34s**, exit 0.
- Command: `PYTHONPATH=src /tmp/nifi-mcp-modernise/.venv/bin/python -m compileall -q src tests scripts` — exit 0.
- Command: `git diff --check` — exit 0.
- Command: `/tmp/nifi-mcp-modernise/.venv/bin/python -m pip check` — “No broken requirements found”, exit 0.
- Command: `PYTHONPATH=src /tmp/nifi-mcp-modernise/.venv/bin/python scripts/smoke_mcp.py` — exit 0; protocol `2025-11-25`, server `nifi-mcp-server 1.30.0`, 35 tools; required version/root-group/processors/health tools found.
- The smoke output explicitly states: **“NiFi API connectivity: NOT TESTED by this smoke test.”** These checks establish code quality and protocol/tool discovery only.

### Fresh private-service and target discovery

- Cloudflare tunnel inventory reports `mcp-bridge` with no active connection.
- The active `t4h-mac` tunnel configuration maps `mac.tech4humanity.com.au` to `http://127.0.0.1:8787`; it does not declare the MCP hostname. No local listener was present on ports 8787, 3000, 8000 or 8443 during the check.
- Public unauthenticated probe of `https://mcp.tech4humanity.com.au/mcp` returned HTTP 401. The root path timed out and `/health` returned 404. A 401 is not proof that the origin is healthy or that an authenticated MCP request succeeds.
- No authorised live NiFi API URL or authentication method was found in the scoped local configuration/repository search. The configured SSH alias `ec2` timed out on port 22.
- AWS CLI identity is available. Initial ap-southeast-2 checks found no NiFi/MCP-named SSM parameters or Secrets Manager entries. A cross-region EC2 scan produced no positive running-instance rows, but per-region errors were suppressed; do not treat that as definitive proof of global absence.
- GCP Compute Engine discovery for project `mcp-bridge-478002` returned a billing-disabled error. No billing change was made; enabling billing requires explicit cost authorisation.
- No secret values were printed or committed. No tunnel routing was changed, no unauthenticated listener was exposed, and no NiFi operation was invoked.

### Six-step acceptance register

| Gate | State | Closure evidence required |
|---|---|---|
| Restore private Cloudflare path | **BLOCKED** | Correct origin host/port and tunnel mapping; active tunnel; Access and origin auth intact; authenticated MCP initialize/tool call succeeds |
| Establish real NiFi target/auth | **BLOCKED** | Authorised NiFi API URL, approved auth method and permitted network path; secrets remain server-side |
| Intended AI-client live reads | **BLOCKED** | Actual version, root process group, processors and flow-health responses from live NiFi |
| Independent comparison/security negatives | **BLOCKED** | Timestamped comparison with NiFi UI/direct API plus auth-denial, unreachable-target, redaction, GET retry and partial-health results |
| Safe non-production mutation | **NOT RUN — AUTHORISATION REQUIRED** | Explicit target/action approval; reversible operation; independent read-back and cleanup, or formally recorded exclusion |
| Remote deployment and rollback | **BLOCKED** | Private authenticated endpoint, verified client calls, TLS/network/access evidence and tested rollback |

### Audit disposition

**PARTIAL — NOT ACCEPTED — NOT PRODUCTION-READY.** The code hardening and local MCP protocol checks are verified at the scope stated above. End-to-end acceptance depends on an authorised NiFi target/authentication configuration and the correct private Cloudflare origin/tunnel mapping. A demo, HTTP 401, local handshake, or unit test cannot substitute for those missing acceptance results.

### Continued discovery — 2026-10-28 21:38 +11:00

- Local credential metadata exists for the `mcp-bridge` Cloudflare tunnel, but Cloudflare reports no active connector. No local service listens on ports 8787, 3000, 3030, 8000 or 8443. The local `t4h-mac` tunnel config routes only `mac.tech4humanity.com.au` to port 8787; it is not safe to repurpose it for MCP without an approved routing design.
- Other Cloudflare tunnels are active, but their presence alone does not prove they route this hostname or can reach NiFi.
- The local governed-MCP environment file has Supabase configuration only; no NiFi/Knox host or auth settings were found there.
- GCP project `mcp-bridge-478002` returned no Compute Engine instance rows; its Secret Manager API is disabled, and Cloud Run API was not enabled in the checked MCP Bridge project. No APIs or billing were enabled, and no resources were created. Another active project, `gen-lang-client-0427780391`, did not yield a confirmed NiFi runtime. These checks do not prove no NiFi exists elsewhere.
- A broad all-region AWS EC2 scan was stopped after high latency and is explicitly incomplete. Targeted AWS region checks returned no instance rows; the configured SSH alias timed out. No secrets were read or logged.

**Execution boundary remains:** do not start a dead MCP listener or route the hostname to an unconfigured origin merely to make the tunnel show as connected. The next safe action requires locating the authorised NiFi API host and approved auth/network path, then configuring the correct private origin/tunnel route. No live NiFi call or mutation has been claimed.


## Local NiFi API simulator and MCP safety harness — 2026-10-30

### Implemented

- Added tests/nifi_api_simulator.py, a deterministic HTTP test double for a small NiFi REST API subset. It binds to loopback by default, can optionally require a simulator-only bearer token, can queue selected HTTP failures, and can delay POST responses to model an ambiguous timeout. It does not run a NiFi engine or execute flows.
- Added tests/test_nifi_api_simulator.py with HTTP contract tests and a real MCP stdio client/server round-trip pointed at the simulator.
- Documented simulator usage, safety boundaries, and the difference between simulation and live acceptance in README.md.

### Verification on the connected Mac

- PYTHONPATH=src /tmp/nifi-mcp-modernise/.venv/bin/python -m pytest -q: **16 passed in 4.27s** (includes the existing hardening tests plus simulator and MCP end-to-end tests).
- PYTHONPATH=src .../python -m compileall -q src tests scripts: passed.
- git diff --check: passed.
- .../python -m pip check: **No broken requirements found**.
- PYTHONPATH=src .../python scripts/smoke_mcp.py: passed; MCP protocol 2025-11-25, server nifi-mcp-server 1.30.0, 35 tools, all required read tools discovered. This smoke test itself uses an intentionally unreachable target and does not test NiFi API connectivity.
- Started the simulator manually on 127.0.0.1:18787, retrieved the fixture /flow/about response with curl, and terminated the temporary process after the check.

### Safety cases exercised

- HTTP reads for version, root process group, processors, connections, controller services and bulletins.
- MCP stdio tool discovery and successful calls to get_nifi_version, get_root_process_group, list_processors, and get_flow_health_status against the simulator.
- Read-only MCP tool registration: write tool start_processor is absent, and the exercised read-only call sequence produced no POST/PUT/DELETE requests.
- Missing bearer token denied with HTTP 401.
- Simulated HTTP 503 on a read recovers on retry; HTTP 400 is not retried.
- Simulated POST response timeout after the simulator has recorded the request results in exactly one POST attempt (no automatic mutation retry).

### Scope and disposition

**Simulator/harness verified; live integration remains BLOCKED / NOT ACCEPTED / NOT PRODUCTION-READY.** These are controlled test fixtures, not a real Apache NiFi cluster. The harness cannot prove NiFi-version-specific schema compatibility, Cloudera authentication/network reachability, actual flow execution, real NiFi authorisation, or end-to-end production safety. No cloud resource was provisioned, no public listener/tunnel was opened, no real credentials were used, and no live NiFi mutation was attempted. The Cloudera 60-day trial remains the real-server acceptance target.


---

## Final demonstration handover — 2026-10-31

**Project disposition: CLOSED AT DEMONSTRATION SCOPE. NiFi is not an operational-system dependency.**

The owner clarified that Apache NiFi is needed only for a demonstration. This supersedes earlier plans to establish a live NiFi target, Cloudera trial, private hosted MCP endpoint, production integration or BAU support. No further NiFi infrastructure work is required.

### Demonstration artefacts retained

- Hardened MCP server source and configuration.
- Deterministic local REST API test double: `tests/nifi_api_simulator.py`.
- HTTP contract and MCP stdio integration harness: `tests/test_nifi_api_simulator.py`.
- Safe protocol smoke script: `scripts/smoke_mcp.py`.
- This receipt and `MODERNISATION-DECISION-RECORD.md`.
- Full operator-facing demo guide: `DEMO-GUIDE.md`.

### Verified result at published head

- Repository: `trojan-oz/NiFi-MCP-Server`
- Branch: `modernise/evidence-first-guardrails`
- Verified commit: `9cc75d3b5b9320a1e917ca56687e508493960a65`
- On the authorised Mac, 2026-10-30: `PYTHONPATH=src .../python -m pytest -q` — **16 passed in 4.27s**.
- `compileall -q src tests scripts`: passed.
- `git diff --check`: passed.
- `pip check`: no broken requirements found.
- Safe MCP protocol smoke: passed; protocol `2025-11-25`, server `nifi-mcp-server 1.30.0`, 35 tools discovered. This smoke intentionally uses an unreachable placeholder NiFi URL and does not test live NiFi connectivity.
- Manual loopback GET to `/nifi-api/flow/about` returned the simulator fixture. Temporary simulator process was stopped; a subsequent listener check found no listener.

### What the tests demonstrate

- HTTP contract handling for version, root process group, processors, connections, controller services and bulletins.
- MCP stdio round-trip invoking version, root group, processor list and flow-health tools against the simulator.
- Read-only tool registration and zero POST/PUT/DELETE requests during the read-only exercise.
- Simulator bearer-token denial when credentials are absent/wrong.
- Transient GET 503 retry/recovery and non-retry of GET 400.
- No automatic second POST when a delayed simulated mutation response times out after the server has recorded the request.

### What is not claimed

No live NiFi/Cloudera compatibility, live authentication, real NiFi data retrieval, independent comparison with a live NiFi UI/API, live mutation, remote deployment, production readiness, support/SLA or BAU operation is claimed. Simulator fixtures are synthetic and must always be labelled as simulated.

### Safety and cleanup boundary

No cloud resources were provisioned; no APIs or billing were enabled; no public listener or tunnel was opened; no real credentials were used; no live NiFi mutation was attempted. The demo fork and source artefacts are intentionally retained. The last local process/listener check found no simulator listener. A later cleanup recheck was unavailable because Desktop Commander monthly usage was exhausted; temporary test cache/environment deletion is not claimed. Do not delete the source checkout or preserved receipt/patch backups as part of temporary cleanup.

### Reactivation rule

Reopen only for a named demonstration requirement. Use a disposable local environment, loopback-only simulator, no production credentials, and explicit simulated-data labels. Any future live NiFi test is a separate scope requiring an authorised target and approval; it is not implied by this demonstration.

**Final statement: the MCP/NiFi demonstration artefacts are retained and documented; simulator/protocol scope is verified; live NiFi integration is not required and is not claimed.**
