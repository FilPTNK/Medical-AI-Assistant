# Website and drug directory research

Reviewed 3 November 2026. This note covers the first release of the Vietnamese-language Fil website and the separate catalog publishing workflow.

## Reference sites and interaction design

| First-party reference | Observed pattern | Application to Fil |
| --- | --- | --- |
| [SAT Prep AI vocabulary list](https://www.satprepai.app/vocab-list) | A focused page with one heading, short introduction, prominent text search, All and six alphabetical ranges. Flashcards are a separate mode. | Put drug search and All / A–D / E–H / I–L / M–P / Q–T / U–Z above a list of entries. Keep generic names prominent and display the matching alias or brand for disambiguation. Open a dedicated monograph view with visible source details. |
| [SAT Prep AI homepage](https://www.satprepai.app/) | Compact navigation, a benefit-led hero with a primary action, then named tools grouped in a directory. | Give Fil its own front door. Lead with direct drug lookup and offer chat as a peer destination. Keep the existing chat session experience inside its own route. |
| [VN Exams homepage](https://vn-exams.com/) | The headline names a concrete task and the primary action opens the underlying question bank. Short labels identify the available tools. | Use familiar Vietnamese action labels and an immediate path from the homepage search field to matching entries. Keep account controls secondary to navigation and give administrators a dedicated management page. |

Rebuild the hierarchy and interaction patterns in the existing React/Vite app with Fil’s own identity. Use native links for route changes and native buttons for alphabet filters. Give the input a persistent accessible label, expose the active filter and result count, and keep focus on the search field while results update. The W3C specifically discusses announcing a search result count without moving focus. Review reflow, visible focus, contrast and target size against WCAG 2.2. [W3C status messages](https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html) · [WCAG 2.2](https://www.w3.org/TR/WCAG22/)

The reference interfaces establish the page structure. A flashcard reveal conceals details by design, while Fil’s reference workflow benefits from visible indications, dosing, contraindications and warnings once a monograph opens. Separate routes let a physician return to the directory or share an entry without going through the chat flow.

## Skill setup and use

- UI/UX Pro Max is already installed on this machine at `~/.codex/skills/ui-ux-pro-max`. The `SKILL.md` and local Python search script are available. The package supplies design and accessibility guidance during development and has no application runtime role.
- The maintainer documents `npm install -g ui-ux-pro-max-cli` followed by `uipro init --ai codex` from the repository for a fresh setup. Its CLI supports `--dry-run` to inspect the write plan. Review the package and expected version before installing on another machine. The maintainer identifies the older `uipro-cli` package as stale. [UI/UX Pro Max upstream installation](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill#installation)
- Codex discovers project skills in `.agents/skills`. A shared setup can commit a reviewed copy of a skill there. A personal installation can use the documented user skill directory. Check the skill manifest and included scripts before executing them. [OpenAI skill locations and structure](https://learn.chatgpt.com/docs/build-skills)
- For this feature, use UI/UX Pro Max’s `--design-system` mode for the clinical directory and `--stack react` for React implementation details. Use the installed frontend-design skill to translate those results into typography, color and layout decisions. Inspect the actual site at desktop and phone widths because the skill’s recommendations do not verify rendering or keyboard operation.

## Local corpus observations

The local workspace contains three generated chunk files. These files are ignored by Git, so a fresh checkout requires the configured source data or an administrator import.

| Local file | Chunk rows | Distinct raw headings | Reused chunk IDs |
| --- | ---: | ---: | ---: |
| `DTQGVN-2022-Q1.json` | 7,144 | 352 | 39 |
| `DTQGVN-2022-Q2.json` | 7,638 | 376 | 0 |
| `THUOC-BIET-DUOC-VA-CACH-SU-DUNG.pdf.json` | 18,708 | 3,608 | 695 |

The counts measure local parser output. Q1 includes an OCR heading beginning with “chứa artemether” and the brand book has six rows with the placeholder `UNKNOWN_DRUG`. Several distinct paracetamol fragments share a section type and printed page. Use the original source, monograph identity, section and fragment order together to distinguish records. Keep printed and PDF page coordinates separate. Q2 opens its ibuprofen entry at printed page 885 and records PDF index 6. [Project document handling](../backend/documents.py) · [Project formulary parser](../backend/dtqg_parser.py) · [Project source inventory](../README.md)

Vietnam’s national formulary is the natural initial reference for this project’s audience. The Đồng Nai Department of Health identifies the Ministry of Health’s decision issuing the third edition. Keep brand-book excerpts and administrator-supplied records identifiable by their own sources. NLM’s RxNorm illustrates the distinction between a generic ingredient, brand, strength and dose form, and its published scope is the United States. DailyMed is U.S. labeling submitted to FDA. NLM publishes that labeling without prior review. [Đồng Nai Department of Health notice](https://syt.dongnai.gov.vn/vi/van-ban/detail/V-v-trien-khai-Quyet-dinh-so-3453-QD-BYT-ve-viec-ban-hanh-Duoc-dien-viet-Nam-V-Ban-bo-sung-va-Quyet-8260/?download=1&id=2) · [RxNorm model and scope](https://www.nlm.nih.gov/research/umls/rxnorm/overview.html) · [DailyMed source scope](https://dailymed.nlm.nih.gov/dailymed/about-dailymed.cfm)

## Deterministic retrieval

1. Read structured records once and construct a small directory of IDs, original display names, synonyms, brands and optional class or ATC metadata. Keep the longer monograph sections in a separate detail payload. For a directory of hundreds to a few thousand entries, client-side filtering on the small index can respond on each keystroke. The database or local corpus remains the source of record. If response size or rendering becomes measurable at larger scale, use bounded server-side results and benchmark an indexed SQLite prefix or trigram search. [SQLite FTS5](https://www.sqlite.org/fts5.html)
2. Normalize lookup keys and queries consistently. Fold accents, handle Vietnamese đ explicitly, collapse whitespace, and compare case-insensitively. Preserve the original names and section text for display. Unicode normalization supports canonical equivalence and the project already has Vietnamese-specific folding and a reviewed alias lexicon. [Unicode normalization](https://unicode.org/reports/tr15/) · [Project text folding](../backend/text_fold.py) · [Project drug aliases](../backend/drug_alias.py)
3. Rank exact generic and explicit alias matches before prefix and substring matches, then order ties consistently. Apply alphabet ranges to the folded generic name and expose an All state. A shared alias should yield separate candidate entries with their generic identity and formulation when present. The FDA documents medication errors from name confusion. Similar spelling may support a visible suggestion that requires an explicit selection. [FDA drug name review](https://www.fda.gov/drugs/fda-drug-info-rounds-video/drug-name-review)
4. On selection, return stored section text and provenance without asking an LLM to write a summary. Show the source title, volume and printed page where available and link to the source coordinate when a viewer exists. Keep missing fields explicit and avoid deriving a strength, indication or dosage from another record. Keep plain text and source metadata separate in the data model.

## Admin publishing

Reuse the server’s administrator check on every upload endpoint. A different route and menu provide separation for the operator, while enforcement belongs on the server. Permit only CSV and JSON, impose byte and record limits, and check actual encoding, structure and field types. Use UTF-8 and accept a UTF-8 BOM when reading common spreadsheet exports. Use a CSV parser that handles quoted commas and multiline cells. For JSON, enforce the agreed record schema and report duplicate keys or invalid records explicitly. Render imported values as text and allow only valid HTTP(S) source links when a link is present. [Project administrator check](../backend/main.py) · [OWASP authorization](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html#validate-the-permissions-on-every-request) · [OWASP file upload](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html) · [Python CSV](https://docs.python.org/3/library/csv.html) · [Python JSON](https://docs.python.org/3/library/json.html)

Use a stable ID to distinguish a new entry from an update and preserve identity when aliases or display names change. Detect duplicate IDs in a batch. Validate all rows before publishing and report a row or record number when the file needs correction. Publish data and index changes together using a transaction for database storage or one atomic snapshot replacement for file storage. Concurrent readers should see either complete version. After success, refresh the directory’s data so the first lookup after publication reflects the new records. [SQLite transaction semantics](https://www.sqlite.org/lang_transaction.html)

## Acceptance checks

- The homepage enters the drug directory directly and chat opens from its own URL.
- Search works with uppercase and lowercase, accents and no accents, an explicit synonym, a known brand, alphabet filtering and an unknown query.
- A name shared across source records stays distinguishable. Paracetamol is a useful source check because the local Q2 parser output has several fragments with repeated section labels and printed pages.
- Compare displayed section text, drug identity, units and source pages with the imported row or original scan. Correct retrieval establishes that the site returns the intended record faithfully. Source accuracy also depends on OCR and editorial review.
- Verify a normal user and an unauthenticated request cannot publish, a failed import leaves existing records available, and the next successful lookup reflects a valid CSV or JSON upload.
