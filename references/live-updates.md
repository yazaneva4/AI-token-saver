# Live context and code updates

Use fresh tool results for current files, status, versions and prices. Never label remembered content live. Re-read a file after an edit or when its fingerprint changes. Preserve timestamps and report offline or unavailable sources accurately.

For a local UTF-8 context file that another tool keeps writing, start:

```bash
python live_watch.py context.txt --output compacted-context.txt --interval 1
```

Keep the process running while updates are needed. It reads the current file once per interval, publishes changed snapshots atomically, and skips unchanged content. The default `runs` mode is reversible. `--dedupe off` keeps exact input; `--once` runs one check. Do not watch credentials or write to the input path. The watcher does not call a model or reduce usage already consumed, and is not a background daemon after it exits.

For a Git clone, check code freshness with `python update_skill.py`; run `python update_skill.py --update` when updating is requested. The update accepts only the official origin, refuses local edits and non-fast-forward merges, and never changes provider quotas. Stop the watcher before updating and restart it afterwards. ZIP installs require a fresh ZIP and host reload. A skill cannot hot-swap instructions already loaded into an assistant's context.

Build the current ZIP with `python build_skill.py`. CI publishes a fresh package artifact from tested source; a Git commit alone does not replace a user's already-installed copy.
