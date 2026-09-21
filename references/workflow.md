# Commands and local configuration

Run from the skill directory. Python 3.12; dependencies in requirements.txt. Remote requests follow HTTPS_PROXY when configured. Loopback Zotero requests explicitly ignore proxy variables. The actual host-agent decision is kept in a JSON file and logged, not computed by the tool.

## Inputs

claims.json is a list of `{claim_id, section_id, claim_text, citation_anchor, required_depth}`. Depth is `abstract` or `fulltext`. IDs must be unique. The project directory must initially be empty. Each project has project.json, claims.json, papers.jsonl and events.jsonl; this build uses claims.json instead of planned TSV to validate structured inputs consistently.

Decision files contain a list of `{paper_id, decision, decision_maker:"host_agent", reason, abstract_read, evidence:[{claim_id, required_depth, relation, reason}]}`. Relations are supports, qualifies, contrasts, context_only, unresolved. include requires at least one claim. Existing title/ID conflicts block inclusion. Decisions are all validated before saving.

If the daily library already contains duplicate same-DOI entries, the agent may explicitly select an existing canonical entry after inspecting complete titles and metadata: `bind --project <dir> --paper-id <P...> --item-key <key> --reason <reviewed reason>`. This validates same DOI and punctuation-normalized complete title and records the binding. It does not merge or delete existing items. Different-DOI or substantial title conflicts remain blocked.

```text
python scripts/lit2zotero.py discover --project <dir> --provider epmc --query <query> --pages 1
python scripts/lit2zotero.py discover --project <dir> --provider crossref --query <query> --pages 1
python scripts/lit2zotero.py decide --project <dir> --record <agent_decisions.json>
python scripts/lit2zotero.py resolve --project <dir> --paper-id <P...>
python scripts/lit2zotero.py attach --project <dir> --paper-id <P...> --file <user-provided.pdf>
python scripts/lit2zotero.py read --project <dir> --record <agent_reading.json>
python scripts/lit2zotero.py sync --project <dir>
python scripts/lit2zotero.py sync --project <dir> --apply
python scripts/lit2zotero.py handoff --project <dir>
```

Reading JSON: `{paper_id, decision_maker:"host_agent", summary, locators:[{pdf_page:1, excerpt:"actual short text"}]}`. Exact excerpt/page checks prevent fabricated locators, but do not replace agent inspection of the full required material. A changed PDF requires renewed reading; fulltext_available_not_read is not fulltext_read. Files in tests are software fixtures, not research evidence.

## Local writer choice

- `native`: install `dist/lit2zotero-local.xpi` via Zotero Tools → Plugins → Install from File. Package/source/config all remain here. `private/bridge.json` holds the local token; do not print or publish. Native operations are limited to this project's prefixed collection and PDF paths under the configured allowedRoot. The server rejects browser Origin/Referer and wrong tokens.
- `existing`: compatible with the already-installed zotero-write-endpoint v1.1.0. No extra plugin is needed for metadata. It reuses existing identities, preserves memberships and creates one initial managed note. It cannot update managed notes or attach local PDF files safely; those capabilities stay pending until native is available. Do not mislabel linked URLs as imported files.
- No cloud writer is configured. No arbitrary JavaScript or SQL interface is exposed by this skill.

Build the native XPI with scripts/build_bridge.py. This creates local credentials and an allowed directory under the current checkout; it does not edit any Zotero profile or install automatically. Install the generated XPI through Zotero's plugin manager. The XPI includes machine-specific settings and must not be redistributed.

## OA behavior and limits

The resolver uses existing Europe PMC PDF links and OpenAlex OA locations. OPENALEX_API_KEY is optional environment input. Unpaywall and arbitrary search engines remain agent-side fallbacks, not falsely advertised CLI providers. PDF parsing uses PyMuPDF; identity must be recognizable in first pages. Required inaccessible PDFs produce a precise manual_pdf_needed state. Files remain below 60 MB; large files require a reviewed adjustment. No paywall bypass.

No abstract is fabricated; original source abstract is kept. Full-text OCR/supplement reading is not automated in this first build; the agent must use suitable tools and record limitations. Version families, corrections and retractions require agent review; source notices are not assumed absent.

handoff readiness is a material/identity gate based on the agent's declared relationship. It is not an independent scientific endorsement or retraction audit. Before actual manuscript use, the host agent must finish those checks. The real pilot includes six broad abstract-level contextual claims; it does not authorize detailed method-parameter or mechanistic assertions from their abstracts.

## Writing safety

Use a single mutating CLI process per project. The native server serializes its write operations. The legacy compatibility API has no compare-and-swap protection, so avoid simultaneous manual edits during its short sync; use native for normal production. Never run restore/merge/delete endpoints automatically. Keep read errors and partial write status visible.

## Minimal environment

The .venv was installed only here. To recreate: `python -m venv .venv`, then `.venv/Scripts/python.exe -m pip install -r requirements.txt` with TEMP/TMP/PIP_CACHE_DIR pointing into this directory. No LLM API key is required: the host agent makes scientific decisions. `.env` is not auto-loaded; supply service credentials via environment explicitly.

## Required host-native web search

The host agent must actually use its native search and page-opening tools alongside structured scholarly APIs for each literature-search assignment. The Python CLI cannot call the host tool by itself; a standalone discover command is only the structured-retrieval part of the workflow. Cover relevant alternatives and limitations rather than only searching exact titles already chosen.

Record each actual search batch with:

```text
python scripts/record_web_search.py --project projects/my_paper --record native_web_search.json
```

The JSON object contains actor=host_agent, tool (actual tool name), query, scope, performed_at (ISO timestamp), status (completed/no_results/failed/unavailable), and results (title, url, optional opened_url and doi). failed/unavailable requires a reason. Include returned/opened URLs, not invented tool IDs. Records are host attestations; the validator checks format and links known DOI candidates, but cannot prove the browsing call happened. It does not change inclusion or reading states.

For newly discovered papers, obtain verified structured metadata using an exact DOI query such as Europe PMC `DOI:10.xxxx/yyyy`, then match the DOI/title and link to the web record. If that source lacks the paper, use Crossref and explicitly verify the identifier; a search snippet must never become a fabricated abstract. A paper without confirmed metadata stays pending. Keep a discovered preprint separate from its journal version until the host reviews that relationship.

Open relevant primary pages for identity, OA locations, methods, supplements and notices. Search engines are discovery tools, not inclusion arbiters. Opening HTML does not automatically mark fulltext_read; record actual reading with the established reading contract. Native-tool outages do not block useful API searches, but must remain visible as incomplete native coverage.
