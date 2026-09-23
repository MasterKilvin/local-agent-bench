# Public bug anchor provenance — INCOMPLETE

No task JSON has been authored or validated. These are discovery notes, not a completed provenance record. No benchmark was run and no other folder was changed.

## Sources successfully fetched on 2026-09-22

- [python-dotenv issue 360](https://github.com/theskumar/python-dotenv/issues/360): adding a key to a file without a final newline joins the new assignment to the previous value.
- [python-dotenv PR 361](https://github.com/theskumar/python-dotenv/pull/361): the conversation confirms the merged fix; the page displays commit abbreviation `2e0ac43` and merge abbreviation `45848bb`. The actual PR/commit diff was **not fetched**.
- [Pre-fix main module at v0.19.1](https://raw.githubusercontent.com/theskumar/python-dotenv/v0.19.1/src/dotenv/main.py) and [post-fix main module at v0.19.2](https://raw.githubusercontent.com/theskumar/python-dotenv/v0.19.2/src/dotenv/main.py): fetched as web-rendered text, whose Python indentation/newlines were collapsed. This is not a byte-exact source archive. Parser dependencies and the licence were not retrieved.
- [python-pathspec issue 93](https://github.com/cpburnz/python-pathspec/issues/93): includes a leading-space pattern mismatch, alongside other behavior differences. A task based on this report should isolate the leading-space case.
- [python-pathspec issue 98](https://github.com/cpburnz/python-pathspec/issues/98): constructing a null-operation regex pattern raises an uninitialized-local exception.
- [Pre-fix pattern module at v0.12.1](https://raw.githubusercontent.com/cpburnz/python-pathspec/v0.12.1/pathspec/pattern.py): the fetched text contains the reported missing assignment. Fixed source and the exact fixing commit were not retrieved.
- [python-pathspec change history in README](https://github.com/cpburnz/python-pathspec/blob/master/README-dist.rst): records both fixes in 1.0.0 and identifies MPL-2.0 licensing. The pinned licence file still needs fetching.
- [boltons changelog](https://raw.githubusercontent.com/mahmoud/boltons/master/CHANGELOG.md): records an atomic-save overwrite fix in 18.0.1. The linked historical report and fix were not retrieved; this candidate is not established.

The available source views are retained in `.evidence/source-views.txt`. Selected failed historical fetches are retained in `.evidence/historical-fetch-failures.txt`. These contain web tool renderings, not original source bytes; do not treat their hashes as upstream file hashes.

## Retrieval blocker

The shell's HTTPS request failed at DNS resolution. The web tool could read the public issue pages and some tagged source views, but historical commit pages, PR diff endpoints, and required additional source URLs returned cache misses or internal errors. Browser connection returned `No browser is available`.

Per the workspace instruction to stop after an alternative approach also fails, further retrieval attempts stopped. Completion requires readable upstream source bundles and fixes, or an execution environment that can fetch them. No rename map, licence archive, authentic fix diff, regression result, or reference implementation has been fabricated.

## Remaining work

Retrieve the exact fix and parent source plus dependency closure and licence for three or four candidates. Extract and consistently rename executable code; record every transformation here. Create the neutral README, entry point, behavioral tests and reference files; verify original-fails/reference-passes, file counts, size limits, and realistic entry-point behavior. Write one line per completed task in MANIFEST.md only after those checks pass.
