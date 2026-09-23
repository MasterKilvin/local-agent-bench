# Public bug anchor provenance

Three tasks completed on 2026-09-22. This document, licences, scripts, source bundle and `.evidence/` belong to the outer collection, never to a task payload. Retain the supplied licence files with the collection when distributing it.

## Source retrieval and limits

This attempt used the host-fetched offline bundle described in [upstream/README.md](upstream/README.md); it made no network requests. URLs below identify origins, not fresh successful fetches. The earlier issue discovery notes are preserved in [prior-provenance.md](.evidence/prior-provenance.md). Full issue bodies for these three reports were not included in the bundle; the symptoms in those notes are corroborated by its changelogs and source changes. Tests were independently written from those reported symptoms with new neutral examples and boundary cases, not copied from upstream tests. The release diffs retain upstream tests only as evidence.

[Source SHA-256 hashes](.evidence/source-sha256.txt) identify the exact supplied bytes. Release tags identify source revisions but are not immutable hashes. For the pattern bugs, the bundle establishes the fixed release, not an individual fixing PR/SHA; the tagged commit and release diff are linked without inventing a precise fixing commit.

## append-setting

- Project: **python-dotenv**. Report: [issue #360](https://github.com/theskumar/python-dotenv/issues/360). Reproduction: appending an absent assignment to a file without a final newline joins it to the previous record. The new test uses `COLOR=blue` followed by `NEW=oak` and asserts two separate lines.
- Fix: [PR #361](https://github.com/theskumar/python-dotenv/pull/361), [PR diff endpoint](https://github.com/theskumar/python-dotenv/pull/361.diff). The PR-specific diff was not bundled; the [supplied release diff](upstream/dotenv-v0.19.1..v0.19.2.diff) contains the complete `src/dotenv/main.py` fix and a changelog attribution to #361. [Original comparison](https://github.com/theskumar/python-dotenv/compare/v0.19.1...v0.19.2).
- Pre-fix: [main.py v0.19.1](https://raw.githubusercontent.com/theskumar/python-dotenv/v0.19.1/src/dotenv/main.py), supplied as [dotenv-main-v0.19.1-prefix.py](upstream/dotenv-main-v0.19.1-prefix.py).
- Fixed: [main.py v0.19.2](https://raw.githubusercontent.com/theskumar/python-dotenv/v0.19.2/src/dotenv/main.py), supplied as [dotenv-main-v0.19.2-fixed.py](upstream/dotenv-main-v0.19.2-fixed.py).
- Dependency: [parser.py v0.19.2](https://raw.githubusercontent.com/theskumar/python-dotenv/v0.19.2/src/dotenv/parser.py), supplied as [dotenv-parser-v0.19.2.py](upstream/dotenv-parser-v0.19.2.py). The release diff has no parser change; both variants use this parser.
- Licence: **BSD-3-Clause**, including inherited notices, retained in [dotenv-LICENSE.txt](upstream/dotenv-LICENSE.txt). [Original licence](https://raw.githubusercontent.com/theskumar/python-dotenv/v0.19.2/LICENSE).
- Extraction: retain `with_warn_for_invalid_lines`, `rewrite`, `set_key`, their imports, logger and `_PathLike` compatibility branch; retain the parser's complete executable code. Omit unrelated loading, interpolation, unset/search APIs and unused imports. Both editor variants come directly from their corresponding supplied modules. The reference adds exactly the four statements in the upstream newline hunk.
- File renames: `src/dotenv/main.py` → `settings/editor.py` (selected definitions); `src/dotenv/parser.py` → `settings/records.py` (full executable module). Redirect the relative parser import. The package initializer, `main.py`, README and hidden test are newly authored scaffolding.
- [Focused upstream change](.evidence/append-setting-upstream.patch) is generated from the extracted definitions before renaming; formatting is normalized, so it is not a verbatim PR diff. [Renamed reference patch](.evidence/append-setting-reference.patch).
- Coverage: empty/terminated/unterminated files, comments, malformed records, multiline values, quoting, export prefix, duplicate-key updates, repeated appends, five value lengths and CLI success/failure. Exact preserved-text assertions reject unconditional newlines and whole-file normalization. Tests permit any implementation satisfying this behavior.

## disabled-rule

- Project: **python-pathspec**. Report: [issue #98](https://github.com/cpburnz/python-pathspec/issues/98). Reproduction: `RegexPattern(None)` raises `UnboundLocalError` because the compiled local is uninitialized. The renamed reproduction constructs `TextRule(None)` and also checks inert behavior and public state.
- Fix revision: [v1.0.0 tagged commit](https://github.com/cpburnz/python-pathspec/commit/v1.0.0), [release](https://github.com/cpburnz/python-pathspec/releases/tag/v1.0.0), [comparison](https://github.com/cpburnz/python-pathspec/compare/v0.12.1...v1.0.0). The [supplied diff](upstream/pathspec-v0.12.1..v1.0.0.diff) records #98 at line 271 and adds `regex = None` in `pathspec/pattern.py` at line 21522. An individual fixing commit is not established by this bundle.
- Pre-fix: [pattern.py v0.12.1](https://raw.githubusercontent.com/cpburnz/python-pathspec/v0.12.1/pathspec/pattern.py), supplied as [pathspec-pattern-v0.12.1-prefix.py](upstream/pathspec-pattern-v0.12.1-prefix.py).
- Fixed: [pattern.py v1.0.0](https://raw.githubusercontent.com/cpburnz/python-pathspec/v1.0.0/pathspec/pattern.py), supplied as [pathspec-pattern-v1.0.0-fixed.py](upstream/pathspec-pattern-v1.0.0-fixed.py).
- Licence: **MPL-2.0**, retained in [pathspec-LICENSE.txt](upstream/pathspec-LICENSE.txt), [original licence](https://raw.githubusercontent.com/cpburnz/python-pathspec/v1.0.0/LICENSE). The derived `routing/rules.py` remains covered source.
- Extraction: retain the full pre-fix module's executable definitions and standard-library imports, including its legacy iterator. Backport only the upstream `regex = None` assignment. Omit unrelated v1.0.0 typing/deprecation changes; the reference is the isolated upstream fix, not the entire new release module.
- File rename: `pathspec/pattern.py` → `routing/rules.py`. The package initializer, CLI, README and test are new scaffolding.
- [Focused upstream change](.evidence/disabled-rule-upstream.patch), [renamed reference patch](.evidence/disabled-rule-reference.patch).
- Coverage: positional/keyword None construction, public state, equality, text/bytes paths, mixed instance order, active text/bytes regexes, all compiled-rule decisions, an inert subclass, invalid arguments, CLI success/failure. None must not become an active empty regex. Tests do not mandate where or how the missing initialization is repaired.

## literal-leading-space

- Project: **python-pathspec**. Report: [issue #93](https://github.com/cpburnz/python-pathspec/issues/93), restricted to leading-space matching; its other behavior differences are out of scope. Reproduction: a pattern with leading spaces matches a filename lacking those spaces instead of the intended spaced name.
- Fix revision: [v1.0.0 tagged commit](https://github.com/cpburnz/python-pathspec/commit/v1.0.0), [release](https://github.com/cpburnz/python-pathspec/releases/tag/v1.0.0), [comparison](https://github.com/cpburnz/python-pathspec/compare/v0.12.1...v1.0.0). The [supplied diff](upstream/pathspec-v0.12.1..v1.0.0.diff) records #93 at line 269. Its individual fixing SHA is not established.
- Pre-fix: [gitwildmatch.py v0.12.1](https://raw.githubusercontent.com/cpburnz/python-pathspec/v0.12.1/pathspec/patterns/gitwildmatch.py), supplied as [pathspec-gitwildmatch-v0.12.1.py](upstream/pathspec-gitwildmatch-v0.12.1.py), plus the pre-fix pattern base above.
- Fixed evidence: [basic.py v1.0.0](https://raw.githubusercontent.com/cpburnz/python-pathspec/v1.0.0/pathspec/patterns/gitignore/basic.py) and [spec.py v1.0.0](https://raw.githubusercontent.com/cpburnz/python-pathspec/v1.0.0/pathspec/patterns/gitignore/spec.py) are bundled as added-file sections in the release diff, not standalone downloaded files. The relevant blocks are at lines 22023–22030 and 22368–22375. They preserve the expression when its last space is escaped and otherwise use `rstrip()`. [The supplied v1.0.0 gitwildmatch module](upstream/pathspec-gitwildmatch-v1.0.0-fixed.py) is only a deprecated wrapper around the new implementation.
- Licence: **MPL-2.0**, [complete licence](upstream/pathspec-LICENSE.txt). Derived `selection/rules.py` and `selection/globs.py` remain covered source.
- Extraction: retain the error class, complete `GitWildMatchPattern` class including segment translation/escaping, encoding/capture constants and the pre-fix pattern base. Remove registry imports/registration and the deprecated `GitIgnorePattern` wrapper, warnings import and unused dependencies. Direct class construction replaces registry use in this task's API.
- The reference backports only the fixed whitespace block: `pattern = pattern.lstrip()` becomes `pass`; `pattern = pattern.strip()` becomes `pattern = pattern.rstrip()`. The new upstream local `pattern_str` corresponds to old `pattern`, then renamed `expression`. No other matching algorithm changes. The independent None-construction defect remains untouched in this task; its contract accepts only text/bytes expressions.
- File renames: `pathspec/pattern.py` → `selection/rules.py`; `pathspec/patterns/gitwildmatch.py` → `selection/globs.py` (selected definitions). Redirect the relative import to `.rules`. Initializer, CLI, README and test are new scaffolding.
- [Focused upstream backport](.evidence/literal-leading-space-upstream.patch) uses normalized extracted old source; the supplied release diff preserves the original added-file changes. [Renamed reference patch](.evidence/literal-leading-space-reference.patch).
- Coverage: one/two/four leading spaces, three name lengths, text/bytes, root/nested paths, wildcards, directories, escaped and unescaped trailing whitespace, leading #/!, negation, comments, anchoring, CLI success/failure. Fixing only ordinary stripping fails escaped-final-space cases. Assertions check behavior, not generated regex strings or private helpers.

## Transformation and patch comparison

[build_anchors.py](build_anchors.py) regenerates all three JSON files, hashes, rename maps and focused diffs from the supplied bundle. It removes comments and standalone documentation strings and uses AST printing for formatting. Branches, loops and regex logic remain unchanged except for the explicit upstream reference fixes. Imports are restricted to each extraction's dependency closure. CLI wrappers parse arguments and invoke the API without repair logic. Standard-library names, magic methods and grammar tokens such as literal `export` remain unchanged.

Every explicit identifier/string substitution is listed below and in [rename-map.json](.evidence/rename-map.json), including slot names, named-tuple fields, forward annotations and f-string fragments. Standard-library exception messages remain unchanged. The internal regex capture label `ps_d` becomes `directory_edge`. Shared substitution maps may include entries unused by a particular retained definition. File/import changes and removals are described per task above.

For per-attempt patch similarity, compare the agent's patch with `*-reference.patch` in the task's namespace. Use `*-upstream.patch` and the original supplied release diff to establish upstream correspondence; the focused generated patches are clearly distinguished from the untouched raw diffs. Unrelated release changes are not the comparison target.

## Local verification

Reproduce with `python3 -B build_anchors.py` and then `python3 -B verify_anchors.py`, from this folder; the second reads the per-task files the first writes. The rebuilt tasks are byte-identical to `tasks-anchors.jsonl` (checked September 23, 2026). Verification uses Python 3.14.7 and subprocesses with `-B -S`, only the standard library, and temporary directories inside this folder. It overlays `reference_files` onto `files`, adds the hidden test and runs unittest discovery. Every given snapshot fails on the reported behavior; imports and syntax succeed. Every reference passes. Each suite exercises the CLI parser/API journey and invalid input.

| Task | JSON bytes | Visible / with tests | Test methods | Given | Reference | Incomplete fix |
| --- | ---: | ---: | ---: | --- | --- | --- |
| append-setting | 16,664 | 5 / 6 | 4 | FAIL: joined records | PASS | rejected |
| disabled-rule | 11,939 | 4 / 5 | 5 | FAIL: unbound local | PASS | rejected |
| literal-leading-space | 21,582 | 5 / 6 | 4 | FAIL: incorrect matches | PASS | rejected |

[Validation report](.evidence/validation.json) records hashes, commands, results and per-variant log paths. Checked the exact seven-field solvable-task schema, `group: anchor`, file/size limits, relative filenames, standard-library imports and absence of upstream/personal identifiers in payloads. Narrow-fix notes are in the manifest rather than an extra JSON field. The rejected mutations always insert a newline, make None an active empty regex, or retain left-stripping in the escaped-space branch.

No benchmark, model run or complete upstream test suite was run. These checks establish the extracted contracts on the local runtime. Unused packaging/boltons sources and prior discovery artifacts remain unchanged; all writes stayed inside the assignment folder.

## Complete rename maps

### settings/records.py

Identifiers:

| Original | Task |
| --- | --- |
| `make_regex` | `compile_token` |
| `_newline` | `_line_break` |
| `_multiline_whitespace` | `_record_space` |
| `_whitespace` | `_inline_space` |
| `_export` | `_prefix_token` |
| `_single_quoted_key` | `_quoted_name` |
| `_unquoted_key` | `_bare_name` |
| `_equal_sign` | `_assignment_token` |
| `_single_quoted_value` | `_single_value` |
| `_double_quoted_value` | `_double_value` |
| `_unquoted_value` | `_bare_value` |
| `_comment` | `_comment_token` |
| `_end_of_line` | `_record_end` |
| `_rest_of_line` | `_discard_tail` |
| `_double_quote_escapes` | `_double_escapes` |
| `_single_quote_escapes` | `_single_escapes` |
| `Original` | `SourceText` |
| `Binding` | `Record` |
| `Position` | `Cursor` |
| `Error` | `ScanError` |
| `Reader` | `Scanner` |
| `string` | `text` |
| `key` | `name` |
| `original` | `source_text` |
| `error` | `invalid` |
| `chars` | `offset` |
| `position` | `cursor` |
| `mark` | `checkpoint` |
| `has_next` | `has_more` |
| `set_mark` | `remember` |
| `get_marked` | `remembered` |
| `read_regex` | `consume` |
| `decode_escapes` | `unescape` |
| `decode_match` | `unescape_hit` |
| `parse_key` | `scan_name` |
| `parse_unquoted_value` | `scan_bare_value` |
| `parse_value` | `scan_value` |
| `parse_binding` | `scan_record` |
| `parse_stream` | `scan_records` |
| `reader` | `scanner` |

Strings:

| Original | Task |
| --- | --- |
| `Original` | `SourceText` |
| `Binding` | `Record` |
| `Position` | `Cursor` |
| `string` | `text` |
| `key` | `name` |
| `original` | `source_text` |
| `error` | `invalid` |
| `read: End of string` | `The record ended before the requested text.` |
| `read_regex: Pattern not found` | `The next token did not match.` |

### settings/editor.py

Identifiers:

| Original | Task |
| --- | --- |
| `Binding` | `Record` |
| `parse_stream` | `scan_records` |
| `key` | `name` |
| `original` | `source_text` |
| `string` | `text` |
| `error` | `invalid` |
| `with_warn_for_invalid_lines` | `report_invalid_records` |
| `mappings` | `records` |
| `mapping` | `record` |
| `rewrite` | `staged_edit` |
| `set_key` | `store_value` |
| `dotenv_path` | `settings_path` |
| `key_to_set` | `name_to_store` |
| `value_to_set` | `text_to_store` |
| `quote_mode` | `quote_style` |
| `export` | `export_entry` |
| `quote` | `use_quotes` |
| `value_out` | `encoded_value` |
| `line_out` | `new_record` |
| `replaced` | `updated` |
| `missing_newline` | `needs_separator` |
| `_PathLike` | `_FilePath` |
| `logger` | `log` |
| `source` | `incoming` |
| `dest` | `outgoing` |

Strings:

| Original | Task |
| --- | --- |
| `Python-dotenv could not parse statement starting at line %s` | `Unrecognized settings record at line %s` |
| `Unknown quote_mode: {}` | `Unsupported quoting style: {}` |

### routing/rules.py and selection/rules.py

Identifiers:

| Original | Task |
| --- | --- |
| `Pattern` | `RuleBase` |
| `RegexPattern` | `TextRule` |
| `RegexMatchResult` | `Hit` |
| `PatternHint` | `CompiledHint` |
| `MatchHint` | `HitHint` |
| `include` | `decision` |
| `pattern` | `expression` |
| `regex` | `compiled` |
| `match_file` | `match_path` |
| `pattern_to_regex` | `compile_text` |
| `files` | `paths` |
| `file` | `path` |
| `other` | `candidate` |

Strings:

| Original | Task |
| --- | --- |
| `include` | `decision` |
| `pattern` | `expression` |
| `regex` | `compiled` |
| `RegexPattern` | `TextRule` |
| `RegexMatchResult` | `Hit` |
| `include:` | `decision ` |
| ` must be null when pattern:` | ` requires no override for expression ` |
| ` is a string.` | ` supplied as text.` |
| ` is null.` | ` supplied as disabled.` |
| `pattern:` | `expression ` |
| ` is not a string, re.Pattern, or None.` | ` must be text, a compiled matcher, or disabled.` |
| `{cls.__module__}.{cls.__qualname__} must override match_file().` | `{cls.__module__}.{cls.__qualname__} needs a match_path implementation.` |
| `{cls.__module__}.{cls.__qualname__}.match() is deprecated. Use {cls.__module__}.{cls.__qualname__}.match_file() with a loop for similar results.` | `{cls.__module__}.{cls.__qualname__}.match() is legacy; iterate using match_path().` |

### selection/globs.py

Identifiers:

| Original | Task |
| --- | --- |
| `Pattern` | `RuleBase` |
| `RegexPattern` | `TextRule` |
| `RegexMatchResult` | `Hit` |
| `PatternHint` | `CompiledHint` |
| `MatchHint` | `HitHint` |
| `include` | `decision` |
| `pattern` | `expression` |
| `regex` | `compiled` |
| `match_file` | `match_path` |
| `pattern_to_regex` | `compile_text` |
| `files` | `paths` |
| `file` | `path` |
| `other` | `candidate` |
| `GitWildMatchPattern` | `PathRule` |
| `GitWildMatchPatternError` | `RuleSyntaxError` |
| `_BYTES_ENCODING` | `_TEXT_CODEC` |
| `_DIR_MARK` | `_DIRECTORY_GROUP` |
| `original_pattern` | `original_expression` |
| `pattern_segs` | `pieces` |
| `override_regex` | `special_expression` |
| `is_dir_pattern` | `directory_only` |
| `_translate_segment_glob` | `_compile_piece` |
| `need_slash` | `needs_separator` |
| `return_type` | `output_type` |
| `out_string` | `escaped_text` |
| `meta_characters` | `special_characters` |

Strings:

| Original | Task |
| --- | --- |
| `ps_d` | `directory_edge` |
| `pattern:` | `expression ` |
| ` is not a unicode or byte string.` | ` must be text or bytes.` |
| `Invalid git pattern: ` | `Malformed path rule: ` |
| `Escape character found with no next character to escape: ` | `Dangling escape in path rule: ` |
| `s:` | `input ` |
