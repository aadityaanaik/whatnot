# Problem 2 (medium): transactions

Clients want to make several changes that either all happen or none do. Add
`BEGIN`, `COMMIT` and `ROLLBACK` to the text protocol.

## Behaviour

```
> SET balance:alice 100
OK
> BEGIN
OK
> INCR balance:alice -30
70
> INCR balance:bob 30
30
> GET balance:alice        # reads inside a transaction see its own writes
70
> ROLLBACK
OK
> GET balance:alice
100
> GET balance:bob
(nil)
```

## Requirements

1. `BEGIN` starts a transaction and returns `OK`. Transactions **nest**:
   `BEGIN` inside a transaction starts an inner one.
2. While a transaction is open, `SET`, `DEL` and `INCR` do **not** touch the
   `Store` (and so are not written to the log). They are buffered in the
   session.
3. Every read (`GET`, `TTL`, `SCAN`, `COUNT`, and the reads that `DEL` and
   `INCR` do) sees the committed store with all open transactions' pending
   changes layered on top, innermost last. For example `SCAN` must hide a key
   deleted in the transaction and show one set in it, in sorted order.
4. `ROLLBACK` discards the innermost transaction's changes. `COMMIT` merges
   the innermost transaction into its parent; committing the outermost
   transaction applies everything to the `Store`. Both return `OK`.
5. `COMMIT` or `ROLLBACK` with no open transaction returns
   `ERR no transaction`.
6. A command that errors inside a transaction (e.g. `INCR` on a non-integer)
   leaves the transaction open and unchanged.
7. TTLs: `SET k v EX n` inside a transaction starts its n-second clock when
   the outermost `COMMIT` happens. `INCR` inside a transaction keeps the key's
   existing expiry (as it does outside one, once problem 1 is fixed).
8. Transactions belong to a `Session`. Two sessions sharing a `Store` must not
   see each other's uncommitted writes.

## Out of scope

Isolation between concurrent sessions beyond requirement 8 (no locking or
conflict detection needed): if another session changes a key while your
transaction is open, last commit wins.

## Things worth deciding deliberately (you'll be asked about them)

- Where does the buffering live: `Session`, `Store`, or a new class?
- What does `TTL` return for a key set with `EX` inside an open transaction?
  Pick something sensible and document it.
- If the process crashes halfway through applying a large `COMMIT`, what is
  in the log? (Problem 3 has a stretch goal about this.)
