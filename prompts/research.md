Produce a research brief for an Earworm episode, a substantive audio documentary for one narrator and a curious listener without assumed domain expertise.

Topic: {{topic}}
Today's date: {{date}}

Research the subject with the available web search and fetch tools. Find what is worth understanding and the evidence needed to understand it. An important explanation can earn its place without contradicting conventional wisdom. Investigate common assumptions where relevant; do not manufacture a debunk or a surprising finding quota.

Evidence:
- Prefer original research, government and institutional records, documented investigations, and experts speaking on the record. For technical claims, read the original methods and results rather than relying on an abstract or another article's summary. Record sample sizes, comparison conditions, measured outcomes, limits, and relevant funding.
- A company announcement is primary evidence of what the company announced, not independent proof that its product or claimed outcome works. Attribute announcements and accounts of decisions accurately. Find underlying data or independent corroboration before adopting promotional claims as established results. Apply the same distinction to advocacy reports and vendor white papers.
- Date the evidence and distinguish an event's date from a publication date. Explain when an older result is still relevant rather than presenting it as a new development.
- Tag every load-bearing finding: [strong] for well-supported evidence with methods appropriate to the claim; [limited] for a small or narrow study, a preprint, or industry-funded work without independent replication; [contested] for a supported disagreement; [reported] for an attributed account not independently verified. A publication venue alone does not establish reliability. Explain the particular limitation beside the claim.
- Fetch the sources needed for the key claims. If access fails, record precisely what you could read and which claims remain unverified. Do not imply that an abstract-only read checked a method or that a search snippet established a result.

Material for the episode:
- Gather documented actions, decisions, constraints, mechanisms, comparisons, and consequences when the sources supply them. Preserve a useful chronology and distinguish an observed causal link from a proposed explanation or a merely related event.
- An experiment or a technical idea can supply the material. A person, villain, scene, conflict, reversal, or historical arc is not required. Never invent dialogue, surroundings, motives, or a moment of discovery to make research resemble a scene.
- Include the context a listener needs to follow the strongest material. Note which related threads have enough evidence to develop and which would distract from it. Do not prescribe a stock opening, sequence of spoken sections, or moral.
- Record the exact spelling of proper names and technical terms. Include a reliable pronunciation source or verified pronunciation when available; identify uncertainty instead of inventing phonetics.

Keep this Markdown envelope so the pipeline can extract show notes:
- Begin with `# Report title`, replacing the title with this report's actual title.
- Follow it with a short factual summary in a blockquote, `> Summary text`.
- End with a `## Sources` heading and bulleted Markdown links, `- [Descriptive source title](https://source-url)`, using actual verified source titles and URLs.

Between the summary and source list, organize the evidence record, necessary context or chronology, and unresolved gaps as this subject needs. Keep source links and evidence tags beside the claims. The envelope is report metadata for show notes, not a required episode outline or sequence of spoken sections.

Return the complete report as your final response, without a preamble or a code fence. Gather enough depth for roughly eight to twelve minutes where the material supports it; do not pad a thin subject to fill time. Return a research report, not a script. The pipeline saves your response; do not request or use filesystem tools.

{{retained_evidence}}
