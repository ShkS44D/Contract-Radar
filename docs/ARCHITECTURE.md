# Architecture

The scanner is independent of Flask. Typed `Finding` and `ScanResult` dataclasses are the shared boundary for reports, storage, exports, and clients. Terminal failures cannot carry a score. Scanner configuration is explicit and environment-derived; no module enables debug mode.

`source.py` preserves offsets while masking comments and string literals. `compiler.py` resolves import closures and compatible stable compiler ranges from a bounded catalog (0.4.11 through 0.8.30). Independent roots can use different versions; conflicting imported pragmas fail. Missing pragmas are recorded as warnings. Installation uses a shared file lock and subprocess timeout; `SOLC_VERSION` is set per child, never globally.

`process.py` runs argument lists without a shell, monitors deadlines/output, and terminates child trees. `engine.py` orchestrates setup, Slither execution, strict JSON parsing, and metadata. Uploaded framework scripts are never run: Slither is forced to its Solidity compiler backend. Missing imports require supplied source files.

The whole scan has one deadline, including installation; the installation timeout is additionally capped. States are queued, running, completed, compile_error, timeout, and engine_error. Failed scans discard partial findings and remain unscored.

Initial verification: range/import/masking tests, malformed/missing reports, secret filtering, real subprocess deadlines/output limits, and mocked success/failure states. Real Slither integration is checked separately against installed compiler versions.
