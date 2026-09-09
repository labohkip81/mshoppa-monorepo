---
version: alpha
name: MSHOPPA Natural Storefront
themeId: natural-01
status: implementation-specification
updated: "2026-09-05"
reference:
  name: Allbirds design-language reference
  website: "https://www.allbirds.com"
  suppliedBy: user
  suppliedOn: "2026-09-05"
  claimedExtractionDate: "2026-05-13"
  sourceAuthor: "Dov Azencot"
scope:
  application: apps/storefront
  themePackage: packages/storefront-themes
  domains:
    - "<business>.mshoppa.com"
    - "verified merchant custom domains"
  excludedApplications:
    - apps/merchant-admin
    - apps/platform-admin
    - apps/marketing
    - apps/payments
colors:
  ink: "#212121"
  ink-pure: "#000000"
  ink-charcoal: "#575757"
  ink-mid: "#6a6767"
  ink-muted: "#a8a2a7"
  canvas: "#ece9e2"
  canvas-warm: "#e0dacf"
  canvas-lightest: "#f5f4f1"
  surface-white: "#ffffff"
  hairline: "#cdcdcd"
  brand-mauve: "#a57e75"
  brand-sky: "#879aab"
  brand-taupe: "#d1b0a4"
  brand-olive: "#9e8949"
  ink-midnight: "#03143b"
  ink-khaki: "#443828"
  status-error: "#9c0f0f"
  status-success: "#10714e"
  on-ink: "#ffffff"
typography:
  display-serif: {fontFamily: '"Self Modern", ui-serif, serif', fontSize: "40px", fontWeight: 400, lineHeight: "1.0", letterSpacing: "0px"}
  display-serif-h2: {fontFamily: '"Self Modern", ui-serif, serif', fontSize: "40px", fontWeight: 400, lineHeight: "1.5", letterSpacing: "0px"}
  display-serif-editorial: {fontFamily: '"Self Modern", ui-serif, serif', fontSize: "40px", fontWeight: 400, lineHeight: "1.2", letterSpacing: "0px"}
  heading-md: {fontFamily: "Geograph, system-ui, sans-serif", fontSize: "24px", fontWeight: 400, lineHeight: "1.33", letterSpacing: "0.6px"}
  body-lg: {fontFamily: "Geograph, system-ui, sans-serif", fontSize: "20px", fontWeight: 400, lineHeight: "1.4", letterSpacing: "0px"}
  body-md: {fontFamily: "Geograph, system-ui, sans-serif", fontSize: "16px", fontWeight: 400, lineHeight: "1.5", letterSpacing: "0px"}
  body-sm: {fontFamily: "Geograph, system-ui, sans-serif", fontSize: "14px", fontWeight: 400, lineHeight: "1.5", letterSpacing: "0.7px"}
  body-xs: {fontFamily: "Geograph, system-ui, sans-serif", fontSize: "12px", fontWeight: 400, lineHeight: "1.33", letterSpacing: "0.6px"}
  label-uppercase-sm: {fontFamily: "Geograph, system-ui, sans-serif", fontSize: "14px", fontWeight: 500, lineHeight: "1.43", letterSpacing: "0.7px", textTransform: uppercase}
  label-uppercase-xs: {fontFamily: "Geograph, system-ui, sans-serif", fontSize: "12px", fontWeight: 500, lineHeight: "1.25", letterSpacing: "0.3px", textTransform: uppercase}
  button-cap: {fontFamily: "Geograph, system-ui, sans-serif", fontSize: "12px", fontWeight: 500, lineHeight: "1.25", letterSpacing: "0.3px", textTransform: uppercase}
  button-mono: {fontFamily: '"Akkurat Mono", ui-monospace, monospace', fontSize: "16px", fontWeight: 500, lineHeight: "1.5", letterSpacing: "0.8px", textTransform: uppercase}
  caption-mono: {fontFamily: '"Akkurat Mono", ui-monospace, monospace', fontSize: "12px", fontWeight: 400, lineHeight: "1.33", letterSpacing: "1.2px", textTransform: uppercase}
rounded:
  none: "0px"
  xs: "4px"
  sm: "8px"
  md: "16px"
  lg: "20px"
  full: "9999px"
spacing:
  xxs: "2px"
  xs: "4px"
  sm: "8px"
  md: "10px"
  base: "12px"
  lg: "16px"
  xl: "20px"
  2xl: "24px"
  3xl: "32px"
  4xl: "40px"
---

