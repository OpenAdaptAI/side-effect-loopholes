# Verifier audit supplement, camera-ready

This archive reproduces the counts in the camera-ready paper. It needs Python
3.10 or later and nothing else: no credentials, no model, no benchmark server,
no checker.

```text
python reproduce.py --check --verify-manifest
```

The script checks `MANIFEST.sha256`, which lists every other file in the
archive, and refuses to run if a file is missing, extra, or changed. It then
derives the counts and compares them with `expected_results.json`. Where a
camera-ready count can be recomputed from the reviewed `data/` files, the
script recomputes it and stops if the two disagree.

## What changed since the reviewed supplement

The reviewed archive carried two copies of shipped AppWorld evaluators in
plain form, plus twelve regrade ledgers that listed AppWorld's requirement
text. AppWorld releases its protected code and data under Apache-2.0 with one
more condition: public copies, and copies of derivatives, must be encrypted.
Those fourteen files are gone. `patch_repair/patches.json` now describes the
two test changes in words and by SHA-256, and
`patch_repair/regrade_summary.json` keeps the regrade's requirement counts
without the text.

The 23-cell WorkArena extra-field rerun is withdrawn as evidence. Its anonymous
derivative stays in `data/` as history, and
`camera_ready/workarena_rerun_alias_probe.json` says why it no longer counts. A
paired census replaces it.

`camera_ready/` is new. `LICENSE.txt` replaces the anonymous-review license.

## The two AppWorld test changes

Generator `22cc237` creates Venmo payment requests. Its shipped test checks the
field values of the added payment requests and asserts that no request was
updated or removed. It never counts the added rows, so a duplicated request
passes. The regraded copy inserts one assertion after line 61 of the shipped
file, inside that same requirement: the number of payment-request records the
run added must equal the number of payment requests the task asks for.

Generator `396c5a2` adds songs to a music queue. Its shipped test compares the
end-state queue with the songs already queued plus the songs to add, as sets,
so a duplicated enqueue passes. The copy inserts one assertion after line 82,
the last line of the shipped file, inside that requirement: the queue's length
must equal the number of songs already queued plus the number of songs to add.

Neither copy changes or deletes a shipped line. Neither adds a requirement
block, because AppWorld's evaluator rejects a requirement string it doesn't
know, which would turn the run into an evaluation error rather than a FAIL.
Each copy also has a comment after line 1 that records the shipped file's
SHA-256. With a local AppWorld install, that digest identifies the file each
copy started from.

The frozen protocol is `patch_repair/PROTOCOL_PATCH_REPAIR_2026_08_30.md`.
The regrade sent all six Extra-NI runs from PASS to FAIL. In each one, the
single failing requirement is the one that holds the inserted assertion. All
six controls stayed PASS. Table 2 still reports the unmodified shipped tests.

## Camera-ready evidence

Each file in `camera_ready/` summarizes one output committed in the study
repository, and `artifact_inventory.json` gives that output's SHA-256. The
scripts that produced them need the AppWorld data bundle, a WorkArena install,
or AppWorld's released baseline runs, so they stay out of the archive. The
summaries keep counts and drop per-run records.

`operator_tally.json` counts the edits that remove or change the requested
effect: 261 scored, 252 FAIL, 9 PASS. All nine PASS cells are WorkArena
omitted-field edits whose default already equals the requested value. The
reproducer recomputes these totals from `data/fault_family_vectors.json`. It
also recomputes the intent-swap census from `data/intent_swap_cells.json`:
2,689 valid off-diagonal runs (2,263 AppWorld, 426 WorkArena), no PASS, and
118 one-parameter twins (43 and 75). The six confirmed false accepts are all
AppWorld Extra cells, three on `22cc237` and three on `396c5a2`.

