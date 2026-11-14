# Patch-repair increment — frozen 2026-08-30 before scoring

This is a new post-census increment. It is not a rewrite of the main audit
or of Table 2. The main audit still uses the unmodified shipped AppWorld
tests; no cell in `fault-aw-v3`, `fault-aw-v3-ni`, or the WorkArena ledgers
is re-scored here, and the pinned `appworld==0.1.3.post1` wheel
(source `66ad809`) is not edited in place.

The patch lives only under `analysis/intent_swap/patch_repair/`. For each of
the six Extra-NI extra-row cells (`22cc237_1/2/3`, `396c5a2_1/2/3`) it copies
the shipped `ground_truth/evaluation.py` and adds only
`test.case(len(added_*), "==", N)` — the assertion AppWorld's own generator
guide already documents (`guides/developing_new_task_generators.md`: "if the
task requires sending money on Venmo … do NOT compare the size of the
tables. Instead … `test.case(len(added_addresses), "==", 1)`"). Generator
`22cc237` already asserts `|updated|=0` and `|removed|=0` and never
`|added|=N`. Generator `396c5a2` compares `queue_song_ids` by set-union; the
copy adds `|queue|=|existing|+|to_be_added|`. Uniqueness was not required
to flip those three cells: Extra-NI queues grew 10 to 11, so cardinality
alone fails. The same Extra-NI
programs (retained `edited_calls.jsonl` from `raw_ledgers/fault-aw-v3-ni`)
are then replayed fresh and graded under those copies. Their CONTROL
replays are graded too, as a no-false-reject check. Expected: 6/6 extra-row
cells PASS→FAIL; CONTROLs stay PASS. Idempotent extras on other generators
are out of scope (their tests are unpatched). The added `test.case` sits
inside an existing `with test(...)` requirement: AppWorld's evaluator
refuses unknown requirement strings from `test_data.json`, so a new
requirement block is an EVAL_ERROR rather than a FAIL. No model calls.
HOLDOUT stays sealed. WorkArena is not re-run.

Command, after this file and the patched copies are committed:

```text
python analysis/intent_swap/patch_repair/run_patch_repair.py \
  --appworld-root "$OA_BENCH_APPWORLD_ROOT" \
  --appworld-python "$OA_BENCH_APPWORLD_VENV/bin/python" \
  --out analysis/intent_swap/patch_repair/run
```
