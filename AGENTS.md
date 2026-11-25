# Agent guide: `pycalista-ista`

Audit date: 2026-11-24. Original audited revision: `a62c3fe`. Release history: 0.9.3 bugfix, 0.10.0 minor.
This guide describes the audited code and the subsequent 0.10.0 implementation. The original audit was read-only; section 18 records the implemented changes.

Read this guide before changing the package. Read `../ista-calista/AGENTS.md` before changing the Home Assistant consumer. The two repositories form one system but release independently.

## 1. Safety rules

1. **Keep credentials, cookies, property IDs, and property labels out of logs.** Version 0.10.0 masks sensitive query/form values, logs cookie names only, omits selector pages, and redacts sensitive pairs in response snippets. Preserve the redaction tests in `tests/test_logging_redaction.py` when changing any log path.
2. Never commit real credentials, cookies, account exports, invoice PDFs, serial numbers, or locations. Tests use synthetic data and mocked HTTP.
3. Do not call the live portal from tests. Use `aioresponses` and the existing login helper.
4. Construct `PyCalistaIsta` or `VirtualApi` **inside a running event loop** when no session is supplied. Current constructors create `aiohttp.ClientSession` immediately and raise `RuntimeError` outside a loop.
5. If a caller supplies a `ClientSession`, the caller owns it. `close()` does not close an injected session.
6. Preserve UTC handling. Naive `Reading` dates are interpreted as UTC. Portal date-only radio readings become UTC midnight.
7. Preserve old and new billed-consumption header support. The October 2026 portal rename is issue `herruzo99/ista-calista#4`.
8. Run the full suite and all three style checks before proposing a push. The style checks are currently red on pre-existing files; see §12.

## 2. What this package is

`pycalista-ista` is an asynchronous Python scraper for the Ista Calista customer portal. It is not a documented public REST API client. It depends on portal HTML forms, redirects, cookie names, endpoint parameters, Spanish XLS headers, and export-link markup.

Current package version: **0.10.0**, not published by this audit. Python requirement: `>=3.12`. Runtime dependencies: pandas, xlrd, openpyxl, unidecode, aiohttp, yarl, beautifulsoup4.

The package provides:

- Keycloak form login and automatic relogin.
- Radio meter history as XLS/XLSX.
- Billed consumption (`Mis Consumos`) as XLS.
- Invoice listing as HTML and invoice history as XLS.
- Invoice PDF download.
- In-memory device, reading, invoice, and billed-reading models.

No database, filesystem cache, background scheduler, rate limiter, or durable session exists.

## 3. Architecture

```text
PyCalistaIsta                 public facade: defaults, validation, error mapping
  └── VirtualApi              HTTP, Keycloak, endpoints, retries, chunking, merging
        ├── ExcelParser       radio XLS/XLSX -> Device + Reading
        ├── ConsumptionParser billed XLS -> BilledReading
        ├── InvoiceXlsParser  invoice XLS -> Invoice
        └── InvoiceParser     invoice HTML -> Invoice

models/
  Device
  ├── WaterDevice
  │     ├── ColdWaterDevice
  │     └── HotWaterDevice
  └── HeatingDevice
  Reading, Invoice, BilledReading
```

Imports flow in one direction: models ← parsers ← `virtual_api` ← `pycalista_ista` ← package `__init__`. `const.py` is shared. There is no import cycle.

`virtual_api.py` is about 1,346 lines and contains most behavior. `pycalista_ista.py` is a thin facade. A change that looks small in the facade can still alter authentication or retry behavior below it.

## 4. File map

