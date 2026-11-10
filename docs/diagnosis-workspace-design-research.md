# Diagnosis workspace design research

Research date: 2026-11-10 (Asia/Saigon). Scope: presentation and interaction of Fil's existing diagnosis support workflow. This is UI research, not clinical guidance or validation of diagnostic output.

## Starting point and constraints

The current [DiagnosisTreeView.jsx](../frontend/src/components/DiagnosisTreeView.jsx) contains one patient-description textarea, a pannable/zoomable symptom tree, exam suggestions and findings, selected-symptom summaries, differential results, reasoning details, treatment suggestions and allergy checks. Application state and API calls are owned by [App.jsx](../frontend/src/App.jsx). These functional capabilities should remain available.

The user's earlier accepted simplifications remain constraints: one description field; no separate previous-condition field; no Home button; no repeated large diagnosis hero or description above the workspace. Keep the shared website header and the existing Fil teal identity. Drug transcription is paused and outside this work.

## Primary-source references

### 1. A real dashboard template: shadcn/ui dashboard-01

The official [Dashboard Blocks](https://ui.shadcn.com/blocks/dashboard) page supplies a working dashboard example and source, including a content inset, consistent section spacing, content cards, chart region and table. This provides an inspectable implementation reference, not just a concept image. Its app sidebar and operational metrics serve a different product context.

**Fil adaptation (design inference):** use its disciplined surface hierarchy and spacing for a broad clinical workspace plus a narrower results rail. Do not transplant the app sidebar, fake statistics, charts or sample data. The existing React/Radix components can provide this composition; importing the whole template or changing frameworks is unnecessary.

### 2. Carbon: ordered progress and useful empty states

Carbon's [Progress indicator guidelines](https://www.carbondesignsystem.com/building-blocks/core/components/progress-indicator/guidelines) distinguish completed, current and future stages in a linear task with three or more steps. The default indicator reports progress without acting as navigation. It discourages this component for unordered or variable-length processes.

**Fil adaptation (design inference):** a compact four-stage status row—Mô tả, Triệu chứng, Khám, Kết luận—reflects the actual sequence. Derive its state from real description/tree/exam/final-result state. Avoid completion percentages that the backend does not provide. The row should not create another large header or hide access to existing sections.

Carbon's [Empty states pattern](https://www.carbondesignsystem.com/building-blocks/core/patterns/empty-states) recommends a concise explanation of the missing content and an appropriate next action. A related illustration is optional. It cautions against repetitive illustrations across several empty dashboard widgets and against competing primary actions.

**Fil adaptation (design inference):** make the empty tree region feel intentional with a small abstract branching diagram, a short title and one line directing the doctor to enter the description. Do not draw fabricated symptoms or diagnoses. The result rail can use quieter text and a small icon. Give generation, waiting, error and populated states distinct messages within the same bounded region. Do not decorate all empty panels equally.

GOV.UK's [Task list guidance](https://design-system.service.gov.uk/components/task-list/) specifically excludes tasks that must be completed in a fixed order. Therefore its free-order task-list template is not suitable for replacing this clinical sequence.

### 3. NHS: clear input and purposeful grouping

The NHS [Textarea component](https://service-manual.nhs.uk/design-system/components/textarea) documents a persistent associated label and optional hint connected with `aria-describedby`. The [Card guidance](https://service-manual.nhs.uk/design-system/components/card) uses cards to group related content and actions, and distinguishes primary and secondary emphasis.

**Fil adaptation (design inference):** keep one strongly labeled, generous description field with a concise hint outside the placeholder. Use the description, tree and exam blocks as meaningful groups; keep the results rail visually quieter. Reserve the prominent teal primary action for the next valid operation. Make the dependent exam action explain why it is unavailable before symptoms are selected. Avoid turning every sentence into another nested card.

### 4. React Flow: a canvas reference, not a migration requirement

The official [Background component](https://reactflow.dev/api-reference/components/background) exposes dots, lines and cross patterns with configurable color, spacing and size. The [Controls component](https://reactflow.dev/api-reference/components/controls) places zoom and fit actions in a compact viewport control panel. The first-party [Dark Mode example](https://reactflow.dev/examples/styling/dark-mode) and [Theming documentation](https://reactflow.dev/learn/customization/theming) show coordinated canvas and control themes.

**Fil adaptation (design inference):** keep a restrained dot or fine grid texture inside the tree canvas, bounded by a distinct rounded frame. Float the existing zoom/reset/fit controls above the canvas so they remain readable. Keep the page background quieter than the graph. Use matching dark tokens for nodes, connections, surfaces and controls rather than only darkening the page. No React Flow dependency is needed: Fil already owns these interactions, and this request is not a graph-engine rewrite.

### 5. Accessibility checks for the visual redesign

[WCAG non-text contrast](https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html) requires meaningful control/state cues to reach 3:1 against adjacent colors, with stated exceptions. Decorative background grids can be faint; selected-state indicators and control icons cannot rely on that faint treatment. Keep labels or distinct shapes alongside the confirmed/excluded color encoding.

[WCAG status messages](https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html) explains how progress and completion text can be announced without moving focus. Use `role="status"` for generation and completion messages. Make zoom reset a real named button instead of the existing clickable span. Retain visible keyboard focus and ensure the results detail dialog has usable keyboard dismissal and focus behavior.

## Concrete Fil composition

The following is a proposed design, not a claim about any reference's exact CSS or clinical effectiveness:

```text
Shared Fil website header
────────────────────────────────────────────────────────────
 Mô tả        Triệu chứng         Khám          Kết luận

 ┌────────────────────────────────┐ ┌───────────────────────┐
 │ Nhập mô tả bệnh nhân            │ │ Triệu chứng đã chọn   │
 │ single textarea + concise hint │ │ real confirmed / no   │
 │                 [Tạo cây]      │ └───────────────────────┘
 └────────────────────────────────┘ ┌───────────────────────┐
 ┌────────────────────────────────┐ │ Kết quả chẩn đoán     │
 │ Cây triệu chứng  legend        │ │ quiet waiting state   │
 │                                │ │ or real results       │
 │   deliberate empty state       │ │ reasoning / selection │
 │   or real interactive tree     │ │ treatment / allergies │
 │                 [−][100%][+][⤢]│ │                       │
 └────────────────────────────────┘ └───────────────────────┘
 ┌────────────────────────────────┐
 │ Exam action / findings         │
 └────────────────────────────────┘
```

- **Background:** a very light, static teal wash around the workspace, with plain reading surfaces. Put fine texture only on the canvas. Do not introduce animation or a photographic hospital backdrop behind medical text.
- **Hierarchy:** distinct input, canvas and output surfaces; consistent padding; restrained shadows; one strong accent area at the input or active stage. Preserve the website's existing overall alignment.
- **Content:** show counts, progress and results only from actual state. Do not fill empty results with demonstration patients, medical facts, likelihoods or suggested diagnoses.
- **Responsive:** collapse the results rail under the primary workflow on narrow screens; allow stage labels to wrap; retain usable control hit areas. Avoid nested page scrollbars where a single document flow works.
- **Implementation scope:** reuse Be Vietnam Pro, lucide-react and Radix already installed. UI/UX Pro Max and Polish are already available. A new design package or plugin would not improve this bounded presentation change enough to justify extra runtime/dependencies.

## Verification targets

Verify the initial empty page, typing, disabled/ready action, generation, error/retry, real tree selection and exclusion, zoom/reset/fit, exam suggestions, entered findings, final results and reasoning, selected treatment, allergy checks, light/dark themes and mobile reflow. Use API fixtures for presentation tests and label them as test data. Do not treat visual QA as evidence that diagnosis output is medically correct.

## Implementation notes

The implemented visual system reuses Fil's established palette: background `#f2f8f8`, white reading surfaces, ink `#173a40`, muted text `#526d74`, teal `#006875`; dark mode uses `#101f2c`, `#192d3d` and `#9de5e4`. Be Vietnam Pro, lucide icons and existing Radix packages are retained. The quiet teal wash sits outside the cards; the fine dot texture belongs only to the graph canvas. There is no new sidebar, hero, sample patient or invented metric in the production UI.

The four-stage indicator follows actual tree/exam/final state. Existing selection, generation, reasoning, treatment and allergy components remain connected to the same callbacks and APIs. Zoom reset is now a keyboard-operable button; the reasoning dialog uses Radix focus management and Escape dismissal.

The same revision removes the white specialty ribbon and Fil wordmark within cover cards, moving just the specialty symbol to the upper corner. Account/profile/password management is separated from general website settings: the avatar opens account actions, the gear opens settings directly, and notifications retain their own header control. Profile specialty and email editing are explicitly saved with the existing profile API.

## Validation record

- Production build passes; all 19 existing frontend tests pass. The pre-existing large clinical-bundle warning remains.
- Browser QA used a local fixture server with explicitly artificial UI-only content. It verified profile save, separate account/settings menus, all 12 cleaned-up covers, error/retry, yes/no and choice answers, zoom/reset, exam suggestions, findings, final result selection, reasoning dialog Escape dismissal, treatment rendering and allergy-state rendering.
- Responsive widths of 320, 390, 820, 1051, 1100, 1280, 1440 and 1920 CSS pixels were checked; both light and dark themes were also inspected. No document-level horizontal overflow was observed. No drug corpus or backend medical logic was modified.
