# SDD ledger — plan: docs/superpowers/plans/2026-10-28-url-review.md

Design approved 2026-10-28. Execution: native, assistant implements; student learns through small edits afterward.

Ruling: workspace started without Git; isolated new directory and local implementation branch created instead of worktree — no existing checkout/branch to isolate; no remote configured or publication.

Pre-flight: Task 1 Table/Store → Task 3 UI: matching bool/error/ownership contract. Task 2 Guide → Task 3 UI: stable ordered entries and descriptions. Task 4 CLI tests exercise the same executable.

Ruling: fixed total input size safety limit 256 MiB — bounds accidental memory consumption while accommodating 5000 long descriptions; larger datasets require an explicit future adjustment.

Task 1: complete — make test-core passed. ASan/UBSan passed with ASAN_OPTIONS=detect_leaks=0; LeakSanitizer cannot run in this sandbox (ptrace restriction), not a code failure.

Task 2: guide extracted from provided category PDF using column/page coordinates; 59 actual categories including c2. No real CSV opened.

Task 2: complete — make test-guide passed.

Task 3: core ncurses scenario passed real PTY tests (multiple labels, confirmations, defer/return/back, empty NOT_DESC, resume, cancel/help/resize). A regression under LANG=C was reproduced; fixed by selecting C.UTF-8 for LC_CTYPE when the environment is single-byte.

Ruling: source tree is new Git repository, so native executor task scripts expecting an existing baseline worktree are replaced with this ledger plus task commits. No existing branches affected.
