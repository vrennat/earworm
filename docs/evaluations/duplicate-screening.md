# Duplicate screening evaluation

The release-review repeat was a classification failure, not missing coverage.
The screening prompt contained both the published usage-data episode and its
original commission, but the local judge accepted another telling of it.

The baseline also produced repeated JSON keys, which Python silently overwrote.
A sparse list of rejected topics could not distinguish an intentionally new topic
from an omitted decision. Making the instructions longer did not repair the miss.

## Candidate change

Each proposal receives an explicit decision with up to three candidate coverage
matches. A second call compares only those exact pairs. A related first match
cannot hide a better match later in the shortlist. Both calls use the existing
local route, with its request, token, time, and spending limits.

The parser rejects missing/repeated decisions, duplicate JSON keys, out-of-range
references, ambiguous types, and incomplete confirmations. It resolves references
only to supplied coverage. Bare numbers and the observed unambiguous `{n}` or
`{n, reason}` reference objects are accepted. Extra valid ranked references are
validated and then capped to three. Malformed screening stops discovery before
queue writes, rather than quietly accepting unscreened topics.

## Method

Twelve diagnostic proposals were labeled before comparative responses: six
repeats and six distinct stories, grouped into three batches of four. Four are
the original discovery batch; eight are constructed paraphrases and adjacent
controls. The coverage snapshot contains 80 episode descriptions and 80 topic
commissions. These records are evaluation inputs, not independently verified
claims about the underlying research.

The controls distinguish SQLite document storage from WAL concurrency,
usage-data interpretation from privacy engineering, nonunique circuit
explanations from interference weights, and unrelated biological/hardware
mechanisms. Labels were authored during this investigation; this is a small,
partly fitted diagnostic set, not an independently adjudicated benchmark.

The model is local `gemma4:26b`, Q4_K_M, with explicit reasoning effort `none` and
1,500 output tokens per call. Model digest:
`08ae7ec1744bd7f451c4a530afb39d2673ad9d07a8369b8a33a3613b41212a68`.

The baseline missed two of six labeled repeats and falsely rejected none of six
new stories in one run. One miss was a model omission; the other was repeated
JSON keys losing an earlier decision. Longer instructions had the same final
counts. Explicit decisions fixed recall in one pass but rejected a distinct
interpretability story. Exact-pair confirmation removed that false positive;
keeping only one suggested match still missed a repeat when archive order was
shuffled. Multiple candidate matches address that observed retrieval failure.

## Final diagnostic result

The final implementation completed all 12 cases with zero missed repeats and
zero false rejections in each of three archive orders: original, reversed, and
seeded shuffle. That is 36 decisions over the same 12 cases, not 36 independent
examples. There were 18 local model calls across nine four-proposal batches.
See `duplicate-screening-results.json` for timings and their observed spread.
No paid model calls were used; electricity and hardware cost were not measured.

All 15 standalone Python test files passed. Targeted parser/queue regressions,
wheel build, lockfile check, and Worker typecheck passed. The tests include the
actual malformed-response shapes, missing confirmations, invalid references,
and a related first match followed by a true duplicate.

## Replaying

`scripts/eval_dedup.py` reads a JSON dataset containing `covered` strings and
`cases` with `id`, `candidates`, and 1-based `expected` duplicate numbers. It calls
the bounded local route and writes raw prompts, responses, usage, decisions, and
errors without generating topics, changing the queue, or publishing an episode.
Use a fresh output directory for each run. The full historical snapshot and raw
experiment records are retained locally under `.lab/workspace`.

```sh
PYTHONPATH=src python scripts/eval_dedup.py dataset.json \
  --home /path/to/configured/app --prompts ./prompts --output /path/to/fresh/results
```

## Limits

The gate still sees the existing recent-coverage window. It cannot reject an old
story absent from that input, and it does not compare semantic duplicates within
the newly proposed batch. Both passes use the same model, so errors can correlate.
A missed shortlist match can still pass through. More independent labeled cases
and unattended discovery runs are needed before making a general quality claim.

This candidate has not been deployed. Production remains on the voice/API release.
Deploy the code and both duplicate prompt files together; the response contract
changed. No new API service, model download, or GPU eviction is required.