| Path | Responsibility |
|---|---|
| `pycalista_ista/__init__.py` | Public exports and `VERSION` alias |
| `pycalista_ista/pycalista_ista.py` | `PyCalistaIsta` facade |
| `pycalista_ista/virtual_api.py` | Session, auth, HTTP, endpoint discovery, data orchestration |
| `pycalista_ista/const.py` | URLs, limits, device/incidence constants, version import |
| `pycalista_ista/excel_parser.py` | Radio-reading workbook parser |
| `pycalista_ista/consumption_parser.py` | Billed-consumption workbook parser |
| `pycalista_ista/invoice_xls_parser.py` | Invoice workbook parser |
| `pycalista_ista/invoice_parser.py` | Invoice listing HTML parser |
| `pycalista_ista/exception_classes.py` | Four exception types |
| `pycalista_ista/models/device.py` | Base device and sorted history |
| `pycalista_ista/models/reading.py` | Immutable timestamped reading and subtraction |
| `pycalista_ista/models/{water,hot_water,cold_water,heating}_device.py` | Device subclasses |
| `pycalista_ista/models/invoice.py` | Immutable invoice record |
| `pycalista_ista/models/billed_reading.py` | Immutable billed-consumption record |
| `tests/conftest.py` | HTTP mocks, login chain, XLS fixture loader |
| `tests/test_virtual_api.py` | Auth, requests, chunking, interpolation, session lifecycle |
| `tests/test_pycalista_ista.py` | Facade validation and error mapping |
| `tests/test_parser.py` | Radio parser, real XLS fixtures, invoice XLS tests |
| `tests/test_consumption_parser.py` | Old/new/mixed billed headers and row errors |
| `tests/test_{device,reading,water_device,heating_device}.py` | Model behavior |

## 5. Public API

Package exports in `__all__`:

- `PyCalistaIsta`, `VERSION`
- `Device`, `WaterDevice`, `HotWaterDevice`, `ColdWaterDevice`, `HeatingDevice`, `Reading`
- `Invoice`, `BilledReading`, `INCIDENCE_NAMES`
- `IstaApiError`, `IstaConnectionError`, `IstaLoginError`, `IstaParserError`

Parsers and `VirtualApi` are importable from their modules but are not public package exports.

### `PyCalistaIsta`

```python
client = PyCalistaIsta(email, password, session=None)
```

- `email` is stripped; `password` is not stripped.
- Empty email or password raises `ValueError`.
- `login()` is async and returns `True` or raises.
- `get_devices_history(start=None, end=None)` is async. Defaults: today minus 30 days through today. `start > end` raises `ValueError`.
- `get_billed_consumption()` is async and returns `list[BilledReading]`.
- `get_invoices()` is async and returns HTML-derived `list[Invoice]`.
- `get_invoice_xls()` is async and returns XLS-derived `list[Invoice]`.
- `get_invoice_pdf(invoice_id)` is async and returns PDF bytes.
- `close()` is async. Use `async with PyCalistaIsta(...) as client` for owned-session cleanup.
- `set_log_level(level)` and `get_version()` are synchronous.

There is no public `logout()`. `VirtualApi.logout()` exists, but the facade does not expose it and no package code calls it.

### Exceptions

```text
IstaApiError
├── IstaConnectionError
├── IstaLoginError
└── IstaParserError
```

Every library exception derives from `IstaApiError`. Catch the specific type first when behavior matters. A parser error is also an API error. Current HTTP handling maps non-retryable 4xx/5xx responses to `IstaConnectionError`, so callers cannot distinguish a changed URL from a portal outage.

## 6. Authentication and session lifecycle

### Session ownership

- No supplied session: library creates a session with its User-Agent and a 30-second total timeout. Library owns and closes it.
- Supplied session: library uses the caller's timeout, headers, and cookie jar. Library does not close it.
- One `asyncio.Lock` per `VirtualApi` serializes `login()` calls.
- `relogin()` clears cookies for `oficina.ista.es`, `login.ista.com`, and `acceso.ista.es`, then calls `login()`.

Multiple clients sharing one session also share cookies. The Home Assistant integration currently does this. Concurrent relogins can replace each other's cookies; this is a code-level risk, not a reproduced live-portal failure.

### Login sequence

1. Discover the Keycloak form from the authorization URL.
2. Parse the first POST form, including hidden inputs and button/select values.
3. Submit username and password. `aiohttp` follows the callback and portal redirects.
4. If the final host is Keycloak, extract its error and raise `IstaLoginError`.
5. GET `preCargaLecturasRadio` as a preload step. Its body is not validated.

