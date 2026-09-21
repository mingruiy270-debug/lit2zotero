# Word handoff

`citation_handoff.tsv` is an evidence/identity index, not a Word field file. It includes claim/section anchors, exact title, DOI, item key, actual Zotero URI, local availability and evidence readiness. Scope of an abstract-level claim remains limited to that abstract.

Read the installed `.agents/skills/third-party/zotero-word-citations-skill/SKILL.md` in the parent workspace before any Word action. It requires connected word_mcp_live and a separate output document. This skill does not install, invoke or bypass Word automation.

1. Confirm actual Zotero library and item key after sync. A local-only `users/local/...` URI is valid Zotero identity but the installed citation script may assume an account library. Check that boundary before use; do not fabricate users/0 as a public URI.
2. Use `【exact complete title】` placeholders at actual authorized sentence positions. Adjacent placeholders represent a citation group.
3. Run existing match_titles.py on the saved document copy, generating actual occurrence ranges, mapping and resolved_items.json. Only exact_unique, normalized_unique or duplicate_same_doi_resolved can pass. Reconcile item key/DOI against this handoff; fuzzy or different-DOI matches are unresolved.
4. Run this skill's scripts/prepare_word_mapping.py with --handoff citation_handoff.tsv --mapping the existing matcher output directory --out a new mapping-bound directory. It re-reads the explicitly reviewed item key, actual library ID, title, DOI and CSL. Use the THREE files in mapping-bound (mapping TSV, occurrence TSV, resolved_items.json) for insertion. This is necessary because the older matcher may choose another same-DOI duplicate; do not silently replace a reviewed binding with its automatic preference. The adapter edits only mapping files, never DOCX. Ambiguous or unread handoff entries fail.
5. Use the existing insertion script's explicit --apply, representative subset first. Generate real refreshable ADDIN fields; do not substitute static numbers or .bib keys.
6. ZoteroRefresh, bibliography, repeated citation checks and compare_content must pass. Also compare the refreshed citation URIs with the reviewed handoff. Field-code presence alone is not a valid test. Later edits to a linked manuscript use word_live_* only.

No Word round trip has happened merely because `handoff` succeeds. Report the two outcomes separately. BBT is optional; no BBT changes are made here.
