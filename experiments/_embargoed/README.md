# Embargoed results — PUBLISHED 2026-11-20

The competition embargo lifted with the Nov 19 winners announcement; this
tree is now tracked in git with its original file structure intact. The
procedure below is kept for the record.

Competition embargo until the Oct 22 final test set: experiment results,
score tables, and findings stay local-only. Code and infrastructure still
push to the public repo. Publish after the deadline with history intact.

## Publish procedure (verified 2026-10-03, dry-run clean)

The whole tree is local-only via one `.gitignore` line —
`experiments/_embargoed/` — so publishing is removing that rule and
committing the tree. There is no git history for these files (they were
never tracked); "history intact" means the internal dating is the record —
dated dir names (`gate-20260921-01`), file mtimes, and the dated docs
themselves. Commit them as they are.

```sh
# 1. Lift the ignore rule (the only gitignore change needed)
sed -i '' 's|^experiments/_embargoed/$|# experiments/_embargoed/  (embargo lifted 2026-10-22)|' .gitignore

# 2. Stage — expect exactly this dir plus .gitignore, nothing else
git add .gitignore experiments/_embargoed/
git status --porcelain    # 178 files + modified .gitignore as of 2026-10-03

# 3. Pre-commit runs tools/scan_secrets.py on the staged files (already
#    verified clean on 2026-10-03); ruff hooks do not fire — no .py files here.
git commit -m "embargo lifted: publish experiments/_embargoed receipts"
git push
```

Post-publish sanity checks (all verified in the dry run):

- `frontend/build.py` still discovers exactly the kNNN runs — `_embargoed/`
  has no top-level `facts.json`, so it is skipped by `discover_runs`, and
  nothing under it is copied into `dist/`.
- Every public doc references this tree via inline code paths
  (`` `_embargoed/…` ``), not markdown links — no link rot before or after.
- Optional follow-up commit: update the "embargoed until Oct 22" sentences
  in `AGENTS.md`, `experiments/README.md`, `docs/vcc-two-track-strategy.md`,
  and `docs/signature-content-impasse.md` to point at the now-public paths.

Timing note: AGENTS.md says publish after Oct 22, but final submissions run
through Nov 5 — pick the date deliberately.