Keycloak constants are in `const.py`: realm `GESCON-PORTAL-ES-APP-Abonado`, client `abonado-service`, callback under `acceso.ista.es`. The OAuth `state` value is a static portal URL, not a random nonce.

### Expiry and relogin

`_send_request` treats HTTP 200 from `login.ista.com` as an expired session. It relogs in and retries once with `relogin=False`. It also relogs in after certain network errors mentioning `gescon.ista.net`.

Important limitation: after that one retry, another HTTP 200 login page can be accepted as success. Radio history has an extra HTML guard; invoice and preload paths do not consistently validate the final page.

## 7. HTTP behavior

Constants: 2 retries, 2-second backoff base, 30-second total request timeout, retry statuses 408/429/502/503/504.

- Retryable status: waits 2 seconds, then 4 seconds with default settings.
- Network error/timeout: retries with a duplicated backoff formula.
- `Retry-After` is ignored.
- Bodies are read as text before status checking, including XLS bytes. This increases memory use and can obscure binary failures.
- Worst-case time for one request is roughly 96 seconds, before parsing.
- Billed consumption is fetched with GET preload, POST search, HTML export-link discovery, then GET XLS.
- Export URLs are scraped from anchors containing `6578706f7274` (hex for `export`) or `d-<number>-e=<number>`. The code forces `e=2` and uses the first match.
- Relative export links are resolved against a hardcoded portal origin.

Do not assume the coordinator's four concurrent library calls finish within 30 seconds. Each call can perform several requests and retries.

## 8. Parsers and data contracts

### 8.1 Radio history: `ExcelParser`

Engine: `PK` magic means openpyxl/XLSX; otherwise xlrd/XLS.

Header pipeline: trim, remove `°`/`º`, spaces to underscores, remove `n_`, lowercase, remove accents. Required metadata: `tipo`, `n_serie`, `ubicacion`. Optional metadata: `unidad_medida`. Every other header must be a `dd/mm/yy` date and becomes `dd/mm/yyyy`.

Known defect: lowercase `nº serie` becomes `nserie`, because `n_` removal occurs before lowercase. Current fixtures use `Nº Serie` and work.

Rows map by device-type substring:

- `distribuidor de costes de calefaccion` → `HeatingDevice`
- `radio agua caliente` → `HotWaterDevice`
- `radio agua fria` → `ColdWaterDevice`

Unknown type or empty serial/type skips the row. Reading values replace decimal comma with dot. Bad values become `None`; negative values skip that reading. Duplicate serials in one workbook merge. Dates are UTC midnight.

Real fixtures contain 11 devices, newest date column first, text values such as `4,956`, and numeric serials. If a serial column becomes floating point because of empty cells, `str()` can produce `141740872.0`; this is unverified but possible.

### 8.2 Billed consumption: `ConsumptionParser`

Required normalized columns:

```text
nº serie, tipo equipo, fecha, lectura anterior, lectura actual, consumo
```

Optional: `ubicación`, `id lectura`, `incidencia`, `unidad medida`.

Accepted aliases, added in `ff3458e`:

```text
lectura anterior facturada -> lectura anterior
lectura facturada           -> lectura actual
```

An alias is applied only when the canonical column is absent. A workbook containing both keeps the canonical column. This is the fix for `ista-calista#4`; keep the mixed-header test.

Rows with serial `_` are skipped. Dates are UTC `date` values. Numeric fields currently use `float(value or 0)`.

Known defects:

- Empty numeric cells produce `NaN`, because `NaN` is truthy.
- Decimal-comma strings such as `120,5` cause the whole row to be skipped.
- Output remains workbook order despite a docstring that says descending date order.
- pandas parsing runs on the event loop in `get_billed_consumption`.

No real billed-consumption XLS fixture is committed. Current tests build synthetic workbooks with xlwt.

### 8.3 Invoice XLS: `InvoiceXlsParser`

