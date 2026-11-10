# Notebook covers and recent workspaces

Research date: 2026-11-10 (Asia/Saigon). Scope: the latest homepage request only; no changes to drug content.

## Reference and design decisions

The user's attached Gemini Notebook screenshot (`codex-clipboard-cf8febd4-cf39-4f81-afc1-c6bfc0c673ab.png`) is the visual authority. The public [Notebook page](https://notebook.google.com/) does not expose the signed-in dashboard's component CSS, so the following are screenshot observations, not claims about Google's source implementation:

| Observed reference treatment | Fil adaptation |
| --- | --- |
| Featured cards use a complete image cover, large rounded corners, white text over a darker image, and compact metadata. | Put all 12 specialty notebooks in **Khám phá chuyên khoa**. Keep the existing Fil palette and specialty artwork; remove the separate white description panel. |
| The featured section shows a horizontal group with a section-level action. | Use a horizontal strip with explicit navigation and a **Xem tất cả** action that reveals all specialties. Avoid an automatic slideshow. |
| Recent notebooks form a separate, simpler grid with an icon, title, date and compact action. | Replace the duplicated **Sổ tay chuyên khoa** grid with **Sổ tay gần đây**, populated from real conversations. |
| The header provides direct tool navigation. | Remove the **Tất cả** header item; make the supplied transparent Fil logo the home link. Preserve the three requested tool links. |

Any chosen radius, card width, overlay opacity, number of visible cards or breakpoint is an implementation estimate to verify visually, not a measured Google CSS value. Decorative book badges, public-sharing symbols, authors, dates and source counts should not imply features or data Fil does not have.

## Implementation and accessibility

