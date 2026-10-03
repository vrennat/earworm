# Earworm archive audit, October 2, 2026

Earworm's strongest material explains a concrete system through an event, object, or decision. Its recent weakness is editorial selection: AI measurement and hidden-bottleneck questions dominate, and a commission can proceed even when the evidence needed to answer its central question was not retrieved. More energetic prose alone would preserve these problems.

## Evidence and method

- Production snapshot: `/Users/tanner/Developer/earworm/.lab/workspace/2026-10-02-editorial-audit/snapshot.json`, captured **2026-10-03 06:04:43 UTC**, or **October 2 at 23:04 Pacific**.
- Inventory: **159 topic rows, 141 episode rows, and 148 archived scripts**. Topic states were 143 done, 15 failed, and 1 pending. A done topic or an archived script is not, by itself, a published episode.
- Publication test: **140 episode rows have a non-null `published_at`**. Episode ID 111, topic 113, *Did Claude Actually Break Cryptography?*, has a null publication timestamp and is excluded from published counts. Publication here means the registry records publication; this audit did not verify feed delivery or listening-client state.
- The title/metadata census covers all 141 registry rows. The accompanying [classification CSV](2026-10-02-archive-classification.csv) preserves episode ID, topic ID, editorial date, publication timestamp, classification, and rationale. Its one unpublished row remains visible for reconciliation.
- **AI-led is a cross-cutting editorial classification, separate from configured A/B/C/D lanes.** AI model research, evaluation, deployment, economics, policy, and AI compute/power infrastructure count as AI-led. A technical subject such as SQLite or stock settlement does not count merely because it is technical. The reactor episodes count as AI-led because their questions explicitly center data-center demand. The general grid-resilience episode does not. Topic 54 concerns expertise transfer in general even though some sources discuss AI.
- Classification is a single-reviewer judgment based on the entire title census, original topic strings, and descriptions where titles are ambiguous. These are descriptive census counts, not estimates from a random sample; no sampling confidence interval applies. Different decisions at ambiguous category boundaries could change the counts.
- The close reading covers **15 complete script artifacts: 14 published scripts and 1 archive-only alternative**, spanning June 10 to October 1. Nine are dated September 5 or later. This is a deliberately selected, nonrepresentative qualitative sample, not a quality estimate for all episodes. Earlier local copies read for topics 2, 8, 16, and 26 were compared with the production snapshot; their script bodies match, with only the frontmatter report path differing.
- No audio listening, external source fact-check, factual accuracy rate, or model-quality experiment was performed. Findings below concern the text and its own research/review record.

## Breadth census

Among **134 published original editorial episodes**, **103 are AI-led (76.9%)** and **31 are other subjects (23.1%)**. Five imported AI-related source readings and one personal interview-preparation episode are excluded from that denominator.

| Editorial month | AI-led originals | Other originals | Imported readings | Personal | All published |
| --- | ---: | ---: | ---: | ---: | ---: |
| June | 6 | 16 | 5 | 1 | 28 |
| July | 55 | 12 | 0 | 0 | 67 |
| August | 25 | 0 | 0 | 0 | 25 |
| September | 16 | 3 | 0 | 0 | 19 |
| October through October 1 | 1 | 0 | 0 | 0 | 1 |
| Total | 103 | 31 | 5 | 1 | 140 |

Month uses the script/slug editorial date, not the UTC publication day. In publication order, **27 of the latest 30 episodes are AI-led (90%)**; **17 of the latest 20 are AI-led (85%)**. All 25 published August episodes are AI-led. Sixteen published episodes have an editorial date of September 5 or later; 13 are AI-led and three are other subjects.

The earlier archive includes music and cognition, astronomy, nuclear-waste communication, tacit knowledge, metrology, digital preservation, disease control, helium, and collective-action successes. Recent variety largely shifts between AI papers, AI policy, and AI infrastructure. Those can be substantively different, but they do not restore the broader curiosity visible in June.

## Complete-script sample

Numbers in this table are **topic IDs**, not episode IDs. Each link points to the captured production artifact.

