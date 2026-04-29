# Repo-versioned git hooks

These hooks block commits whose staged content or commit message matches
any pattern in `blocklist.txt`. The intent is to prevent customer names,
internal infrastructure references, and known-bad credential strings
from leaking into the public repo.

## Install (per-clone, one-time)

```bash
bash .githooks/install.sh
```

This sets `core.hooksPath = .githooks` for this clone. Both
`pre-commit` and `commit-msg` are armed.

## What gets blocked

`blocklist.txt` is the authoritative list. Each line is a
case-insensitive POSIX extended regex, applied against:

- the **added or modified lines** in the staged diff (pre-commit hook)
- the **commit message text**, with `#`-prefixed comment lines stripped
  (commit-msg hook)

A match in either prints the offending pattern and aborts the commit
with a non-zero exit code.

## Edit the blocklist

```bash
vi .githooks/blocklist.txt
git add .githooks/blocklist.txt
git commit -m "chore: extend blocklist"
```

The file format is its own documentation; the top of the file lists the
syntax rules.

## Bypass

```bash
git commit --no-verify
```

Don't make this a habit. If a pattern is hitting a false positive, the
right fix is to refine the regex in `blocklist.txt`, not bypass.

## Uninstall

```bash
git config --unset core.hooksPath
```
