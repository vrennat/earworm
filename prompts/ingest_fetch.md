Fetch the article at {{url}} using WebFetch and extract its text, verbatim.

- Pull the main article only: its title and the full body prose, in order.
- Strip everything that is not the article itself: site navigation, page headers and footers, cookie and newsletter banners, share and subscribe buttons, author bios, related-article lists, comments, and ads.
- Do NOT summarize, paraphrase, shorten, or editorialize. Reproduce the author's words exactly. Keep the paragraph breaks. Keep the section headings as their own lines.
- If WebFetch returns truncated or partial content, fetch again and assemble the complete text. The goal is the whole essay, start to finish, with nothing dropped from the middle or end.

Write the result to {{out_path}}: the article title as a `# ` heading on the first line, then a blank line, then the body. Create parent directories if needed.
