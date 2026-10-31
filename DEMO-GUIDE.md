# NiFi MCP Server — demonstration guide and handover

**Status:** Demonstration-only artefact; project closed 2026-10-31  
**Owner decision:** NiFi is not needed by the operational system. It is retained only for a demonstration.  
**Repository:** https://github.com/trojan-oz/NiFi-MCP-Server  
**Branch:** `modernise/evidence-first-guardrails`  
**Verified demo commit:** `9cc75d3b5b9320a1e917ca56687e508493960a65`

## 1. Purpose

This repository demonstrates how an AI client can discover and call MCP tools shaped around Apache NiFi concepts, and how safety controls can be tested without connecting to a real NiFi deployment.

It is not an operational integration, a production service, or a requirement for any T4H system. The local simulator supplies deterministic HTTP fixtures for repeatable tests. It does not execute dataflows or emulate the NiFi engine.

## 2. Components and responsibilities

| Component | Role | Boundary |
|---|---|---|
| NiFi MCP server | Exposes NiFi-oriented tools over MCP | Tool interface only; requires a configured NiFi API for real use |
| NiFi API client | Handles HTTP calls, auth, errors and retry policy | Live NiFi connectivity was not tested in the final demo |
| Local API simulator | Returns deterministic fixture responses on loopback | Test double; not NiFi and not production evidence |
| Contract/safety tests | Exercise HTTP and MCP calls against simulator | Prove only the tested simulator contract and code paths |
| MCP smoke script | Checks protocol initialization and tool discovery | Uses an unreachable placeholder API; does not call NiFi |

## 3. Safety properties demonstrated

- Read-only is the default for the tested smoke/harness path.
- Read-only MCP tool listing excludes mutation tools.
- The tested read-only sequence makes no POST, PUT or DELETE requests.
- A simulator-only bearer-token check rejects missing/incorrect credentials.
- Transient GET failure handling retries and recovers in the simulated case.
- A non-retryable GET 400 is not retried.
- A timed-out POST is not automatically repeated, avoiding duplicate mutation risk when the server may already have applied the request.
- Secret redaction, explicit version-detection failure, incomplete-health reporting and mutation allowlist enforcement have regression coverage in the broader test suite.

These are code/test observations, not a substitute for NiFi's own authentication, authorisation or operational controls.

## 4. Reproduce the local demonstration

Requirements: Python 3.10+ (use the version declared by the project metadata), Git, and a local shell. Docker, a Cloudera account, cloud services and real NiFi credentials are not required.

```bash
git clone https://github.com/trojan-oz/NiFi-MCP-Server.git
cd NiFi-MCP-Server
git checkout modernise/evidence-first-guardrails
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'
PYTHONPATH=src python -m pytest -q
PYTHONPATH=src python -m compileall -q src tests scripts
python -m pip check
git diff --check
```

Expected historical result at the recorded verification commit: **16 tests passed**. The exact runtime and dependency versions can affect future reruns; record the current commit and output rather than assuming the historical result applies to a changed checkout.

### Optional manual simulator inspection

Run only on loopback:

```bash
python tests/nifi_api_simulator.py --host 127.0.0.1 --port 18787
```

In another terminal:

```bash
curl -sS http://127.0.0.1:18787/nifi-api/flow/about
```

Stop the simulator with Ctrl-C. Confirm the listener is gone before finishing. Do not bind to `0.0.0.0`, expose it through a tunnel, or place real credentials in the simulator. The optional simulator token is for local test coverage only.

### Protocol discovery smoke

```bash
PYTHONPATH=src python scripts/smoke_mcp.py
```

This deliberately configures an unreachable placeholder NiFi API URL, forces read-only mode and removes inherited NiFi/Knox credentials. It checks MCP initialization and tool discovery, not NiFi connectivity.

## 5. Recorded verification evidence

At commit `9cc75d3b5b9320a1e917ca56687e508493960a65`, the authorised Mac run on 2026-10-30 recorded:

| Check | Result |
|---|---|
| `pytest -q` | 16 passed in 4.27s |
| `compileall -q src tests scripts` | Passed |
| `git diff --check` | Passed |
| `pip check` | No broken requirements |
| Safe MCP protocol smoke | Passed; 35 tools discovered |
| Manual simulator GET | Fixture response returned |
| Simulator process/listener | Stopped; subsequent listener check found none |

The MCP stdio harness called version, root process group, processor-list and flow-health tools against the simulator. Tests also covered authentication denial, retry policy and no automatic retry of a timed-out POST.

## 6. Explicit non-results

The following were not done and must not be represented as completed:

- No real NiFi or Cloudera cluster was contacted.
- No authenticated live NiFi read or independent comparison with NiFi UI/API was performed.
- No live mutation was attempted.
- No Cloudera trial or cloud resource was provisioned.
- No cloud API or billing was enabled.
- No remote MCP endpoint, Cloudflare tunnel or public listener was created.
- No production release, SLA, on-call rotation or BAU support arrangement exists.

## 7. Cleanup

For a temporary local run:

1. Stop the simulator and any local MCP process started for the demo.
2. Check that the simulator port is no longer listening (for example, `lsof -nP -iTCP:18787 -sTCP:LISTEN` on macOS).
3. Remove only the disposable virtual environment and test caches created for that run, after checking the paths. Do not remove the repository, source branch, test fixtures, receipt, decision record or backup artefacts.
4. Do not remove shared tunnels, credentials, cloud projects or general-purpose infrastructure; this demo did not create any of those resources.

Historical cleanup note: the simulator process was stopped and a subsequent listener check found no listener on 2026-10-30. A fresh filesystem cleanup check could not be completed at project close because the connected Desktop Commander monthly usage limit had been reached. Deletion of any temporary test directory/cache is therefore not asserted.

## 8. Artefact inventory

- `src/`: MCP server implementation and NiFi API client.
- `tests/nifi_api_simulator.py`: deterministic loopback-only REST API test double.
- `tests/test_nifi_api_simulator.py`: simulator HTTP contract and MCP stdio harness.
- `scripts/smoke_mcp.py`: safe protocol/tool-discovery smoke.
- `MODERNISATION-RECEIPT.md`: chronological verification evidence and final close-out.
- `MODERNISATION-DECISION-RECORD.md`: historical rationale and superseding demo-only decision.
- `DEMO-GUIDE.md`: this operator handover.

The owned fork and branch are retained as the durable copy. Upstream Cloudera PR #3 was not merged; the attempt to close it through the connected GitHub integration returned 403, so it remains an external housekeeping item for an authorised PR maintainer. This does not affect the closed T4H demo scope.

## 9. Reactivation rule

Reopen only for a specific, approved demonstration requirement. Keep the simulator local and labelled as simulated. Any future live NiFi test is a separate scope with an authorised target, approved authentication/network route and explicit permission. Passing these simulator tests does not satisfy live integration acceptance.