| Editorial date | Topic ID | Script | Registry status | Close-reading finding |
| --- | ---: | --- | --- | --- |
| 2026-06-10 | 2 | [Why Do Songs Get Stuck in Our Heads? The Science of Earworms](/Users/tanner/Developer/earworm/.lab/workspace/2026-10-02-editorial-audit/production/done/scripts/2026-06-10-0002-why-do-songs-get-stuck-in-our-heads-the-science-of-earworms.md:7) | Published | Strong everyday question and concrete listener consequence; later sections become a study-by-study tour. |
| 2026-06-16 | 8 | [The Warning We Can't Write](/Users/tanner/Developer/earworm/.lab/workspace/2026-10-02-editorial-audit/production/done/scripts/2026-06-16-0008-how-do-you-warn-humans-10000-years-from-now-away-from-buried.md:7) | Published | Memorable physical failure anchors one durable question; several side threads and research-process asides dilute it. |
| 2026-06-27 | 16 | [The Cables Are Fine. The Ships That Fix Them Aren't.](/Users/tanner/Developer/earworm/.lab/workspace/2026-10-02-editorial-audit/production/done/scripts/2026-06-27-0016-a-few-hundred-undersea-fiber-optic-cables-carry-nearly-all-i.md:7) | Published | Repair ships give the story a tangible mechanism; governance and source caveats broaden the final third. |
| 2026-06-30 | 26 | [Code Got Cheap. Did Software?](/Users/tanner/Developer/earworm/.lab/workspace/2026-10-02-editorial-audit/production/done/scripts/2026-06-30-0026-ai-coding-agents-have-collapsed-the-cost-of-writing-code-whi.md:7) | Archive only | Archived alternative, not a current published episode; cheap-code versus review-cost framing repeats a familiar downstream-bottleneck payoff. |
| 2026-07-29 | 102 | [The Attack That Checked Out and the Story That Didn't](/Users/tanner/Developer/earworm/.lab/workspace/2026-10-02-editorial-audit/production/done/scripts/2026-07-29-0102-when-language-models-break-cryptography-anthropic-red-team-d.md:7) | Published | Specific public exchange gives the capability-versus-marketing argument a concrete scene; later evidence disputes multiply. |
| 2026-08-19 | 118 | [Fourteen Months Inside the Multi-Agent Experiment](/Users/tanner/Developer/earworm/.lab/workspace/2026-10-02-editorial-audit/production/done/scripts/2026-08-19-0118-the-coordination-paradox-in-multiagent-ai-anthropics-red-tea.md:7) | Published | Real conflicting engineering choices are engaging; experiment inventory and recurring caveats overtake the original decision. |
| 2026-09-05 | 135 | [SQLite as an Application File Format](/Users/tanner/Developer/earworm/.lab/workspace/2026-10-02-editorial-audit/production/done/scripts/2026-09-05-0135-sqlite-as-an-application-file-format-how-putting-a-database.md:7) | Published | Positive example: one support problem and one document example carry a causal explanation. |
| 2026-09-12 | 141 | [The Price of Being Caught](/Users/tanner/Developer/earworm/.lab/workspace/2026-10-02-editorial-audit/production/done/scripts/2026-09-12-0141-non-tech-measuring-how-much-of-a-citys-or-grids-resilience-a.md:7) | Published | Strong physical dependency loop; high number density and a final abstract institutional question weaken the landing. |
| 2026-09-18 | 145 | [The clearest recent agent-paper cluster is harness engineering, not model capability](/Users/tanner/Developer/earworm/.lab/workspace/2026-10-02-editorial-audit/production/done/scripts/2026-09-18-0145-the-clearest-recent-agent-paper-cluster-is-harness-engineeri.md:7) | Published | Clear harness mechanism, but three papers, many names and deltas become a narrated literature survey. |
| 2026-09-20 | 147 | [Infinite-Parameter LLMs and the Dilution Boundary](/Users/tanner/Developer/earworm/.lab/workspace/2026-10-02-editorial-audit/production/done/scripts/2026-09-20-0147-infinite-parameter-llms-arxiv-260918842-a-hypernetwork-turns.md:7) | Published | Mechanism is explainable; final script narrates a truncated source retrieval. |
| 2026-09-21 | 148 | [Anthropic's Frontier Red Team and the baseline problem in tactical evaluations](/Users/tanner/Developer/earworm/.lab/workspace/2026-10-02-editorial-audit/production/done/scripts/2026-09-21-0148-anthropics-frontier-red-team-benchmarked-tactical-intelligen.md:7) | Published | Published despite having only a title/index entry; listener gets generic evaluation requirements rather than findings. |
| 2026-09-22 | 149 | [SoL-Pi and the Token-Efficiency Constraint on Recursive Self-Improvement](/Users/tanner/Developer/earworm/.lab/workspace/2026-10-02-editorial-audit/production/done/scripts/2026-09-22-0149-sol-pi-arxiv-260920519-recursively-scales-auto-research-loop.md:7) | Published | Useful mechanisms buried in a long inventory; exact-table access problems remain in the spoken script. |
| 2026-09-25 | 157 | [How a $2 Trillion Settlement Shock Happens in Hours: What Actually Settles a US Stock Trade Today Under T+1](/Users/tanner/Developer/earworm/.lab/workspace/2026-10-02-editorial-audit/production/done/scripts/2026-09-25-0157-how-a-2-trillion-settlement-shock-happens-in-hours-what-actu.md:7) | Published | Concrete clearing mechanism and Robinhood example; title promises a $2 trillion shock that the body never substantiates. |
| 2026-09-30 | 161 | [The Interconnection Queue is Now the Real Bottleneck for Data-Center Power](/Users/tanner/Developer/earworm/.lab/workspace/2026-10-02-editorial-audit/production/done/scripts/2026-09-30-0161-the-interconnection-queue-is-now-the-real-bottleneck-for-dat.md:7) | Published | Concrete regulatory sequence explains an incumbent advantage; source gaps remain audible. |
| 2026-10-01 | 162 | [Follow the Money Behind a Restarted Reactor: Constellation's $1.6 Billion Three Mile Island Relaunch](/Users/tanner/Developer/earworm/.lab/workspace/2026-10-02-editorial-audit/production/done/scripts/2026-10-01-0162-follow-the-money-behind-a-restarted-reactor-constellations-1.md:7) | Published | Replays the preceding episode’s core event and waiver; unavailable contract cannot support its advertised risk-allocation answer. |

## Strongest findings

### 1. Research failure is being converted into the episode's premise

The September 21 script says, “The methods, the sample sizes, the design of the benchmark, and the conclusions remain unseen,” and later, “The only verified fact” is that the lab announced a measurement. See [topic 148](/Users/tanner/Developer/earworm/.lab/workspace/2026-10-02-editorial-audit/production/done/scripts/2026-09-21-0148-anthropics-frontier-red-team-benchmarked-tactical-intelligen.md:13) and [topic 148](/Users/tanner/Developer/earworm/.lab/workspace/2026-10-02-editorial-audit/production/done/scripts/2026-09-21-0148-anthropics-frontier-red-team-benchmarked-tactical-intelligen.md:33). The middle of the episode fills that gap with general statements about expert baselines.

This was an editorial decision, not just an overlooked sentence. Its [research review](/Users/tanner/Developer/earworm/.lab/workspace/2026-10-02-editorial-audit/production/runs/2026-09-21-0148-anthropics-frontier-red-team-benchmarked-tactical-intelligen/review.md:25) explicitly acknowledges “a title, a date, a team, and a one-sentence mandate” and then commissions an episode about the evaluation genre. The evidence access problem becomes a claim about what a discipline has not established.

**Change implied:** require a viable answer or an alternative story supported by evidence before commissioning. A missing paper body is a reason to defer, replace, or repair research. It should not automatically become an episode about missing evidence.

### 2. Nominally different questions can replay the same episode

September 30 and October 1 both open with the September 2024 Constellation announcement, describe the same reactor, Microsoft contract, delayed transmission, Eddystone rights transfer, and FERC waiver. Compare [September 30 opening](/Users/tanner/Developer/earworm/.lab/workspace/2026-10-02-editorial-audit/production/done/scripts/2026-09-30-0161-the-interconnection-queue-is-now-the-real-bottleneck-for-dat.md:7) with [October 1 opening](/Users/tanner/Developer/earworm/.lab/workspace/2026-10-02-editorial-audit/production/done/scripts/2026-10-01-0162-follow-the-money-behind-a-restarted-reactor-constellations-1.md:7). The latter asks who bears delay risk, but its necessary contract terms are unavailable.

The October 1 [review already spotted the repeat](/Users/tanner/Developer/earworm/.lab/workspace/2026-10-02-editorial-audit/production/runs/2026-10-01-0162-follow-the-money-behind-a-restarted-reactor-constellations-1/review.md:17). It tried to distinguish the new episode through contract-level risk allocation, even though that was the unavailable evidence. The resulting script repeats the known event to support a different advertised question it cannot resolve.

**Change implied:** compare the central event, mechanism, decisive evidence, and listener payoff, alongside question wording. Permit revisiting a subject when new evidence or a materially different explanation earns it. A new abstract question attached to the same causal sequence is insufficient.

### 3. Narrated literature surveys flatten promising mechanisms

The September 18 harness episode has a useful central idea. But the listener must track three research teams, three frameworks, benchmark names, model names, and multiple exact gains. [One paragraph](/Users/tanner/Developer/earworm/.lab/workspace/2026-10-02-editorial-audit/production/done/scripts/2026-09-18-0145-the-clearest-recent-agent-paper-cluster-is-harness-engineeri.md:29) introduces a task count, completion rate, two comparative gains, three model names, and a token-reduction claim. [Another paragraph](/Users/tanner/Developer/earworm/.lab/workspace/2026-10-02-editorial-audit/production/done/scripts/2026-09-18-0145-the-clearest-recent-agent-paper-cluster-is-harness-engineeri.md:37) adds four latency percentages across two benchmarks. The SoL-Pi episode similarly enumerates four mechanisms before its benchmark accounting.

This is descriptive evidence of listening burden, not a measured attention effect. The current scripts often spend their detail budget proving that the research was read, instead of helping the listener build one usable explanation.

**Change implied:** choose one worked example or failure/recovery sequence as the spine. Keep the numbers that establish the mechanism or change the conclusion. Move source inventory and supporting benchmark detail to show notes rather than deleting the qualifications that actually matter.

### 4. Tool access limitations survive as spoken research notes

September 20 says, “The final multi-turn session benchmarks were cut off in the retrieved copy of the text” ([topic 147](/Users/tanner/Developer/earworm/.lab/workspace/2026-10-02-editorial-audit/production/done/scripts/2026-09-20-0147-infinite-parameter-llms-arxiv-260918842-a-hypernetwork-turns.md:57)). September 21 narrates guessed URL failures ([topic 148](/Users/tanner/Developer/earworm/.lab/workspace/2026-10-02-editorial-audit/production/done/scripts/2026-09-21-0148-anthropics-frontier-red-team-benchmarked-tactical-intelligen.md:13)). September 22 says table values are “partially unobtainable” and “specific linear coefficients” remain unresolved ([topic 149](/Users/tanner/Developer/earworm/.lab/workspace/2026-10-02-editorial-audit/production/done/scripts/2026-09-22-0149-sol-pi-arxiv-260920519-recursively-scales-auto-research-loop.md:39)).

A substantive evidence limit belongs in the story when it changes the answer. The crawler's failure or truncation is a production issue to resolve or use to narrow the commission. It is weak listener material in its own right, and it should not imply that the original publication omitted something that the production system failed to retrieve.

**Change implied:** keep an explicit distinction between a source's stated limitation, an unpublished artifact, and this run's retrieval failure. Route the last category to repair or deferral.

### 5. Final claims and titles can outrun the narrowed commission

The October 1 [commission says](/Users/tanner/Developer/earworm/.lab/workspace/2026-10-02-editorial-audit/production/runs/2026-10-01-0162-follow-the-money-behind-a-restarted-reactor-constellations-1/review.md:27) “Do not attempt to explain 'who bears delay risk' as a concluded fact.” Its final paragraph nevertheless generalizes that “the utility carries the schedule risk,” immediately after saying the actual allocation remains sealed ([topic 162](/Users/tanner/Developer/earworm/.lab/workspace/2026-10-02-editorial-audit/production/done/scripts/2026-10-01-0162-follow-the-money-behind-a-restarted-reactor-constellations-1.md:49)). This is an internal mismatch visible without independently fact-checking the energy story.

The September 25 title promises a “$2 Trillion Settlement Shock.” The full body instead opens with a $7.1 billion modeled shortfall, describes a clearing mechanism, and later gives a $5.55 trillion peak transaction value. The title's $2 trillion claim is never substantiated in the script. See [title and opening](/Users/tanner/Developer/earworm/.lab/workspace/2026-10-02-editorial-audit/production/done/scripts/2026-09-25-0157-how-a-2-trillion-settlement-shock-happens-in-hours-what-actu.md:1).

**Change implied:** final review should verify that the title, opening promise, and closing answer are supported by the same surviving evidence after revision. A qualification should change the conclusion when it removes the promised basis for that conclusion.

### 6. Topic variety needs different payoffs as well as different domains

The sampled material repeatedly lands on a hidden bottleneck, an incentive failure, or a warning that an impressive measurement does not establish what the audience assumes. Those are useful forms, but repeated exposure makes new subject matter feel familiar. The title census includes *Grading the Grader*, *Grading a Mind That's Grading You Back*, *The Fixer Grades Its Own Test*, and *Grading Its Own Homework*. Different underlying papers can still promise the same kind of realization.

**Change implied:** broaden the commission beyond exposure and correction. Include explanations of how a technique works, why a successful design survives, what skilled practice feels like, how an ordinary object acquired its form, and how a system actually recovered from failure. Underused lanes visible in this archive include music/cognition, materials and manufacturing, ecology/biology outside AI discovery, standards and measurement, and ordinary civic systems. These are search directions, not source-verified ready-to-publish topics.

## Positive example: preserve the SQLite episode's method

The SQLite script starts with attributable support calls: the application got blamed when its separate database server failed. It then follows one familiar object, a presentation, through increasingly capable file designs. Each step changes a concrete behavior: save one slide, retain an old version, recover an interrupted update. See [opening](/Users/tanner/Developer/earworm/.lab/workspace/2026-10-02-editorial-audit/production/done/scripts/2026-09-05-0135-sqlite-as-an-application-file-format-how-putting-a-database.md:7), [first design](/Users/tanner/Developer/earworm/.lab/workspace/2026-10-02-editorial-audit/production/done/scripts/2026-09-05-0135-sqlite-as-an-application-file-format-how-putting-a-database.md:17), [second design](/Users/tanner/Developer/earworm/.lab/workspace/2026-10-02-editorial-audit/production/done/scripts/2026-09-05-0135-sqlite-as-an-application-file-format-how-putting-a-database.md:19), and [qualification](/Users/tanner/Developer/earworm/.lab/workspace/2026-10-02-editorial-audit/production/done/scripts/2026-09-05-0135-sqlite-as-an-application-file-format-how-putting-a-database.md:23). The proposed-editor limitation is stated precisely where it matters.

The value is not simply that this script is shorter or non-AI. It has one causal path, a specific consequence, and a grounded ending. The nuclear-warning episode's kitty-litter incident and the cable episode's repair ships show related strengths in earlier material. Preserve these concrete anchors while improving selection and the final promise-to-evidence check.

## Limits and next validation

This pass establishes the publication mix and supplies inspectable examples of failure modes. It does not establish that a revised chain improves listening quality. A useful next check is a small, fixed comparison of scripts commissioned under old and revised rules from the same evidence packets, including a strong source packet, an inaccessible-source packet, and a near-duplicate topic. Evaluate the promised question, supported answer, narrative continuity, and omissions before paying for narration. Listen to matched text if evaluating voices or audio delivery.
