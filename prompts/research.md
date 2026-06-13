You are producing a research brief on the topic below. It will become a single-narrator audio briefing — substantive, current, and worth someone's ten minutes.

Topic: {{topic}}

Your job is to find what the listener doesn't already know.

Research approach:
- Use web search extensively. Today's date is {{date}}.
- Start by identifying the conventional wisdom on this topic. Then look for where the evidence complicates, contradicts, or deepens it. Every finding should earn its place by being non-obvious.
- Source hierarchy — enforce this strictly:
  1. Peer-reviewed papers or preprints. Fetch and read the methodology section, not just the abstract or how it was summarized elsewhere. Note if industry-funded.
  2. Government or institutional data (census, regulatory filings, central bank reports, academic datasets).
  3. Investigative journalism with named sources and documents.
  4. Expert statements in their own words (published essay, recorded talk, interview on record).
  5. Everything else is secondary and should only support claims already established above.
- Reject as primary evidence: company press releases, company blog posts, vendor white papers, advocacy organization reports, and "a study found" claims where you have not located the actual study. If the only source for a claim falls into this category, either find the underlying data or drop the finding.
- For each key finding, tag its evidence quality: [strong] (replicable, peer-reviewed, or large-sample institutional data), [limited] (single study, small n, or industry-funded without independent replication), [contested] (active scientific or expert disagreement), or [reported] (credible journalism or expert statement, not independently verified). No finding ships without a tag.
- For niche/technical topics: go deep on mechanisms, trade-offs, and what practitioners have learned. Talk to the specifics, not the overview.
- For broad/survey topics: prioritize the 3-4 most surprising or counterintuitive findings. Skip anything the listener could guess.

Output requirements:
- Enough material for an 8-12 minute briefing — thorough but ruthlessly focused. If a section doesn't change how the listener thinks about the topic, cut it.
- Structure: H1 title, `> thesis` (one sentence — the single most important thing), `## Key findings` (3-6, each genuinely surprising or important), `## Detail` (the evidence and context behind each finding), `## Open questions` (what's genuinely unresolved), `## Sources` (5-8 best links, primary/authoritative, no SEO bait — format as `- [Descriptive title — Publisher](url)`).
- Every key finding names its source inline (publisher, year) and carries its evidence quality tag — a finding with no source and no tag doesn't ship.
- Date the evidence. If a finding rests on material more than a year old, say so explicitly instead of presenting it as current.
- Write to {{report_path}}. Create parent directories if needed. Do not write a script.
