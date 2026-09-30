# Problem 3 (hard): crash recovery and log compaction

tinykv has been running in production for a month. Two incidents:

> **Incident A.** The host lost power. On restart, `python -m tinykv --data
> prod.log` crashed immediately with `json.decoder.JSONDecodeError:
> Unterminated string`. The last line of `prod.log` was
> `{"op":"set","key":"user:42","val` with no newline.

> **Incident B.** `prod.log` is 4 GB, and startup takes minutes, but the
> store only holds about 2,000 keys. Nearly every record is an overwrite of a
> hot counter or a key that has long since expired.

## Part A: survive a torn write

A crash in the middle of `WriteAheadLog.append` can leave a partial final
record. Make `Store.open` recover from that.

- A final record that is incomplete (for example, no trailing newline, or
  not valid JSON) is discarded, and the file is truncated so the next append
  starts on a clean line. The store opens with every complete record applied.
- Corruption **anywhere other than the tail** is not a crash artefact and
  must not be silently skipped. Raise `tinykv.wal.CorruptLogError` (a new
  exception, subclass of `Exception`) with a message that includes the line
  number.
- Explain in the walkthrough how you decided what counts as "the tail" and
  why a missing newline is the signal you rely on (or not).

## Part B: compaction

Add `Store.compact() -> None`, which rewrites the log so it contains only
what is needed to rebuild the current state: one record per live key,
expired keys dropped.

- **Crash safety:** a crash at any moment during `compact()` must leave a log
  that reopens to the same logical state. Never truncate or rewrite the live
  log in place. (Look up `os.replace`, and think about `fsync` on the file
  and its directory.)
- After compacting, the store keeps working: new writes are appended to the
  compacted log and survive a reopen.
- Expiry times are preserved exactly (they are absolute timestamps).
- Test it, including a simulated crash partway through (for example,
  monkeypatch `os.replace` to raise) and a check that the log shrank.

## Part C (stretch): automatic compaction

Compact automatically when the log is mostly garbage: add a
`compact_threshold: int | None` option to `Store` / `Store.open`. After a
write, if the log holds more than `compact_threshold` records **and** more
than twice as many records as live keys, compact. You'll need to track the
record count without rereading the file on every write.

## Part D (stretch, needs problem 2): atomic commits

Right now a `COMMIT` that applies 50 changes writes 50 separate log records;
a crash halfway leaves half a transaction in the log. Make the outermost
commit a single log record so replay applies it all or nothing. How does that
interact with your torn-tail handling from part A?
