# Finding Side-Effect Loopholes in AppWorld and WorkArena Verifiers

Code and evidence for the NeurIPS 2026 workshop paper (Workshop on Who Verifies
the Agents?) by Richard Abrich. arXiv: https://arxiv.org/abs/2610.09142

The paper mutation-tests the verifiers shipped with AppWorld and WorkArena. Each
test makes one hand-written edit to a correct run, and a pass counts as a false
positive only when a separate read of the end state shows the wrong change.

## What is here

`verifier-audit-supplement/` is the same archive as the paper's supplement on
OpenReview (73,296-byte ZIP, SHA-256
`9c5e7373925a4203962ced60c77ab46db5d871c8ba773b137fd92a21bce53554`). It
includes the 15 November 2026 rerun of the WorkArena per-step episodes, graded
at submit by BrowserGym's own post-step call. Its standard-library reproducer
recomputes the paper's counts from the packaged evidence:

```bash
cd verifier-audit-supplement
python reproduce.py --check --verify-manifest
```

It needs Python 3.10 or later and no credentials, model, benchmark server or
verifier. See `verifier-audit-supplement/README.md` for what each file holds.

The archive contains no AppWorld protected content: AppWorld requires encryption
for any public redistribution of its task data and evaluators, so the two
repaired tests appear only as SHA-256 digests and a description of the one
assertion each adds.

## Running an audit

The audit method is available as a general verifier-audit tool in OpenAdapt:
https://github.com/OpenAdaptAI/OpenAdapt/tree/main/packages/flow/openadapt_flow/verifier_audit

## Terms

See `verifier-audit-supplement/LICENSE.txt` and
`verifier-audit-supplement/THIRD_PARTY_NOTICES.txt`.
