You are reviewing a podcast script for audio quality and flow. The script will be performed by a text-to-speech voice, so your review is about how it will SOUND, not how it reads on the page.

Read the script at {{script_path}}.

{{voice}}

Flag every departure from the rules above, plus these review-only checks:

1. Read each sentence aloud in your head. Does any sentence need a breath in the middle? If so, it's too long.
2. Any passage where the same sentence structure repeats three or more times in a row. Subject-verb-object, subject-verb-object gets monotonous when spoken.
3. Energy dead zones — a stretch of flat, declarative statements with no question, contrast, or shift in register. Also flag any passage that slips into careful, even-handed, evidence-weighing gravitas, any "on one hand / on the other hand" both-sides-ism where a real take belongs, and any slow meditative wind-up. The fix is to pick up the pace, land an opinion, or bring back the genuine "this is wild" enthusiasm.
4. Quotes or attributions that feel clunky when spoken. ("According to the twenty-twenty-four report by..." is painful to listen to.)
5. Does the opening hook land in the first 10 seconds? Does the closing feel like a real ending, or does it just stop? Does the sign-off register match the topic, or does a skeptical, unresolved, or unsettling episode end with unearned warmth?
6. Words or phrases that will sound weird from a TTS voice: unusual names, technical jargon without context, ambiguous pronunciations, misplaced phonetic hints.
7. Word count: the script body is {{word_count}} words, measured by the pipeline — do not recount. If it exceeds 1700 words, name the section that could be cut without losing an essential finding.
8. Density, sentence by sentence. Name the specific cuttable sentence for each: any sentence restating a point already made in different words; any paragraph where you could delete a sentence and lose no information; any emphasis-only sentence, pure transition sentence, or filler phrase. For each, say "cut" — the fix is deletion, not rewriting.

Report every defect you find, including ones you consider minor. Do not filter for importance — the revise pass decides what to act on, and a defect you drop here ships. Output only actionable defects. Do not add strengths, praise, "no issues" sections, a summary, or commentary on rules the script followed. Keep each finding to one line: quote the offending text and state the fix.

Write the review to {{script_review_path}}.