# MSHOPPA client-storefront design specification

## Decision and precedence

Use the user's supplied Allbirds design language for the default merchant storefront theme, `natural-01`. Implement it in Angular. References in the supplied material to React, JSX, or a React design-system package do not change MSHOPPA's Angular requirement.

This document adapts the supplied reference into implementation requirements. It does not claim to be a verbatim archive, an independently verified extraction of the live Allbirds site, or a validated implementation of the external DESIGN.md specification.

For client-storefront visual choices, this specification supersedes the original Saleor screenshot styling. The screenshots remain references for product, cart, and checkout structure and functionality. The main implementation prompt governs architecture, authorization, commerce correctness, and delivery scope.

Apply this theme to homepage, catalog/search, product details, cart, checkout, store-hosted payment result/confirmation, delivery tracking, shopper authentication/account pages, and public policy/contact pages. Apply the same theme when a merchant uses a verified custom domain.

Do not restyle merchant or platform administration. They retain the Shadcn-inspired Angular/Spartan direction and MSHOPPA branding. The MSHOPPA marketing site and separately hosted payment application retain their previously specified design scope; this update does not authorize redesigning either. The storefront checkout and confirmation pages are included, even though the separate `payments.mshoppa.app` application is excluded.

## Visual identity

- Warm natural-white canvas `#ece9e2`, with warm graphite `#212121` for normal text, action fills, and strong outlines.
- White panels and warmer cream `#e0dacf` product backgrounds provide surface separation.
- Mauve `#a57e75`, sky `#879aab`, taupe `#d1b0a4`, and olive `#9e8949` are occasional image/editorial background tones. Do not apply all four to every page. They are not CTA, text, border, or status colors.
- Full-pill action buttons and compact single-line fields; 16px product/editorial cards; square full-width navigation, footer, and page bands.
- Flat surfaces without decorative card shadows or hover lift. Photography provides depth. Dialogs use a dark backdrop rather than a floating shadow.
- Neutral sans-serif interface typography with an occasional 40px serif product/editorial display and restrained mono technical captions.
- Display the merchant's name, logo, photographs, and product facts. Do not ship Allbirds names, wordmark, collaboration claims, sustainability copy, or branded photographs as tenant content.
- MSHOPPA orange is not the default storefront CTA or background color. A supplied merchant logo can retain its own colors.

The source includes conflicting occurrence counts, serif usage counts, radius descriptions, and statements about hover/focus. Those are observations, not acceptance criteria. The token values above and the explicit component and state rules below resolve the conflicts for implementation.

## Typography and font assets

Preserve the source roles, weights, and tracking shown in the frontmatter. Use 400/500 as the dominant weights. Keep long body text and forms in sans-serif; reserve serif displays for a product hero or occasional editorial/category heading. Product-grid labels use the smaller sans-serif role rather than 40px headings in every card.

The source names Geograph, Self Modern, and Akkurat Mono; no font binaries or usage rights have been supplied. Do not download proprietary font files from the reference website. Use those faces only when suitable licensed assets are available.

For initial implementation without those files, use Inter when a properly licensed local asset is available, otherwise `system-ui`; use the declared `ui-serif, serif` display fallback; and use IBM Plex Mono/JetBrains Mono only if locally available with their licenses, otherwise `ui-monospace`. These are explicit fallbacks, not claims of exact visual equivalence. Record the selected fonts and fallback screenshots. Do not block the rest of the storefront work on missing fonts.

Keep uppercase tracking at 0.3px on 12px button/utility labels, 0.7px on 14px category labels, and 1.2px on 12px mono captions. Keep 0.6px on the body-xs role. Do not uppercase descriptions, form values, or ordinary running copy.

Use 40px/40px as the desktop product-title target and allow a responsive 32px minimum on compact mobile layouts. Titles must wrap without clipping. Keep checkout input text at least 16px. Font loading must not delay meaningful content or introduce avoidable layout shift.

## Component contract

Token names in this table refer to the frontmatter. Values are visual defaults; accessibility and adaptive-layout overrides are specified below.