`workarena_paired_census.json` replaces the withdrawn rerun. The census
scheduled 84 control and mutation pairs, 168 episodes. In each of the 36
complete valid pairs, the checker passed the mutation, the Table API readback
confirmed the extra saved value, and the checker passed the paired control.
All 57 valid controls passed. The other 48 pairs are unresolved. In 27
hardware-asset pairs, each task object generates its own serial number, so the
two records differ in a required field. In the other 21, the mutation stopped
before the checker ran. The 36 pairs cover 12 candidate fields over seven field
names in two templates, incident and change request. In all 147 episodes that
reached the checker, the page's extra-field flag was unset when the checker
read it. Each of those episodes called the checker once, after submit.
Per-step validation wasn't tested. With 48 pairs unresolved, 36 of 36 doesn't
estimate a rate.

`workarena_rerun_alias_probe.json` explains the withdrawal. The rerun built its
form driver from the same configuration object the evaluator read. In all 9
hardware-asset cells, the driver's constructor overwrote the serial number the
evaluator expected. None of the 14 other cells changed, and none of the 23
changed when the probe gave the driver a deep copy. Nine of the rerun's 21
nondefault PASS cells are those hardware-asset cells. The reproducer matches
the probe's per-template counts against the anonymous template aliases in
`data/workarena_extra_readback.json`.

`e1_official_trace_regrade.json` reads AppWorld's released 2024 baseline runs:
8,190 rows over 28 configurations, 1,277 of them PASS. No PASS row sends the
payment-request create call or the queue add call twice with the same payload,
and none holds two identical payment-request rows.

`e2_reward_equivalence.json` holds the six duplicate-write runs and their clean
controls. Each duplicate passed the same requirements as its control (4 of 4
on `22cc237`, 6 of 6 on `396c5a2`) while making extra writes. The reproducer
computes three rewards from those counts: the pass fraction, the
all-requirements binary reward, and a ProCredit-style score. All three are
equal within every pair. No policy was trained.

`e6_natural_runs_count_check.json` applies the count check to 17 archived agent
trials on four task ids. The shipped tests accept 13. The count check rejects
none of the 13, and 12 of them make exactly the reference solution's state
change. A positive control, the Extra-NI duplicate replayed fresh, passed the
shipped tests and failed the count check on all four task ids.

## The reviewed data, still here

`data/` holds every anonymous intent-swap verdict, the anonymous task and
evaluator manifests, the 48-task duplicate-write census, and paired control and
fault records for all 15 non-idempotent cells. Each paired record has
application-counter totals, call-error counts, call counts, and the checker
verdict. From them the script derives the 33 degenerate edits, 15 eligible
effects, six checker acceptances, five eligible generator groups, and two
positive generator groups.

The AppWorld rank-consequence derivative holds the shipped Task Goal Completion
counts for all 14 archived configurations on each test split, plus the
false-accept and deduplicated control inputs. At the observed budget, 6 of 91
strict `test_normal` orders survive and none of the 91 `test_challenge` orders
do. This is a sensitivity analysis. Interval overlap means the evidence budget
doesn't identify an order. It doesn't show that a shipped rank is wrong.

The original 76-cell WorkArena extra-field flow refused 40 cells before an
attempt, and 13 more stopped before delivery. The other 23 received a checker
PASS, but that run didn't read the field back after submit, so its family
vector records 23 effect-unconfirmed PASS results and no confirmed false
accept.

The `data/` files are non-reconstructive derivatives. They omit source task
identifiers, task and evaluator text, AppWorld database model and field names,
endpoints, payloads, raw application state, and the private alias map. The
camera-ready summaries name only what the paper names: the two AppWorld
generators, and the WorkArena templates and fields.

## Terms

The archive's keys predate the camera-ready wording. `checker` in a key is the
paper's verifier. `DEV` in `protocol_v3.json` is the paper's audit set: eight
generators from AppWorld's official train split and eight from its official dev
split. The sealed holdout wasn't used. A fault family is an operator, an
intent-swap `RUNG` is a distance level, and a degenerate edit is an equivalent
mutant, one that leaves the requested effect correct.

## Provenance

`lineage.json` orders the 19 study stages by protocol and scoring time and
lists 7 later source events, including the retally, the WorkArena withdrawal,
and the removal of the evaluator copies. `artifact_inventory.json` binds every
derived file to the SHA-256 of each source it was built from. Neither exposes a
first-party repository revision.
