# Bug log

Every bug found, and what found it.

| # | Bug | Found by | Fix |
|---|---|---|---|
| B1 | Deals were sized against their own matching supply only. Overlapping deals promised 486k impressions against ~290k slots, so even guaranteed-first delivered 23/40. | Per-campaign delivery table on the first synthetic run | Scale the whole book to a share of forecast slots (`guaranteed_book_share`). |
| B2 | With urgency exponent 4 (the spec's "flat then steep"), AdFill delivered 12/40 in full on synthetic worlds. Campaigns deferred until they needed ~70% of remaining matching supply, then collided. Exponents ≥ 1.5 under-deliver on seeds 1–3; exponent 1 delivers 40/40 and earns the most. | Exponent sweep, seeds 1–3 | Default exponent 1.0. Root cause is the forecast ignoring contention (see B3); revisit in Phase 3. |
| B3 | The Phase 1 forecast was a fixed average of pre-window history, not a trailing one as specified. MovieLens traffic in the window ran ~15% below history, so every campaign under-paced. | MovieLens run: forecast vs realised breaks per day | Rolling trailing average fed by break arrivals. Makegoods $82 → $42. |
| B4 | After B3, deals were sized at their own start date; the rolling forecast expired its history with no arrivals and forecast zero, shrinking the book 14×. | Promised-impressions total on the next run | Size deals at window start. Regression test `test_book_is_sized_to_capacity`. |
| B5 | Deal generation crashed when the window was shorter than the minimum flight. | `tests/test_engine.py` (10-day world) | Clip flight bounds to the window. |
