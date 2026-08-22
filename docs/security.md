# Kytos — Security & secret handling

Deterministic, offline secrets policy. See `tools/scan_secrets.py` +
`tools/secrets-allowlist.txt` (hooked via `.pre-commit-config.yaml`).

## Why offline & deterministic

The pre-commit secrets hook is our own ~120-line scanner, not a network-fetched
tool (no `detect-secrets`/`gitleaks`/`trufflehog` sandbox). Rationale — every
contest deadline fails loudly when a toolchain that grabbed a sandbox weeks ago
rots or vanishes:

- third-party scanners drift and silently change behavior between installs;
- `pre-commit` installing a remote repo needs network on first run, which can
  be unavailable in CI or offline editing;
- we control the exact patterns, so a false-negative is a bug we can fix, not a
  black box we pray about.

This mirrors `NOTES.md` §5 (elcaro: treat fetched content as untrusted; weft:
rules decide). The verdict is made by **rules**, never by an LLM.

## The allowlist — and the discipline it demands

An allowlisted term suppresses **any** secret match that *contains* it. This is
the only escape hatch, and it is the single highest-risk control in the repo.

### Hard rules
1. **Never whitelist a real credential.** The allowlist is for deliberate
   stubs/examples (e.g. `AKIA0000000000000000`, `sk_test_`). If a real key ever
   enters a committed file, you must rotate it and remove it — do not add it to
   the allowlist.
2. **Keep entries minimal and shard-like**, so they cannot accidentally cover
   real tokens. `sk_test_` is fine; `sk-` is NOT.
3. **Prefer `#`-comments with a reason** next to each entry so future-you knows
   *why* it's there and can audit whether it's still needed.
4. **Review the allowlist on every security-relevant commit.**

### Known gap (accepted, must be revisited)
The current scanner is **pattern-based**, so a *novel or low-entropy* secret
with no matching pattern — or a real key that embeds an allowlisted stub shard —
will **not** be caught. The scanner is a **safety net, not a guarantee**. The
real guarantee is: real credentials never enter the repo in the first place.
Use per-deployment env vars / secret managers for anything live.

### Built-in blind spots to note
- **Binary files** are skipped (`\x00` check). Do not commit secrets in
  parquet/h5ad/onnx artifacts.
- The `high-signal assignment` pattern is intentionally strict (`key = "…"`).
  Obscured or base64-encoded secrets are invisible to it.

## Extending the scanner
Add patterns to the `PATTERNS` list in `tools/scan_secrets.py` — e.g. when you
later add real API access (OpenAI, Anthropic `sk-ant-`, LangChain, Hugging Face
`hf_`, cloud IAM) add their token formats and, per the ethos, a
high-entropy no-allowlist guard. Keep each pattern anchored (`\b`) and
false-positive-aware; test with a planted pattern before committing.

## When you add real infra (planned: post-challenge)
- Keep credentials out of the repo indefinitely; inject via env at deploy.
- If you ever commit `.env.example`, add it to the allowlist **by filename**
  only if the scanner's content patterns would otherwise hit its placeholder
  values — and never commit a real `.env`.
- Add a CI-enforced scan (same script runs on PRs) once a CI exists; the
  pre-commit hook covers the local path today.

## Verification checklist
- [ ] Secrets scan passes on `--all` and on staged files
- [ ] A planted real-pattern token **blocks** the commit
- [ ] An allowlisted stub does **not** block
- [ ] `git log` contains no artifact with a raw credential