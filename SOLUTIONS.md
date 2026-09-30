# Reference solutions and walkthrough notes

Spoilers. These are one reasonable answer each, not the only one. Compare
code with `git diff main solutions -- tinykv/`. The acceptance tests are in
`tests/acceptance/`.

## Problem 1: expiry bugs (all in `store.py`)

| Report | Root cause | Fix |
|---|---|---|
| #101 readable at exactly TTL | `_is_expired` used `now > expires_at`; the docstring says gone *at* `expires_at` | `>=` |
| #102 SCAN/COUNT show expired keys | Expiry is lazy and only enforced in `_live_entry`; `scan` and `__len__` read `_data` directly | `_purge_expired()` before both |
| #103 INCR drops TTL | `incr` wrote `expires_at: None` | carry `entry.expires_at` into the new record |

Walkthrough points:

- Show the failing test first for each, then the fix. That is the story
  interviewers want.
- #102 is a design smell, not just a bug: expiry is enforced by convention
  (every reader must go through `_live_entry`). Purging in one helper makes the
  invariant harder to break. Alternative: an eager expiry heap; mention the
  trade-off (O(n) scan vs. background work) rather than building it.
- #103's restart requirement is why the fix belongs in the log record (absolute
  `expires_at`), not in some in-memory patch.
- Lazy deletion without a log record is safe *because* expiry is absolute.
  Being able to say why is a good signal.

## Problem 2: transactions (`commands.py`, plus `Store.lookup` / `Store.apply_batch`)

Design: a stack of layers on the `Session`, each a `dict[str, Pending | None]`
(None = deleted). Buffering in the session (not the store) gives requirement 8
(isolation between sessions) for free.

- **Reads** walk layers innermost to outermost, then fall back to the store.
  `SCAN` starts from `store.scan(prefix)` and applies layers bottom to top;
  `COUNT` is `len(scan(""))` so it cannot disagree with `SCAN`.
- **Writes** go to the top layer. `INCR` reads through the view, so it works
  on a pending value, and `replace(current, value=...)` keeps whatever expiry
  the current value had.
- **TTL** is modelled as two fields: `ttl` (relative, starts at COMMIT, from
  `SET ... EX`) and `expires_at` (absolute, inherited from a committed key by
  `INCR`). A single field can't express both; this is the subtle part.
- **Nested COMMIT** is `parent.update(child)`. **ROLLBACK** is `pop()`.
- **Outermost COMMIT** converts layers into store `Entry`s and calls
  `Store.apply_batch`, which writes one `batch` record (that's part D of
  problem 3 already done).
- **Errors** are raised before the layer is touched, so a failed `INCR` leaves
  the transaction unchanged.

Things to be ready to discuss: what TTL reports inside a transaction (we
report the full relative TTL, not ticking); a key whose inherited
`expires_at` passes mid-transaction reads as missing; lost updates between
sessions (last commit wins; optimistic concurrency via per-key versions, as in
Redis `WATCH`, is the next step).

A common alternative is buffering an op list and replaying it at commit. It
works for writes but makes every read O(ops) and complicates SCAN; say why you
chose one over the other.

## Problem 3: crash recovery and compaction (`wal.py`, `store.py`)

**Part A.** `replay` reads the file as bytes and splits on `\n`. Everything
before the last newline is a complete record; anything after it is a torn
write, which is discarded and truncated off so the next append doesn't glue
onto garbage. A newline-terminated line that fails to parse is corruption and
raises `CorruptLogError` with the line number.

Why the newline: `append` writes `record + "\n"` in one call, so the newline
is effectively the commit marker. A torn write is a prefix of that; it can't
contain the newline without being complete. Honest caveats worth raising: a
single `write` is not guaranteed atomic on every filesystem, and power loss
can leave zero-filled blocks. Per-record checksums (length + CRC, as real WALs
use) are the robust answer; mention it, don't necessarily build it.

**Part B.** `WriteAheadLog.rewrite` writes the live set to
`data.log.compact.tmp`, `fsync`s it, `os.replace`s it over the log (atomic),
then `fsync`s the directory so the rename is durable. On failure the temp file
is removed and the original log is untouched. Expired keys are dropped;
`expires_at` is copied unchanged.

**Part C.** `WriteAheadLog.record_count` is set by `replay`, incremented by
`append`, reset by `rewrite`. `Store._maybe_compact` runs after each write:
`records > threshold and records > 2 * live_keys`. The 2x ratio is what stops
a store with many live keys from compacting on every write.

**Part D.** Solved by `apply_batch` in problem 2: one line per commit, so the
torn-tail rule from part A makes commits all or nothing.

Stretch discussion: compaction blocks writes (fine single-threaded, not in a
server); `open()` per append is slow (keep the file handle open, batch fsyncs /
group commit); snapshot + log segments instead of one file.
