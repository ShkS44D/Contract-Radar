# Architecture

The scanner is independent of Flask. Typed `Finding` and `ScanResult` dataclasses are the shared boundary for reports, storage, exports, and clients. Terminal failures cannot carry a score. Scanner configuration is explicit and environment-derived; no module enables debug mode.

`source.py` preserves offsets while masking comments and string literals. `compiler.py` resolves import closures and compatible stable compiler ranges from a bounded catalog (0.4.11 through 0.8.30). Independent roots can use different versions; conflicting imported pragmas fail. Missing pragmas are recorded as warnings. Installation uses a shared file lock and subprocess timeout; `SOLC_VERSION` is set per child, never globally.

`process.py` runs argument lists without a shell, monitors deadlines/output, and terminates child trees. `engine.py` orchestrates setup, Slither execution, strict JSON parsing, and metadata. Uploaded framework scripts are never run: Slither is forced to its Solidity compiler backend. Missing imports require supplied source files.

The whole scan has one deadline, including installation; the installation timeout is additionally capped. States are queued, running, completed, compile_error, timeout, and engine_error. Failed scans discard partial findings and remain unscored.

The worker compiles facts first, then runs Slither's native CLI with the same compiler. The CLI omits detectors for successful zero-finding scans; only this validated success shape is normalized. Missing/failed reports, nonzero exits, malformed shapes, and projects with no analyzable declarations remain failures. Two compilation passes per unit are a current performance limitation.

Initial verification: range/import/masking tests, malformed/missing reports, secret filtering, real subprocess deadlines/output limits, and mocked success/failure states. Real Slither integration is checked separately against installed compiler versions.

## Application boundaries

The app factory registers browser and API blueprints. Upload preparation produces a UUID source directory and random physical filename for single uploads. The engine restores the logical filename before fingerprinting, making source identity stable across scans. UTF-8 text is normalized to LF to preserve compiler/source line agreement on Windows.

The bounded thread pool admits at most workers + queue_size jobs. Each job runs the scanner subprocess group and cleans its source directory on completion or failure. SQLite stores JSON-serialized normalized results atomically, preserves original expiry during updates, and marks interrupted jobs as engine_error on startup. Deployment is intentionally single-process; multiple independent app pools against the same database are unsupported.

Browser POST redirects with 303 to `/report/<uuid>`. The report route selects loading/error/completed templates. Polling uses the API state; no estimated percentage is invented. Report exports and CLI use shared serialization/export services. All source in HTML is Jinja-escaped and Markdown export escapes HTML. SARIF carries executionSuccessful=false for failed scans. PDF uses ReportLab's controlled paginated layout.

Terminal results are persisted after cleanup; cleanup failures become unscored engine_error reports. A submission timestamp preserves retention if a job outlives its database row. Compiler cache follows the activated environment/home directory and can be overridden with SOLC_SELECT_DIR (a directory named `.solc-select`).