- A native overflow strip with CSS scroll snapping is sufficient for the requested interaction; the platform provides snap positions inside a scroll container. A carousel package is not necessary for this layout. This is an implementation recommendation based on [CSS Scroll Snap](https://developer.mozilla.org/en-US/docs/Web/CSS/Guides/Scroll_snap), not a dependency used by Notebook.
- Provide named previous/next buttons, native touch scrolling and visible keyboard focus. Keep focus stable when those buttons scroll the strip. WAI requires keyboard-operable navigation and sensible focus management; automatic rotation introduces additional stopping controls. A manual strip avoids that extra motion. See [WAI carousel tutorial](https://www.w3.org/WAI/tutorials/carousels/) and [APG carousel pattern](https://www.w3.org/WAI/ARIA/apg/patterns/carousel/).
- White overlay text needs a reliable dark scrim behind the text area across every image, including hover and both themes. Verify at least 4.5:1 contrast for ordinary text and 3:1 for qualifying large text. These are [WCAG contrast requirements](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html), not an assertion that an arbitrary gradient passes.
- A whole-card anchor can provide native navigation, opening in another tab and browser context menus. Keep bookmark/menu buttons outside that anchor as siblings; HTML does not permit interactive descendants inside a link. See the [HTML anchor content model](https://html.spec.whatwg.org/multipage/text-level-semantics.html#the-a-element).
- Use empty image alt text when the nearby specialty title already conveys the image's meaning; decorative artwork should not duplicate the announcement. See [WAI decorative images](https://www.w3.org/WAI/tutorials/images/decorative/).
- Prefer 44 × 44 CSS-pixel hit areas for icon actions as this project's touch-friendly design target. WCAG 2.2 AA's actual minimum is 24 × 24 CSS pixels or its stated spacing/exemption alternatives; do not conflate the two. See [WCAG target size](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html).

## Genuine recent notebooks

Repository evidence before implementation: [Homepage.jsx](../frontend/src/Homepage.jsx) duplicates specialties in its lower grid; [specialties.js](../frontend/src/lib/specialties.js) defines 12 specialties, initially only four with covers. [useClinicalData.js](../frontend/src/components/useClinicalData.js) loads the conversation collection from local storage. [App.jsx](../frontend/src/App.jsx) already stores conversation titles, timestamps and specialty context and restores the last response's sources when selecting a conversation.

The suitable incremental model is a recent card representing an existing conversation workspace. Order by actual activity time, exclude archived entries, and open the existing conversation through the same selection path used by chat history. A newly created workspace should open an empty chat. Empty and search states should remain useful without seeded demonstration conversations.

If source metadata appears, count distinct sources actually present in stored messages and label it **nguồn đã trích dẫn**. That is not the same as a complete notebook's selected source collection: the current conversation schema does not persist that collection. Preserve actual timestamps and titles; do not manufacture dates, clinicians, public badges or source totals. Render history only through the signed-in website's current clinical data flow. These are recommendations from the local data model, not undocumented Notebook behavior.

## Additional skill research

The existing **UI/UX Pro Max**, **frontend-design** and **web-design-guidelines** cover the main design and implementation requirements. The [skills.sh directory](https://www.skills.sh/) was checked first. Its [polish listing](https://www.skills.sh/pbakaus/impeccable/polish) identifies an established final-quality workflow; the original [pbakaus/impeccable repository](https://github.com/pbakaus/impeccable) was then inspected as the primary source. Popularity is discovery evidence, not a substitute for reading the files.

Recommended single addition: **polish**, pinned to official commit `83b01ecfa29031e38230ffa03d345a36002cf118`, path `.agents/skills/polish`. The [complete pinned SKILL.md](https://github.com/pbakaus/impeccable/blob/83b01ecfa29031e38230ffa03d345a36002cf118/.agents/skills/polish/SKILL.md) was read. The [directory at that commit](https://github.com/pbakaus/impeccable/tree/83b01ecfa29031e38230ffa03d345a36002cf118/.agents/skills/polish) contains one Markdown file and no executable/bootstrap files. It adds a focused finishing pass for spacing, typography, interaction states, responsive behavior and image loading, without replacing the installed frontend-design skill. Its prerequisite is the existing frontend-design context; the user's supplied screenshots, Fil identity and doctor audience already provide the task context.

Install just this directory with the Codex skill installer, retaining the pinned revision:

```text
python C:/Users/HP/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py --repo pbakaus/impeccable --path .agents/skills/polish --ref 83b01ecfa29031e38230ffa03d345a36002cf118
```

The present [Impeccable main skill](https://github.com/pbakaus/impeccable/blob/main/.agents/skills/impeccable/SKILL.md) uses a native context launcher, so its broader installer is unnecessary for this request. The pinned static addition avoids introducing that runtime. No new plugin, carousel dependency, global hook or generated context files are needed for this homepage revision. Installation and product edits belong to the main implementation task; this research subtask performed neither.

## Verification targets

Compare the rendered page against the supplied screenshot at wide desktop, tablet and narrow mobile sizes. Verify that all 12 specialty destinations are reachable; the logo returns home; recent cards resume the correct messages and sources; empty history does not show fabricated workspaces; search and grid/list controls remain coherent; long Vietnamese titles wrap; and keyboard focus, image fallbacks, light/dark themes and reduced-motion preferences work.

## Implemented and verified

- Installed the audited, pinned `polish` directory at `C:/Users/HP/.codex/skills/polish`; the installed SKILL.md was read and its final-pass guidance applied alongside frontend-design and UI/UX Pro Max. No runtime package or plugin was added.
- Removed the header All link. The transparent Fil logo is the homepage link, with current-page semantics. All 12 specialty notebooks now have optimized WebP covers in the top discovery strip and its expanded grid.
- Replaced the duplicated lower specialty grid with real recent conversation workspaces. Create, resume with the last cited sources, rename, archive/undo, search and grid/list display work through the existing clinical state. Dates reflect stored activity; source counts are deduplicated cited sources. Existing conversation storage remains browser-local, so this is not cross-device notebook synchronization.
- Automated verification: production build and all 19 frontend tests pass. Existing large clinical bundle warning remains. Browser QA used local API fixtures, not clinical answer generation: actual resume/source restoration, creation, rename, archive/undo, accent-insensitive search, light/dark, and responsive widths 320, 390, 820, 1280 and 1920 were checked. No document/drug corpus edits.