| Component | Default styling and behavior |
| --- | --- |
| Primary button | `ink` fill/outline, `on-ink` label, `button-cap`, 9999px radius, 1px border, 8px 16px padding; compact desktop visual target 33px |
| Primary hover/active | Pure ink `#000000`; retain dimensions/radius; no lift, scale, or shadow |
| Secondary button | White fill, graphite text and 1px border; same pill geometry and label role |
| Mono editorial CTA | Graphite/white pill, `button-mono`, 8px 32px padding; use sparingly |
| Announcement bar | Graphite/white, body-xs, square edges, 32px desktop minimum; wrap or grow for longer/mobile copy |
| Top navigation | Natural-white canvas, 60px desktop minimum, merchant logo, navigation and account/bag utilities; no shadow |
| Navigation link | Sans 16px/24px, graphite; plain link geometry, underline for hover/current state and visible keyboard focus |
| Region dialog, if needed | White panel, 16px radius, up to 32px padding, dark translucent backdrop; do not introduce a mandatory region prompt for single-country stores |
| Product tile | Warm-cream image panel, 16px radius, zero decorative border/shadow, compact title and price below; keep the whole card's geometry at 16px even if it is a link |
| Mauve product/editorial tile | Same card geometry with `brand-mauve` image/background region |
| Sky product/editorial tile | Same card geometry with `brand-sky` image/background region |
| Taupe product/editorial tile | Same card geometry with `brand-taupe` image/background region |
| Olive editorial tile | Same card geometry with occasional `brand-olive` background; no CTA recoloring |
| Product-name display | Serif 40px/40px desktop, graphite, no decorative container |
| Product metadata | Charcoal mono caption at 12px/16px and 1.2px uppercase tracking, only for short specifications |
| Category caption | Graphite uppercase sans 14px/500 with 0.7px tracking |
| Editorial collaboration card | 16px radius, 24px padding and optional muted background; use merchant-provided content, not an invented Pantone/Allbirds collaboration |
| Single-line input | White, graphite text/1px border, pill shape, 42px compact reference height; ordinary padding 10px 12px |
| Newsletter/search input with trailing action | Same single-line input; reserve right space up to 80px only when an actual trailing control needs it |
| Input focus | Visible, contrasting graphite outline with offset; preserve layout and radius; do not repeat the source's visually indistinguishable focus state |
| Hairline divider | 1px `hairline`, square edges; decorative separation only, not the sole outline of a required control |
| Footer header/link | Header: uppercase-xs graphite. Link: body-xs charcoal with underline/focus affordance |
| Cart count chip | Transparent pill, graphite uppercase-xs label, 4px 8px padding |

Every actionable control needs resting, hover where applicable, keyboard-focus, active/selected, disabled, loading, and error/success states as relevant. Hover styling is allowed despite the source's conflicting “no-hover” notes. Color alone must not communicate an error, selection, or payment result.

Full-pill geometry applies to action buttons, filter chips, size options, and suitable single-line inputs. Circular color swatches remain circular; checkboxes/radios retain recognizable shapes; multiline text fields use 16px corners. Page/card links do not force their entire containers into pills. Source 4px/8px/20px tokens remain available for justified minor cases, not generic primary-button rounding.

## Layout and responsive behavior

Use a 4px base rhythm with the supplied exceptions of 2px and 10px. Preserve 8px grid gutters and 32–40px section breathing room. Use a centered content container up to 80rem, with 16px mobile and 32px desktop side gutters as initial implementation defaults.

- Desktop catalog: four columns where card widths remain usable.
- Tablet catalog: two or three columns based on available space.
- Mobile catalog: two columns, reducing to one when content/accessibility requires it; no horizontal page overflow.
- Product details: image gallery and purchase information side by side on desktop, stacked on mobile. Sticky controls must not obscure content, validation, or focused elements.
- Mobile navigation: a keyboard-accessible drawer with clear close control and meaningful categories.
- Cart drawer: fixed side panel on larger screens and a full-width overlay on narrow screens, with a scrollable item region and reachable totals/actions.
- Checkout: main form and summary on desktop; a single column with an accessible summary disclosure on mobile. Do not hide totals or validation feedback.

The source is a desktop-focused extraction. Mobile breakpoints and these layouts are MSHOPPA adaptations and must be visually verified, not presented as observed Allbirds behavior.

## Extending the source to complete shopping flows

The source does not fully specify the PDP, cart, checkout, tracking, or accounts. Use the earlier screenshots for workflow structure and apply this theme as follows:

| Surface | Adaptation |
| --- | --- |
| PDP variants | Pill size/options with graphite selected state; circular swatches with contrasting selection ring and text labels; explain unavailable combinations |
| PDP purchase panel | Sparse sans body, serif product name, prominent real price and graphite pill purchase button; show a reason when purchase is unavailable |
| Cart empty | Warm/light neutral panel, simple outline bag icon, concise explanation and graphite pill shopping action |
| Cart populated | Hairline-separated items, readable quantities/prices, accessible remove control, flat item thumbnails and real shipping-threshold status |
| Checkout | Warm page, white/cream sections with 16px corners, pill single-line inputs, persistent labels, graphite primary actions, country-appropriate fields |
| Payment result on storefront | Clear pending/success/failure/COD-due label, order reference and next action; semantic icon/text rather than an unexplained colored panel |
| Delivery tracking | Flat vertical timeline, timestamps and explicit current status; no invented live map or courier data |
| Shopper login/accounts | Same warm surfaces and pill actions; sans headings for utilitarian forms, clear errors and secure session behavior |
| Policy/contact pages | Readable sans body and restrained heading hierarchy; no mono or uppercase paragraphs |

All state, amounts, availability, and delivery information remain backend-authoritative under the main implementation brief.

## Accessibility and performance adaptations

The source's compact 33px buttons and 42px fields describe visual proportions. For primary purchase/checkout actions and touch contexts, increase the control to at least 44px in height while retaining pill radius and horizontal proportions. Compact secondary desktop controls may keep their reference size only with adequate target size/spacing and no overlapping hit areas. This is an explicit usability adaptation.

Check actual text/background contrast, including semantic text and merchant imagery. `ink-muted` is not approved for essential text just because it appears in the source; use a darker role for legible placeholders/helper copy when needed. Never remove focus indicators to mimic flat styling.

Use semantic controls, visible form labels, keyboard-operable galleries/filters/drawers, announced cart updates, and text explanations for errors. Trap and restore focus in dialogs/drawers. Respect reduced-motion preferences and avoid autoplay motion. Verify at 200% zoom as well as mobile/desktop viewports.

Keep the main prompt's Angular SSR, image optimization, cache scoping, font loading, and performance budgets. Do not fetch external fonts, reference-site scripts, or brand assets on every request. Theme choice must be known during SSR to prevent a flash of platform styling.

## Theme configuration and scope isolation

Implement this in `packages/storefront-themes` and consume it from `apps/storefront`. Use a scoped root such as `[data-storefront-theme="natural-01"]` and namespaced variables such as `--storefront-ink` and `--storefront-canvas`. Do not redefine shared global `--primary`, button radii, or typography defaults for administration.

The merchant theme editor retains the admin design. Its embedded store preview renders the actual storefront in an isolated preview context so storefront styles cannot bleed into admin controls. Shared accessibility primitives may be reused; storefront appearance is a distinct theme layer.

Initial configuration includes theme/version, merchant logo, section content/order, images, announcement, navigation, and selected muted product/editorial surface tones. Keep the graphite CTA and warm canvas as defaults. Any explicitly supported merchant color override must pass contrast validation and remain scoped to that tenant and theme version; do not automatically import MSHOPPA orange into client stores.

Persist draft and published theme versions as specified in the main brief. Theme cache keys include tenant and published version. Publishing one store or changing its domain cannot change another store's appearance or either admin application's styling.

## Acceptance criteria

1. Default storefront at a tenant subdomain and its verified custom domain uses the same warm canvas, graphite actions, pill controls, 16px cards, and flat styling.
2. Admin applications retain their existing MSHOPPA/Shadcn-inspired design. Previewing/editing the theme does not alter the admin shell.
3. No Allbirds branding, marketing copy, extraction counts, or SEO metadata is shipped as merchant content. Pages use merchant-specific titles and metadata.
4. All 19 supplied color tokens, 13 typography roles, 6 radius tokens, and 10 spacing tokens have deliberate mappings; optional/unused reference roles do not force extra UI features.
5. Typography uses documented available fonts/fallbacks, respects tracking, and loads without missing-asset errors. No unlicensed font files are introduced.
6. Product, cart, checkout, confirmation, tracking, and shopper-account surfaces form a coherent theme, including loading, empty, failed, disabled, and selected states.
7. Keyboard focus, contrast, readable forms, mobile targets, and reduced-motion behavior are verified; 33px reference sizing does not compromise primary touch actions.
8. Capture representative mobile and desktop screenshots of catalog, PDP, empty/filled cart, checkout, payment result, and tracking during the relevant implementation phases. Label adaptations and remaining gaps honestly.
9. Verify two tenants with different logos/content/theme settings, correct SSR and cache isolation, and an unchanged admin interface. Follow the main brief's functional and performance gates.

This update specifies the design. No storefront components or production CSS have been implemented as part of accepting the reference.