Required: `fecha lectura`, `importe`. Optional: `tipo equipo`.

Amount removes `€`, replaces comma with dot, and maps NaN to `None`. `invoice_id` is always `None`. Some docstrings incorrectly say `""`. Bad rows are skipped. Parsing runs in an executor.

### 8.4 Invoice HTML: `InvoiceParser`

Finds anchors with `idRecibo=<opaque value>`, requires a parent table row, and deduplicates repeated links in the row. It recognizes `dd/mm/yyyy` dates and amounts such as `80,12 €`. The first other cell becomes `device_type`.

`invoice_number`, `period_start`, and `period_end` are never populated. Missing amount still returns an invoice. No links returns `[]` with a warning, not an exception.

This parser has no direct tests and only 19% coverage. Change it only with new HTML fixtures and tests.

### 8.5 Parser comparison

| Parser | File rejected on bad schema | Bad rows | Execution |
|---|---|---|---|
| Radio XLS/XLSX | Yes | Logged and skipped | Executor |
| Billed XLS | Yes | Warning and skipped | Event loop |
| Invoice XLS | Yes | Warning and skipped | Executor |
| Invoice HTML | No links → empty list | N/A | Event loop |

## 9. Models and invariants

### `Reading`

Frozen dataclass: `date: datetime`, `reading: float | None`.

- Negative values raise `ValueError`.
- Naive dates get UTC.
- Subtraction returns `None` if either value is `None`; otherwise it may return a negative difference.
- Sorted by date.

### `Device`

- Empty serial raises `ValueError`; `location=None` becomes `""`.
- `history` is sorted by date.
- Duplicate dates are silently ignored by `add_reading`.
- `last_reading` returns the final element or `None`.
- `last_consumption` subtracts the final two readings and wraps the result in a new `Reading`.
- **A meter reset currently raises `ValueError`** because the negative result is rejected. Reproduced with 110 followed by 5.
- Equality and hashing use only the serial, even across subclasses. The first device class seen wins a merge.
- Duplicate checking is a linear scan, so large history insertion is O(n²).

### Subclasses

`WaterDevice` is the base of `ColdWaterDevice` and `HotWaterDevice`. `HeatingDevice` derives directly from `Device`. Subclasses add no behavior beyond construction and representation.

### `Invoice`

Frozen dataclass. Every field is optional:

```text
invoice_id, invoice_number, invoice_date,
period_start, period_end, amount, device_type
```

HTML supplies `invoice_id`, date, amount, and usually type. XLS supplies date, amount, and optional type, with `invoice_id=None`. Current parsers do not fill invoice number or period.

### `BilledReading`

Frozen dataclass with required serial, type, location, reading ID, date, incidence, unit, previous/current reading, and consumption. `is_estimated` means incidence `47A4`. Incidence names are `4700`, `47A4`, `47AA`, and `4741`.

## 10. Chunking, merging, and interpolation

Radio requests cover at most 239 days in practice. `_get_readings` builds chunks of `max_days - 1` days and fetches them sequentially. It does not forward a custom `max_days` to `_get_readings_chunk`; values above 240 therefore conflict with the chunk validator.

Each chunk is parsed in an executor. Chunk results merge by serial and date. The first location and device subclass win.

Interpolation:

1. Copy valid nonnegative readings into a new device.
2. Trim leading and trailing `None` values.
3. Fill internal missing values linearly by elapsed seconds, rounded to four decimals.
4. Clamp interpolated values between the surrounding readings.
5. If the ending value is lower, fill internal gaps with zero to represent a reset.

The reset gap is filled, but the actual downward difference remains. This is why `last_consumption` can still crash.

## 11. Concurrency rules

- Network calls are async on one event loop.
- Login has a per-client lock; data methods do not.
- Radio chunk parses run concurrently in the default executor after sequential downloads.
- Invoice XLS parse uses the executor.
- Billed parse and invoice HTML parse run inline.
- `Device` mutation occurs on the event loop and is not protected if callers share a client across coroutines.

