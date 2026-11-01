# Rebuild the assistant around cited pages

The redesign should go in this order. Make every chatbot claim open the exact page of the source PDF with the passage highlighted. Strip the app down to three large, labelled tabs on a calm NHS-style palette. Then upgrade retrieval: switch the embedding model and add a reranker. On the frontend, React 18 sets one hard limit. **react-pdf 11 requires React 19**, so the choices are pinning react-pdf **10.5.0** or wrapping **pdfjs-dist's own `PDFViewer` + `PDFFindController`**. The second is the better choice, because PDF.js already does diacritic-aware search for Vietnamese. On the backend, the current multilingual-e5-small should give way to **BAAI/bge-m3**, an MIT-licensed model that does well on the Vietnamese VN-MTEB benchmark. A cross-encoder reranker comes back: **AITeamVN/Vietnamese_Reranker** or **bge-reranker-v2-m3**. Highlight rectangles are computed when each book is ingested and stored with each chunk. For content, the lowest-risk Vietnamese source is the Ministry of Health's *Hướng dẫn chẩn đoán và điều trị* (diagnosis and treatment guidelines), because official state documents are excluded from copyright. Next come WHO (CC BY-NC-SA 3.0 IGO) and openFDA/DailyMed (CC0/public domain) for drugs. NICE, MSD Manuals, UpToDate and BNF must stay out of the index. For an older doctor, the evidence (WCAG 2.2, NHS, NN/g's studies of users aged 65+) supports the same choices: 18–20px body text, 44–48px targets, one blue accent, red only for danger, no icon-only buttons, and no intro screen.

## The citation-to-highlight flow is the product

The pattern that works is the one NotebookLM documents. Clicking a citation number "immediately takes you to the original quote in the source" ([NotebookLM](https://support.google.com/notebooklm/answer/14290935)), and the source viewer "auto-scroll[s] to the location of the quoted text" ([NotebookLM help](https://support.google.com/notebooklm/answer/14276569?hl=en)). Elicit shows supporting quotes in a fixed side panel next to the answer ([Elicit](https://email.elicit.com/deliveries/dgTd9ggDAKHze6DzewGRV6Mar1nmdWdNl_mKLCI=)). A survey of citation patterns gives four rules: offer both a hover preview and a full click-through, cite exact passages for factual claims, say plainly when a source cannot be located, and keep the citation metadata consistent. It also warns that citations make AI output look more authoritative than it is ([shapeof.ai](https://www.shapeof.ai/patterns/citations)). Users of general chatbots already ask for exactly this click-to-highlight behaviour ([OpenAI community](https://community.openai.com/t/when-only-one-citation-is-used-in-a-chatgpt-response-clicking-the-source-number-should-still-highlight-the-associated-part-of-the-text-for-clarity-and-consistency/1259767)).

Here is how that works for this doctor:

1. **Citation chip.** The chip names the source rather than showing a bare number: `[1] Dược thư · tr. 123` (Dược thư = the national drug formulary; tr. = page). It is a tap target of at least 44×44 px.
2. **Preview.** Tapping the chip opens a popover on desktop or a bottom sheet on mobile. It shows the quoted passage, the book title and edition, and two large labelled buttons: **"Mở sách tại trang này"** ("Open the book at this page") and **"Hỏi về tài liệu này"** ("Ask about this document").
3. **Split view.** Opening the book splits the screen on desktop: chat about 40%, PDF about 60%. On a tablet or phone the PDF goes full-screen with a sticky header showing a back button, the title and "Trang 123 / 800" (page 123 of 800).
4. **Highlight.** The passage gets a yellow highlight at about 40% opacity with a 2px outline, and one short pulse that respects `prefers-reduced-motion`.
5. **Viewer controls.** Large zoom buttons, and a **"Về đoạn trích dẫn"** ("Back to the cited passage") button that re-centres on the passage after the doctor scrolls away.
6. **Honest fallback.** If the passage cannot be located, for example on a scanned page with no text layer, the right page still opens with a banner reading "Không tìm thấy vị trí chính xác — đoạn trích dẫn hiển thị bên dưới" ("Exact location not found — the cited passage is shown below"), followed by the chunk text.
7. **Ask about this document.** This button attaches a visible, removable chip above the chat input, for example "Dược thư (tr. 120–130)". Retrieval is then limited to that `book_id`, with a boost for chunks near the cited page.

Steps 1–3 are the pattern from the sources above. The fallback banner and the scoped chat follow the "state missing sources clearly" and source-scoping practices. The pixel sizes are a synthesis of accessibility guidance, not a study of clinicians.

To make this work, each citation the backend returns needs these fields:

- `book_id`
- `page`: the 1-based physical page index. Show the printed page label as well when it differs.
- `quote`: a short quote
- `chunk_text`
- `rects`: normalised 0–1 coordinates; may be empty
- `match_confidence`: lets the frontend choose between highlighting and the fallback banner

**Compute the highlight rectangles at ingest time, and use frontend search only as a fallback.** At ingest:

1. Normalise the chunk text and the page's words to NFC. Build a match key (NFKC, lowercase, collapsed whitespace, soft hyphens removed, line-end hyphens rejoined) that **keeps the diacritics**, because Vietnamese tone marks distinguish words.
2. Get the page's word boxes with PyMuPDF's `page.get_text("words")`, which returns each word's bounding box with block, line and word numbers ([PyMuPDF](https://pymupdf.readthedocs.io/en/latest/app1.html)).
3. Fuzzy-align the chunk's first and last ~12 tokens against the page text (for example with `rapidfuzz`).
4. Merge the matched word boxes into line rectangles. Store rectangles for both pages when a chunk crosses a page break.

When `rects` is empty, the viewer falls back to PDF.js find. `PDFFindController` NFD-normalises both the text and the query "because the diacritics in the text or in the query can be composed or not". It also rejoins line-end hyphens, and with `matchDiacritics` on, the tone marks must match ([pdf.js source](https://raw.githubusercontent.com/mozilla/pdf.js/master/web/pdf_find_controller.js)). Set `matchDiacritics: true`; otherwise "bệnh" also matches "benh". Search for a distinctive 6–10 word phrase, not the whole chunk. The stock viewer's `#page=N&search=…&phrase=true` URL hash is implemented in the code ([pdf_link_service.js](https://raw.githubusercontent.com/mozilla/pdf.js/master/web/pdf_link_service.js)), but only `#page` is officially documented ([PDF.js wiki](https://github.com/mozilla/pdf.js/wiki/Viewer-options)). The hash cannot set diacritic matching, and it may jump to an earlier match. It is fine for a one-day prototype, but should not be the final mechanism.

One limit was not tested against the real books. PDFs set in legacy TCVN3/VNI fonts with broken Unicode text mappings can make the text layer unsearchable in any library. Test a few pages of each book before trusting highlights.

## What to install, and what to avoid

The frontend choice turns on React 18. react-pdf `main` is now v11.0.0, which states "React 19 is now required" and moves to PDF.js 6.3.289. The last React 18-compatible line is **v10.5.0**, ESM-only, on PDF.js 5.4.296 ([react-pdf releases](https://github.com/wojtekmaj/react-pdf/releases); [package.json](https://raw.githubusercontent.com/wojtekmaj/react-pdf/main/packages/react-pdf/package.json)). react-pdf has no built-in search, highlight or scroll-to API; you have to build those yourself in `customTextRenderer` ([README](https://raw.githubusercontent.com/wojtekmaj/react-pdf/main/packages/react-pdf/README.md)). That is why the recommendation is to wrap **pdfjs-dist** directly in one React component. It gives page jumps (`currentPageNumber`), the tested find engine above, and no React version coupling. Draw the stored rectangles as absolutely positioned divs over the page. **@react-pdf-viewer was archived on 25 March 2026** and requires a commercial licence ([GitHub](https://github.com/react-pdf-viewer/react-pdf-viewer/)), so avoid it. **react-pdf-highlighter-extended** (MIT, 8.1.0) stores viewport-independent `boundingRect`/`rects` and has `scrollToHighlight` ([GitHub](https://github.com/DanielArnould/react-pdf-highlighter-extended)). It is the right add-on only if the doctor will later annotate; its pinned pdfjs-dist version was not verified.

On the backend, the project already runs Chroma, `HuggingFaceEmbeddings` with multilingual-e5-small, `rank_bm25`, RRF fusion (k=60) and PyMuPDF, with no reranker. Vietnamese benchmark results argue for upgrading the embedding model. On VN-MTEB, a Findings of EACL 2026 benchmark of 41 datasets, retrieval scores are **40.88** for multilingual-e5-large-instruct, **39.84** for bge-m3 and **34.18** for the Vietnamese bge-m3 fine-tune ([arXiv 2507.21500](https://arxiv.org/html/2507.21500)). That fine-tune, AITeamVN/Vietnamese_Embedding, still wins clearly on Zalo legal QA (Acc@1 **0.727** vs bge-m3's 0.568) ([HF](https://huggingface.co/AITeamVN/Vietnamese_Embedding)). So the two benchmarks disagree, and the project's own eval set has to decide. The default should be **bge-m3**:

- MIT licence
- 8,192-token context
- One model for both Vietnamese and English
- One forward pass returns dense vectors, sparse lexical weights and ColBERT vectors ([HF](https://huggingface.co/BAAI/bge-m3)), so its sparse output can sit alongside or replace BM25

For the reranker, **AITeamVN/Vietnamese_Reranker** (Apache-2.0, 0.6B parameters, Zalo Acc@1 **0.794**, the best in its table) ([HF](https://huggingface.co/AITeamVN/Vietnamese_Reranker)) should rerank only the top 20–30 fused candidates. CPU latency was never measured; an estimate of 1–3 seconds per query on a laptop is an assumption, so put the reranker behind a setting. Validate any int8 quantisation before shipping it. One builder found that int8 noticeably degraded bge-m3 and shipped fp32 instead ([HF](https://huggingface.co/a-ivanovitch/bge-m3-onnx)). For lexical search, **bm25s** is more than 100x faster than rank_bm25 on most BEIR datasets ([arXiv 2407.03618](https://arxiv.org/html/2407.03618v1)). An independent run measured 293 μs vs 3.25 ms at 10K documents ([zerodep](https://zerodep.readthedocs.io/en/latest/benchmarks/sparse_search/)). There is no study showing that Vietnamese word segmentation improves BM25 recall, so A/B test pyvi rather than assuming it helps. Never segment text before passing it to bge-m3 or e5.

Chroma can stay. Its native sparse/hybrid search appears to be Cloud-only ([Chroma docs](https://docs.trychroma.com/cloud/schema/sparse-vector-search)), so keep the fusion in Python. Keep a per-document BM25 mask so that "ask about this document" queries are not diluted by the global top-k.

| Need | Install | Licence | Notes |
|---|---|---|---|
| PDF viewer, page jump, find | `pdfjs-dist` (wrap `PDFViewer`, `PDFFindController`, `EventBus`) | Apache-2.0 | Alternative: `react-pdf@10.5.0`, pinned; not v11 on React 18 |
| Stored highlights / annotation | `react-pdf-highlighter-extended` (optional) | MIT | Check which pdfjs-dist version it pins |
| Bounding-box extraction | PyMuPDF (already used); or `pypdfium2` + `pdfplumber` | AGPL / Apache-2.0 or BSD-3 / MIT | Switch if the app is ever hosted closed-source |
| Embeddings | `FlagEmbedding` + `BAAI/bge-m3` | MIT | Full re-index; A/B against me5-large-instruct |
| Reranker | `AITeamVN/Vietnamese_Reranker` or `BAAI/bge-reranker-v2-m3` | Apache-2.0 | Top 20–30 only; gate behind a setting on CPU |
| Lexical search | `bm25s` | — | Replaces `rank_bm25`; keep RRF k=60 |
| Fuzzy alignment | `rapidfuzz` | — | Chunk-to-page span matching |
| OCR (scanned books) | Tesseract `vie` via OCRmyPDF, or PaddleOCR PP-OCRv5 Latin | — | Run at 300 DPI, then NFC-normalise |

PyMuPDF is dual-licensed: AGPL or commercial from Artifex ([PyPI](https://pypi.org/project/PyMuPDF/1.19.0/)). That is acceptable for a doctor's private local tool. It becomes a risk if the app is ever hosted as a closed service, in which case pypdfium2 (Apache-2.0/BSD-3) ([docs](https://pypdfium2.readthedocs.io/en/stable/)) can extract the same word boxes. Its coordinates use a bottom-left origin and must be flipped. For scanned Vietnamese pages, the PP-OCRv5 Latin recogniser lists Vietnamese as supported, but reports only **84.7%** accuracy on a mixed Latin-script set ([PaddleOCR](https://www.paddleocr.ai/latest/en/version3.x/algorithm/PP-OCRv5/PP-OCRv5_multi_languages.html)). The Tesseract-based VietOCR recommends scanning at 200–400 DPI ([VietOCR](https://vietocr.sourceforge.net/usage.html)). There is no head-to-head Vietnamese OCR benchmark, so try both on a sample of the doctor's own scans. Docling (MIT core) chunks by document structure ([PyPI](https://pypi.org/project/docling-core/2.88.0/)), but heading detection from PyMuPDF font sizes is enough without adding a dependency.

For agent skills, the useful set is mostly already in this workspace:

| Skill | Use | Source / install |
|---|---|---|
| `frontend-design` | Set the visual direction; brief it with "calm clinical, NHS-like, elderly users" | Anthropic |
| `ui-ux-pro-max` | Medical Clinic and Pharmacy palette profiles, plus its UX rule set | [GitHub](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) |
| `webapp-testing` | Playwright checks of target sizes, focus order and 320px reflow | Anthropic example skills, `/plugin install example-skills@anthropic-agent-skills` ([GitHub](https://github.com/anthropics/skills)) |
| `web-design-guidelines` | Review JSX for accessibility and interaction issues | Vercel, `npx skills add vercel-labs/agent-skills`; run `--list` first, sources disagree on exact names ([llmbase](https://llmbase.ai/skills/vercel-labs/web-design-guidelines/)) |
| `react-best-practices` | Render performance on hospital PCs | Vercel, same package |
| `pdf` | Ingestion work | Anthropic document skills |

No reputable clinical-specific agent skill turned up.

## A calm hospital look: one blue, reserved red, big type

The NHS design system is the most reusable model. It uses one blue (`#005EB8`) for links and actions, near-black text (`#212B32`), a grey page tint (`#F0F4F5`) to cut glare, white cards for important content, red only for errors and urgent care, yellow for focus, and it never lets colour carry meaning alone. It requires WCAG 2.2 AA and asks for AAA where possible ([NHS colour](https://service-manual.nhs.uk/design-system/styles/colour)). Medical-device alarm conventions (IEC 60601-1-8) reserve red for high priority and yellow for medium priority ([Vocera](https://pubs.vocera.com/vam/vam_2.2.4/help/vam_admin_help/topics/vam_configalarmlevel.html)). In this app, red should therefore mean only contraindication, severe interaction or a red-flag diagnosis. It should never be used for brand colour, the active tab or counters. Epic's "Display Fewer Colors" setting ([Houston Methodist](https://it.houstonmethodist.org/wp-content/uploads/2021/01/Feb-21-2021-Radiologist-Companion.pdf)) and its "Click Less, See More" redesign theme ([Cooper Health](https://blogs.cooperhealth.org/weeklyrounds/?p=12567)) point the same way. The blue-and-white scheme also matches what Vietnamese doctors see in hospital information systems such as VNPT HIS, without copying their density. That density claim is an inference; no design documentation for those systems is published.

| Token | Hex | Role | Contrast (computed) |
|---|---|---|---|
| `--bg` | `#F4F7F8` | Page tint | — |
| `--surface` | `#FFFFFF` | Cards, chat, monographs | — |
| `--text` | `#1F2A33` | Body | 14.6:1 on white |
| `--text-muted` | `#4C6272` | Meta, citation labels | 6.4:1 |
| `--primary` | `#005EB8` (or teal `#0B6E79`) | Buttons, active tab, links | 6.4:1 / 6.0:1 |
| `--primary-tint` | `#E8F1FA` | Active tab, selected tree node, citation chip | 5.6:1 |
| `--input-border` | `#4C6272` | Inputs and the patient-history textarea | 6.4:1 |
| `--danger` / bg | `#B3261E` / `#FDECEA` | Contraindications, red flags | 6.5:1 |
| `--warning-text` / bg | `#7A4F01` / `#FFF4D6` | "Thận trọng" (caution) | 6.5:1 |
| `--success` | `#1B6E3A` | "Có nguồn" (sourced) badge | 6.3:1 |
| `--focus` | `#FFEB3B` ring + `#1F2A33` outline | Keyboard focus | — |

Do not use grey text lighter than `#4C6272`. `#8A99A6` fails at 2.9:1. These palette ratios were computed with the WCAG formula during research. If dark mode is offered, it should be a manual toggle, not the default.

For fonts, every candidate except one was checked live against the Google Fonts API and has a `vietnamese` subset. **Atkinson Hyperlegible Next has no Vietnamese subset**, so it is ruled out. **Be Vietnam Pro** is designed for Vietnamese and OFL-licensed ([Fontsource](https://fontsource.org/fonts/be-vietnam-pro/about)), but the API build checked has no tabular figures (`tnum`) and uses proportional digits. Stacked doses such as "1,25 mg" over "10 mg" would not align. The practical stack is **Inter, then Noto Sans, then system-ui**, with `font-variant-numeric: tabular-nums`, Inter's slashed zero in dose cells, and `white-space: nowrap` to keep each number with its unit. Be Vietnam Pro can be used for headings if a local identity matters. Use weights 400, 600 and 700 only; thin weights make Vietnamese diacritics harder to read.

For sizes, WCAG 2.2 sets the floor: 24×24 px targets (SC 2.5.8), with 44×44 px recommended for important controls ([W3C](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html)), 4.5:1 text contrast, and text usable at 200% zoom ([WCAG 2.2](https://www.w3.org/TR/WCAG22/)). NN/g's research with 123 users aged 65+ found that tiny type caused problems in every study. It also found that older users make more input errors, struggle to notice error messages, and need to be able to control text size ([NN/g](https://www.nngroup.com/articles/usability-for-senior-citizens/)). NHS body text is 19px on desktop ([NHS typography](https://service-manual.nhs.uk/design-system/styles/typography)). The resulting targets are:

- Body text 18–20px, never below 16px
- Line height 1.6, so stacked marks such as "ễ" and "ặ" do not collide
- Line length about 70ch
- Targets 44–48px, with at least 8px between them
- An A− / A / A+ text-size control
- No icon-only, hover-only or swipe actions
- Error messages in plain Vietnamese placed next to the field
- Drug search that accepts text typed without diacritics

**Navigation:**

- A persistent top bar with three labelled tabs: **"Hỏi đáp y khoa"** (medical Q&A, the chatbot), **"Chẩn đoán"** (diagnosis, the decision tree) and **"Tra cứu thuốc"** (drug lookup, the library). The active tab gets a tint, an underline and bold text, so it does not depend on colour alone.
- On phones, the same three tabs become a bottom bar with labels. No hamburger menu.
- No intro screen. Each tab opens ready to use, as UpToDate's simpler, search-first homepage does ([Freiburg UpToDate guide](https://www.uniklinik-freiburg.de/fileadmin/mediapool/10_andere/bibliotheken/pdf/Materialien/Schulungsmaterialien/Anleitungen/UpToDate-refreshed-homepage.pdf)).

**Decision tree:**

- One question per step, answered with full-width 56px buttons.
- A step counter ("Bước 3/7", step 3 of 7), with **"Quay lại"** (back) and **"Làm lại từ đầu"** (start over) always visible.
- The patient-history box is labelled **"Tình trạng bệnh nhân trước đó (không bắt buộc)"** ("Previous patient status (optional)"). "Optional" goes in the label itself, not only in the placeholder.

## Feed the library government text first, licensed books never

Vietnam's IP law makes Ministry of Health guidelines the safest Vietnamese corpus. Article 15 of Luật SHTT (the Law on Intellectual Property) excludes legal normative documents and administrative documents from copyright protection ([thuvienphapluat](https://thuvienphapluat.vn/hoi-dap-phap-luat/doi-tuong-khong-thuoc-pham-vi-bao-ho-quyen-tac-gia-96705.html); [LSVN](https://lsvn.vn/doi-tuong-nao-khong-thuoc-pham-vi-bao-ho-quyen-tac-gia-1683458018-a130123.html)). The *Hướng dẫn chẩn đoán và điều trị* guidelines are issued as attachments to ministerial decisions (Quyết định …/QĐ-BYT), so they are very likely covered. One residual argument was not tested: that an expert-authored attachment is a scientific work rather than an administrative document. The files are scattered, and many have been superseded:

| Specialty | Decision | Source |
|---|---|---|
| Infectious diseases | 2021 compilation | [kcb.vn PDF](https://kcb.vn/upload/2005611/20210723//Truyen-nhiem-1.pdf) |
| Haematology | QĐ 1832/QĐ-BYT (2022), replaces 1494 | [luatvietnam](https://luatvietnam.vn/y-te/quyet-dinh-1832-qd-byt-224639-d1.html) |
| COPD | QĐ 4562/QĐ-BYT (2018), supersedes 3874 | [luatvietnam](https://luatvietnam.vn/y-te/quyet-dinh-4562-qd-byt-2018-huong-dan-chan-doan-benh-phoi-tac-nghen-man-tinh-166051-d1.html) |
| Respiratory | QĐ 4235/QĐ-BYT | [luatvietnam](https://luatvietnam.vn/y-te/quyet-dinh-4235-qd-byt-cua-bo-y-te-ve-viec-ban-hanh-tai-lieu-chuyen-mon-huong-dan-chan-doan-va-dieu-tri-benh-ho-hap-345865-d1.html) |
| Endocrinology | QĐ 3879/QĐ-BYT | [luatvietnam](https://luatvietnam.vn/y-te/quyet-dinh-3879-qd-byt-bo-y-te-90224-d1.html) |
| Hepatitis C | QĐ 5012/QĐ-BYT (2016) | [luatvietnam](https://luatvietnam.vn/y-te/quyet-dinh-5012-qd-byt-bo-y-te-108606-d1.html) |
| Hepatocellular carcinoma | QĐ 3129/QĐ-BYT (2020) | [Sở Y tế Bắc Giang PDF](https://syt.bacgiang.gov.vn/documents/21459/8882779/120200723193532.pdf/ac0e2065-e7eb-4032-9fb3-f545faa4f88e) |
| Paediatrics | QĐ 3312/QĐ-BYT (2015) | [vnras](https://vnras.com/huong-dan-chan-doan-va-dieu-tri-mot-so-benh-thuong-gap-o-tre-em-theo-bo-y-te-quyet-dinh-so-3312-qd-byt-ngay-07-08-2015/) |
| Musculoskeletal | QĐ 361/QĐ-BYT (2014) | [accgroup](https://accgroup.vn/quyet-dinh-361-qd-byt) |
| Dentistry and maxillofacial | QĐ 3108/QĐ-BYT (2015) | [luatvietnam](https://luatvietnam.vn/y-te/quyet-dinh-3108-qd-byt-bo-y-te-97081-d1.html) |

A 2026 hepatitis B replacement has been posted ([benhnhietdoi.vn](https://www.benhnhietdoi.vn/wp-content/uploads/2026/06/BYT.-QD-ban-hanh-HDCDT-viem-gan-vi-rut-B-final-2.signed.pdf)), but its decision number and date were blank, so its status is unconfirmed. Ingestion should record each document's decision number, signing date and the decision it replaces, so the chatbot never cites a superseded guideline. Prefer files from government domains (kcb.vn, moh.gov.vn, syt.*.gov.vn).

**The *Dược thư Quốc gia Việt Nam* (national drug formulary), 3rd edition, has unclear licensing.** It was issued by QĐ 3445/QĐ-BYT (2022) and has 743 drug monographs ([trungtamthuoc](https://trungtamthuoc.com/tin-hoat-chat/quyet-dinh-ban-hanh-va-loi-noi-dau-duoc-thu-quoc-gia-viet-nam-2022-lan-xuat-ban-thu-ba)). The issuing decision is an administrative document, but the monograph text is a compiled reference work. Index it for the doctor's personal use only, and do not redistribute it.

English-language sources:

- **WHO.** Post-2016 WHO publications carry CC BY-NC-SA 3.0 IGO, confirmed on the 2025 Essential Medicines List report (24th EML, over 520 medicines) ([WHO](https://www.who.int/publications/i/item/9789240119741); [fact sheet](https://www.who.int/news-room/fact-sheets/detail/essential-medicines)). That licence suits a non-commercial personal index, but it would block commercial bundling.
- **openFDA.** Public domain under CC0, with attribution requested ([openFDA](https://open.fda.gov/license)). Its drug label JSON is easier to split by section than raw SPL XML.
- **DailyMed.** The human prescription label set is about 55,100 files and about **16.8 GB**, updated daily ([DailyMed](https://dailymed.nlm.nih.gov/dailymed/spl-resources-all-drug-labels.cfm)). Filter it to generics sold in Vietnam.
- **RxNorm Prescribable Content.** "Without any licensing restrictions" ([NLM](https://mainweb.awsprod.nlm.nih.gov/research/umls/rxnorm/docs/prescribe.html)). Use it to build a brand-to-generic synonym table at build time, combined with spelling-variant rules taken from the Dược thư headers.
- **StatPearls.** CC BY-NC-ND 4.0 ([NCBI](https://ncbi.nlm.nih.gov/books/NBK549793/figure/article-23948.image.f1)). The only lawful bulk route is NCBI's LitArch open-access FTP; any other automated bulk download is prohibited ([NCBI](https://www.ncbi.nlm.nih.gov/books/about/openaccess/)). It was not confirmed that StatPearls is in that subset.

What stays out:

- **NICE** content "cannot be used for AI purposes without written permission… supported by a signed licence agreement" ([NICE](https://www.nice.org.uk/reusing-our-content/use-of-our-content-for-ai-purposes)). Its open licence excludes the BNF and Clinical Knowledge Summaries.
- **MSD Manuals.** MSD's terms address AI training use directly ([MSD](https://www.msd.com/?p=3684420)). Link to it instead of ingesting it.
- **UpToDate, BNF and MedlinePlus drug monographs.** Their licences were not verified, so treat them as excluded.

## Prioritised implementation plan

The order follows dependencies. The citation data contract has to exist before the viewer can use it. The viewer is what the doctor notices most. Retrieval upgrades need the eval set before they can be judged.

| # | Step | Key work | Done when |
|---|---|---|---|
| 1 | Strip the app | Delete the statistics/Dashboard, notification/Reminders, patient-profile and Intro code and their backend routes. Build a three-tab top bar (bottom bar on mobile). | App opens straight into "Hỏi đáp y khoa"; no dead routes |
| 2 | Design tokens and type | Palette tokens in `index.css`; Inter + Noto Sans (Vietnamese subset); 18–20px body; 44–48px targets; focus ring; A−/A/A+ control | 320px reflow and 200% zoom pass; Playwright target-size check |
| 3 | Citation contract | Backend returns `book_id, page, page_label, quote, chunk_text, rects[], match_confidence`; serve PDFs at `/api/books/{id}.pdf` | Every answer chip shows book and page |
| 4 | Ingest-time rectangles | NFC/NFKC match key; PyMuPDF word boxes; rapidfuzz alignment; store normalised rectangles per chunk; record decision-number and replacement metadata | Highlight accuracy spot-checked on 20 chunks per book |
| 5 | PDF viewer | pdfjs-dist `PDFViewer` component in a split view; draw rectangles; fall back to find with `matchDiacritics:true`; "Về đoạn trích dẫn" button and fallback banner | Click a citation, the right page opens and the passage is visibly highlighted |
| 6 | "Hỏi về tài liệu này" | Removable document chip; scoped retrieval (Chroma `where` + per-document BM25 mask) with a boost near the cited page | Scoped answers cite only that book |
| 7 | Eval set | Extend `eval/` with 50–150 Vietnamese and English queries with gold (doc_id, page); recall@5/10/30 and MRR@10 | Baseline numbers for e5-small recorded |
| 8 | Retrieval upgrade | Re-index with bge-m3 (A/B me5-large-instruct, AITeamVN); swap in bm25s; add the Vietnamese reranker on the top 20–30, behind a setting; synonym table from RxNorm | MRR@10 beats the baseline; latency acceptable on the doctor's PC |
| 9 | Corpus | MOH guidelines first (validity checked), then the WHO EML, openFDA labels for local generics, and Dược thư for personal use only; OCR scanned books with Tesseract `vie` or PaddleOCR | Library tab lists each source with its licence and decision number |
| 10 | Tree and drug library polish | One question per step, 56px answers, the optional history box; monographs with fixed section order and `tabular-nums` dose tables | Doctor completes each task unaided in a usability session |

## Conclusion

The biggest change in understanding is that this redesign is mostly about trust, not about adding features. An older clinician will rely on the assistant only if a citation can be checked in one tap against the page it came from. So the rectangle data contract and the honest fallback banner matter more than the choice of embedding model. They also protect against the risk that neat citation chips make answers look more authoritative than they are.

Two open risks deserve early tests rather than assumptions. The first is whether the doctor's actual PDFs have usable Vietnamese text layers; legacy fonts would quietly break both highlighting and BM25. The second is CPU latency of the 0.6B-parameter reranker on the hospital machine. Both can be measured in a day, and their results should decide whether steps 4 and 8 need OCR or a lighter reranker before the rest of the plan goes ahead.
