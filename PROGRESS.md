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

Task 3: complete — real PTY tests cover core manual scenario; task 4 extends error/resize coverage.

Final review: fresh independent reviewer inspected 7d81864..6b1add8. Three important findings reproduced, each covered by regression tests. Confirmation clipping regraded from minor to important because users must be able to inspect every selected label before saving.

Final: fixed inconsistent resume parse/snapshot — tests/test_race.c observed RED (external decision lost), GREEN with single-buffer parse and snapshot, including source initial-copy parse from the same bytes.

Final: fixed hidden small-window confirmation — test_small_window_does_not_confirm_unseen_decision observed RED (ERROR committed), GREEN with selection/saving disabled until sufficient size.

Final: fixed hidden directory fsync failure — tests/test_sync.c observed RED (ordinary success), GREEN with explicit SAVE_UNCERTAIN; test_uncertain_sync_warns_and_waits_for_retry verifies actual warning and retry in a PTY.

Final: fixed long confirmation clipping — test_long_confirmation_can_scroll_to_last_selected_category observed RED; GREEN with scrollable complete confirmation (30 long codes at minimum supported terminal size).

Ruling: after successful rename and failed directory sync, keep memory matching the replaced file and report SAVE_UNCERTAIN; UI does not advance, allows retry — prevents false rollback and false success; power-loss persistence remains uncertain until successful retry.

Final: minor (deferred): externally re-saved compatible working copy retains its own BOM/EOL on resume instead of forcing source metadata; field contents unchanged, README documents this limitation.

Final: Ruling: no physical power-loss/network-filesystem verification — scope is local Linux disk and injected failure tests; do not promise those untested durability guarantees.

Final: Ruling: reviewer validated guide structure, not PDF semantic fidelity — guide generated directly from provided PDF with page/column boundaries and spot-checked; user can inspect source criteria through H, no disputed journal hypotheses included.

Task 4: complete — final warnings-as-errors build; make test (4 C binaries + 12 Python integration tests) and make sanitize passed. Real demo launcher and 5000 synthetic records (~108 MiB) checked. Detailed evidence: docs/verification.md.

Final outcome: keep new local implementation branch and source directory in place, export portable source archive; no existing base branch/upstream to merge into, no push requested. Embeddings remain explicitly next-stage scope.

## Дополнение: открытие сайта

2026-10-28: по запросу пользователя добавляем O/клик на домен → браузер по умолчанию. Текстовый браузер/встраивание JavaScript-страниц не добавляются. Дизайн малого изменения: docs/browser-opening.md.

RED: PTY-тесты открытия по O/клику и отказа file:// не проходили до реализации, модуля browser.c не было. GREEN: модуль нормализует только HTTP(S), posix_spawnp передаёт URL одним аргументом без shell, UI запускает асинхронно и следит за результатом. Проверки используют подставной локальный xdg-open, без настоящего браузера.

Final 1.1: чистая сборка с предупреждениями как ошибками и полный набор из 16 Python-тестов плюс C-проверки прошли. Независимый reviewer не нашёл существенных замечаний. Обновление упаковано отдельно от v1; настоящие сайты не открывались.