For new parsing code, follow the executor pattern unless profiling proves the work is trivial. For new shared state, define ownership and locking explicitly.

## 12. Development and verification

Run from the repository root:

```bash
nix develop --command pytest
nix develop --command pytest --no-cov -o addopts='' -q
nix develop --command pytest tests/test_consumption_parser.py
nix develop --command ruff check .
nix develop --command black --check .
nix develop --command isort --check .
```

Verified on 2026-11-24 at `a62c3fe`:

- Tests: **175 passed** in the final 0.10.0 tree, 4 pre-existing warnings. The original 0.9.3 baseline was 122 tests.
- Coverage: about **76%**. `invoice_parser.py` is 19%; the facade is 60%; `virtual_api.py` is 73%.
- Ruff: **fails**, 4 unused imports in `scripts/verify_expired_keycloak.py`.
- Black: **fails**, 4 pre-existing files.
- isort: **fails**, 3 pre-existing files.
- The same style failures exist at parent revision `23cb5ee`; the two local 0.9.3 commits did not cause them.
- Changed files `consumption_parser.py` and `test_consumption_parser.py` pass Ruff, Black, and isort.

The Nix shell omits openpyxl, even though XLSX is a supported runtime format. `import openpyxl` fails there. Add it before claiming XLSX test coverage. The shell currently provides Python 3.13.5 despite a Python 3.12 comment.

CI runs Python 3.12, Black, isort, pytest/coverage, and Codecov. It does not run Ruff or test 3.13/3.14. Publishing runs on GitHub release creation, not tag push, and uses OIDC for TestPyPI then PyPI.

Version sources are `pyproject.toml`, `pycalista_ista/__version.py`, and legacy `setup.py` reading the latter. They agree at 0.10.0. `pyproject.toml` wins during builds.

## 13. Known defects and risks

Labels: **V** = source-read or reproduced locally; **I** = inferred, not reproduced; **U** = depends on live portal or a newer Home Assistant.

| ID | Severity | Status | Finding |
|---|---|---|---|
| F1 | Security | Fixed in 0.10.0 | Request/form/query logging masks passwords and one-time tokens. Regression tests prove the password is absent. |
| F2 | Security | Fixed in 0.10.0 | Cookie values are never logged; only cookie names are shown. |
| F3 | High | V | `Device.last_consumption` raises after a meter reset. |
| F4 | Data | V | Empty billed numeric cells become `NaN`. |
| F5 | Data | V | Decimal-comma billed values drop whole rows. Latent with current numeric portal cells. |
| F6 | API | V | Constructing a client without a session requires a running event loop. |
| F7 | Compatibility | V | Lowercase `nº serie` normalizes to `nserie` and rejects the workbook. |
| F8 | Auth | I | A second HTTP 200 login page after the single relogin can be accepted. |
| F9 | API | I | `_get_readings(max_days>240)` conflicts with the fixed chunk validator. |
| F10 | Lifecycle | V | Public facade has no logout; changelog's automatic-logout claim is false. |
| F11 | Cleanup | V | Dead constants/parameters: `EXCEL_CONTENT_TYPE`, `current_year`, `_PERIOD_RE`. |
| F12 | Reliability | V | Retry backoff formulas are duplicated; `Retry-After` is ignored. |
| F13 | Performance | I | Billed pandas parse blocks the event loop. |
| F14 | Errors | V | All non-retryable HTTP statuses become `IstaConnectionError`. |
| F15 | Docs | V | Invoice XLS docstrings say `invoice_id=""`; code uses `None`. |
| F16 | CI | V | Repository-wide Black/isort/Ruff gates fail on pre-existing files. |
| F17 | Models | V | Device equality ignores subclass; conflicting types merge into the first class. |
| F18 | Performance | I | History insertion is O(n²). |
| F19 | Packaging/docs | V | Missing openpyxl in shell; absent `py.typed`; broken MkDocs nav and examples; no pre-commit config; missing 0.9.2 changelog entry. |
| F20 | Tests | V/I | Four asyncio warnings; year-default test can be flaky at New Year; unused `requests-mock`. |

