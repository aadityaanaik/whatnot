# Problem 1 (easy): expiry bug reports

Three bug reports came in this week about keys with a TTL. Each reporter is
sure they found a real bug. Reproduce each one with a failing test, find the
root cause, and fix it.

> **#101** "I do `SET otp 123456 EX 30` and poll `GET otp` once a second.
> The docs say a 30 second TTL means the key is gone at 30 seconds, but I
> can still read it at exactly 30."

> **#102** "After my session keys expire, `SCAN session:` still lists them,
> and `COUNT` still includes them. `GET` on those same keys correctly returns
> `(nil)`."

> **#103** "We use `INCR` for per-minute rate limiting:
> `SET rl:alice 0 EX 60`, then `INCR rl:alice` on each request. The counters
> never reset. `TTL rl:alice` says `-1` after the first request."

## Requirements

- All three reports are fixed, each with at least one regression test that
  fails before your fix and passes after.
- The documented semantics in `Store`'s docstring are the source of truth.
- Existing tests still pass.
- Fixing #103 must also survive a restart: after `INCR`, reopening the store
  from its log should still have the key expire at the original time.

## Hint (only if stuck)

<details><summary>Show</summary>

All three are in `tinykv/store.py`. For #102, look at which methods go
through `_live_entry` and which read `_data` directly.

</details>
