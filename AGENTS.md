# AGENTS.md

CLI assistant that parses bank statements (Nexi XLSX, Revolut CSV) and imports the
transactions into Firefly III through its REST API.

## Setup and run

```bash
uv sync
cp config/config.yaml.example config/config.yaml   # then fill url and token
.venv/bin/python main.py
```

Python 3.13. There is no test suite and no formatter or linter configured: ask before
introducing one.

`config/config.yaml`, `constants.py` and `scripts/` are gitignored. `constants.py` is
dead code holding an expired token, nothing imports it.

## Layout

| Path | Role |
| --- | --- |
| `main.py` | Rich CLI, menu with parse/create/recurrence/duplicates/missing/update |
| `config/settings.py` | Dataclasses loaded from `config.yaml` |
| `src/firefly/client.py` | API wrapper; `_get` follows pagination, plus `_post`/`_put` |
| `src/firefly/models.py` | `Transaction`, payload building, JSON round-trip |
| `src/parsers/base.py` | `BaseParser`, amount classification, auto-categorization |
| `src/parsers/nexi.py` | Nexi XLSX parser |
| `src/parsers/revolut.py` | Revolut CSV parser |
| `src/parsers/types.py` | Enums and per-card behaviors |
| `data/inputs` | Statements to parse |
| `data/outputs` | Parsed JSON, reviewed before import |

## Import flow

Parsing and creation are two separate steps on purpose. `parse` writes JSON to
`data/outputs`, which is then reviewed and edited by hand before `create` sends it to
Firefly. Descriptions are left empty by the parsers and must be filled in: `create`
skips any transaction without one.

## Transaction identity

This is the part to understand before touching the parsers.

`external_id` is the deduplication key. Before creating anything, the importer asks
Firefly whether that id already exists.

- **Nexi**: the `Riferimento` column (column D) is used as `external_id`. It is the
  payment circuit reference, stable across exports and unique per transaction.
- **Revolut**: the CSV carries no reference, so the id is a hash.
- **Hash fallback**: `Transaction.generate_id()` returns
  `sha256(date|merchant|amount)[:12]`, used whenever no reference is available
  (`Transaction.__init__` applies it when `id` is None).

`FireflyClient.transaction_exists(external_id, *fallback_ids)` tries the ids in order
and stops at the first hit. The parsers pass the hash as fallback so that transactions
imported before the switch to the reference, which carry a hash-based `external_id`,
are still recognized instead of being imported twice. Nothing rewrites those old ids;
they keep the hash.

`skip_states` (per card, in `config.yaml`) lists statement states to ignore entirely.
It is set to `Non Contabilizzato` on the Nexi cards and it is load-bearing, not a
safety net: an unsettled row has a provisional date and amount and no reference yet,
so importing it means storing a hash that no longer matches once the row settles,
which produces a duplicate.

Known limitation: the hash cannot tell apart two transactions with the same date,
merchant and amount. Where it is used as the identity (Revolut, references missing,
legacy fallback) a genuine second transaction can be skipped as already imported.

## Firefly III notes

- `external_id` is not editable in the transaction form and is not among the optional
  fields in Preferences; it only shows read-only on the transaction detail page. It is
  writable through the API. `internal_reference` instead can be switched on under
  Options > Preferences.
- Useful search operators: `external_id:"..."`, `date_on:YYYY-MM-DD`.
- `PUT /transactions/{id}` applies partial updates: pass `transaction_journal_id` plus
  only the fields to change. Rebuilding the whole split instead drops anything left
  out, which is what `FireflyClient.update_external_id` currently does: it loses
  category, tags and notes.

## Gotchas

- Empty `completed_states` and empty `skip_states` behave in opposite ways: Revolut
  skips every row when its allowlist is empty, while an empty `skip_states` skips
  nothing. Adding a Revolut-style card without `completed_states` silently imports
  zero transactions.
- Account aliases live in the account `notes` field as JSON,
  `{"aliases": ["RAW NAME", ...]}`, and map raw statement names to canonical accounts.
- `FireflyClient.__init__` preloads every asset, expense and revenue account to build
  the alias map, which is several paginated calls. Standalone scripts that only need
  one endpoint are better off talking to the API directly.

## Conventions

- Code, comments, docstrings and commit messages in English.
- Conventional commits, unscoped (`fix:`, not `fix(parser):`).
- Documentation lines wrapped at 88 characters.