Additional packaging facts:

- `entry_points.txt` is not included in the built wheel because setuptools dynamic entry points are not declared correctly.
- The built wheel contains the package modules but no `py.typed`.
- MkDocs navigation names files that do not exist.
- Several docs use sync calls in an async API, wrong exception names, `username=` instead of `email=`, and `requests`, which is not a dependency.
- Dependabot covers GitHub Actions only, not pip.

## 14. Test gaps

Add tests before changing these areas:

- `InvoiceParser` with real-shaped HTML, repeated links, missing amount, and no links.
- `get_invoices`, `get_invoice_pdf`, and the full `get_billed_consumption` network flow.
- Quoted-cookie repair and multi-domain cookie jars.
- Relogin that returns another login page.
- Meter reset through `Device.last_consumption`.
- Empty and decimal-comma billed cells.
- Client construction outside an event loop.
- Empty chunk result and custom `max_days`.
- XLSX parsing in the Nix shell.

No test opens a real socket. Login tests mock a six-step cross-domain redirect/cookie chain. Do not replace them with live-account tests.

## 15. Integration contract

`../ista-calista` calls, concurrently:

```python
login()
get_devices_history(start=date, end=date)
get_billed_consumption()
get_invoices()
get_invoice_xls()
```

It later calls `get_invoice_pdf(invoice_id)` and `close()`.

The integration injects a private Home Assistant-owned session per entry and per config-flow validation. Therefore library `close()` is intentionally a no-op for that session; the integration calls `detach()` for cleanup. The integration treats device-history failure as fatal but billing/invoice failure as non-fatal. A parser error in billed consumption therefore appears as empty billing data and a warning, not as entry failure.

Manifest constraint `pycalista-ista~=0.10.0` selects the new API. The integration dev shell prepends the sibling checkout to `PYTHONPATH`, so local integration tests use this work tree, not the older Nix-pinned package.

## 16. Safe change checklist

1. State whether the change affects auth, HTTP, parser schema, model semantics, packaging, or docs.
2. Add a failing regression test first for a defect.
3. Keep both billed-header spellings working.
4. Keep caller-owned sessions open.
5. Keep dates and timezone behavior explicit.
6. Mask credentials/cookies if touching request logging.
7. Run focused tests, then all 122 tests.
8. Run Ruff, Black, and isort on changed files; disclose existing repository-wide failures.
9. Update both version files and CHANGELOG for a release.
10. Check the Home Assistant consumer if a public signature, exception, or model changes.
11. Do not push, tag, or publish unless the owner explicitly asks.

## 18. Implementation update: 0.10.0

The original audit above remains a historical snapshot. Version 0.10.0 adds:

- Public frozen `PortalAccount(account_id, label)` model.
- `list_accounts()` and `select_account()`.
- Optional `account_id` constructor argument; login and relogin restore and verify the selected property.
- Per-client account-selection lock and per-task recursion guard.
- Full invoice-list pagination with ID deduplication, repeated-URL stop, and a 50-page cap.
- Credential, cookie, token, property-data, export-URL, and exception-text log redaction.
- Truthful `account_id` state: cleared on authentication, failed selection, logout, and close.

Release sequence: 0.9.3 fixes ista-calista#4; 0.10.0 is the minor feature release.

Multi-property behavior is **experimental**. Synthetic two-property tests pass. Only one real property was available for live validation. The live single-property switch and all 63 invoice IDs were verified. A multi-property page without an explicit selected option fails closed rather than guessing.

The final 0.10.0 tree passes 175 tests. The built wheel and sdist include `account_parser.py` and `models/portal_account.py`.

## 19. Limits of this audit

All production files, all test files, real radio XLS fixtures, packaging, workflows, docs, and scripts were read. Local tests and offline probes were run. No real Ista account was used. Live HTML, redirects, cookies, column spellings, and export URLs remain external contracts that can change without notice. See `../pycalista-audit.md` for the full evidence inventory, hashes, and detailed findings.
