# 09 — Testing results

Environment: local Windows workspace, Python 3.13 and Node runtime. Tests used local mocks/fixtures. No production service/network/payment was contacted.

## Exact commands and results

| Command | Result |
|---|---|
| `python -m pytest -q` final working tree | **177 passed, 27 skipped, 0 failed**, 5 warnings, 14.57s. |
| `python -m pytest -q tests/test_daraja_client_logging.py` focused run | **1 passed, 0 failed, 0 skipped**, 1 third-party deprecation warning (also included in final full suite). |
| `node --test tests/*.test.js tests/*.test.mjs` | **14 passed, 0 failed, 0 skipped**. |
| `node --check` over JS under `admin`, `portal`, `hotspot`, root `js`, and `phase-j-relay-source` | **80 files passed syntax check**. |
| `python -m compileall -q app phase-j-relay-source` | Passed. |
| Relay-focused: `python -m pytest -q phase-j-relay-source/tests/test_attestation.py` | **27 passed, 0 failed, 0 skipped**. |
| Relay/FastAPI cross-component group from Phase J report | **68 passed, 0 failed, 0 skipped**. |

The final full suite includes the phone-mask regression. The 27 skipped suite tests are marked database-dependent; there was no local MongoDB service. Warnings include dependency deprecations (`pythonjsonlogger`, `mongomock`, Starlette). Do not count skipped tests as passes.

No actual HTML validator, browser responsive test, live Mongo, Render build/deployment, FreeRADIUS, RouterOS, Daraja, or load test was run. `git diff --check` is required after handover files are written and its result should be appended before release.
