You are preparing a pre-written essay to be read aloud by a text-to-speech voice. This is NOT a rewrite. The author's argument, structure, voice, and length stay intact. Your only job is to remove what breaks when read aloud and fix pronunciation traps. When in doubt, keep the original wording.

Read the source text at {{source_path}}.

Preserve the content:
- Keep every section and every paragraph. Do NOT summarize, condense, shorten, or drop material. The output should be about as long as the input. A long essay makes a long script. That is correct, not a problem to fix.
- Keep the author's own sentences and word choices wherever they already read aloud cleanly. Edit surgically, not stylistically. You are not making it sound like a different writer.

Remove or rewrite reading-only artifacts (anything that assumes eyes on a page):
- References to visual elements: "as shown in the figure below", "see the chart", "the table above", "(pictured)", figure and table numbers. Drop them, or restate the point in words if the sentence depends on it.
- Footnote and endnote markers, and the notes themselves. If a note carries a load-bearing point, fold it into the sentence as a brief aside. Otherwise cut it.
- Inline hyperlinks and bare URLs. Keep the link's anchor text as plain words. The source is listed in the show notes, so you can drop "see https://..." entirely.
- Markdown and layout syntax: headings, bullets, numbered lists, block quotes, bold and italic and code marks, horizontal rules. Turn a heading into a short spoken transition or just a paragraph break. Turn a bulleted list into flowing sentences.
- Cross-references like "in Section 3 we saw" become "earlier" or "later", or get cut.

TTS-aware writing (the voice reads exactly the characters you write):
- No em-dashes, colons, ellipses, or parentheses for pauses or asides. The voice runs straight through them and slurs the words together. Use a comma for a brief pause, a period for a full stop. Set an aside off with commas, or give it its own sentence.
- Spell numbers as spoken: "twenty twenty-five", "ten times", "about forty percent". Convert symbols to words: %, $, &, =, and so on. Years, dates, and large numbers all spelled out.
- Write acronyms in standard form (AI, API, GDP). A downstream normalizer handles pronunciation, so do NOT letter-space them yourself. The first time an acronym carries meaning, expand it in words, then use the short form after.
- On first mention of any non-English name, uncommon surname, or non-obvious pronunciation, add a phonetic hint in square brackets: "Dario Amodei [ah-mo-DAY]". Use simple phonetic spelling. Common English names (John, David, Sam) don't need one.
- New paragraph at each real topic shift; each break is an audible pause. At the two or three MAJOR section pivots, put a line containing only `---` between paragraphs to cue a longer beat. Use it sparingly. Paragraph breaks alone handle minor shifts.

You may, lightly: if the essay opens cold, add a single short spoken sentence at the top naming what this is, for example the title and that it is an essay by its author. {{author_note}} One sentence. Do NOT add a summary, an outro, opinions, or commentary of your own anywhere else. You are reading the author's work, not hosting a show about it.

Write the finished spoken script — body only, no front matter — to {{out_path}}. Create parent directories if needed.
