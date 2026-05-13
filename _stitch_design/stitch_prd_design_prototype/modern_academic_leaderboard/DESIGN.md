---
name: Modern Academic Leaderboard
colors:
  surface: '#fdf7ff'
  surface-dim: '#ded8e0'
  surface-bright: '#fdf7ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f8f2fa'
  surface-container: '#f2ecf4'
  surface-container-high: '#ece6ee'
  surface-container-highest: '#e6e0e9'
  on-surface: '#1d1b20'
  on-surface-variant: '#494551'
  inverse-surface: '#322f35'
  inverse-on-surface: '#f5eff7'
  outline: '#7a7582'
  outline-variant: '#cbc4d2'
  surface-tint: '#6750a4'
  primary: '#4f378a'
  on-primary: '#ffffff'
  primary-container: '#6750a4'
  on-primary-container: '#e0d2ff'
  inverse-primary: '#cfbcff'
  secondary: '#63597c'
  on-secondary: '#ffffff'
  secondary-container: '#e1d4fd'
  on-secondary-container: '#645a7d'
  tertiary: '#765b00'
  on-tertiary: '#ffffff'
  tertiary-container: '#c9a74d'
  on-tertiary-container: '#503d00'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#e9ddff'
  primary-fixed-dim: '#cfbcff'
  on-primary-fixed: '#22005d'
  on-primary-fixed-variant: '#4f378a'
  secondary-fixed: '#e9ddff'
  secondary-fixed-dim: '#cdc0e9'
  on-secondary-fixed: '#1f1635'
  on-secondary-fixed-variant: '#4b4263'
  tertiary-fixed: '#ffdf93'
  tertiary-fixed-dim: '#e7c365'
  on-tertiary-fixed: '#241a00'
  on-tertiary-fixed-variant: '#594400'
  background: '#fdf7ff'
  on-background: '#1d1b20'
  surface-variant: '#e6e0e9'
typography:
  display-lg:
    fontFamily: Instrument Serif
    fontSize: 48px
    fontWeight: '400'
    lineHeight: '1.1'
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Instrument Serif
    fontSize: 32px
    fontWeight: '400'
    lineHeight: '1.2'
  headline-sm:
    fontFamily: Instrument Serif
    fontSize: 24px
    fontWeight: '400'
    lineHeight: '1.3'
  body-lg:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: '1.6'
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: '1.5'
  label-caps:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '600'
    lineHeight: '1'
    letterSpacing: 0.05em
  data-mono:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '500'
    lineHeight: '1'
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  container-max: 1280px
  gutter: 24px
  margin-mobile: 16px
  stack-sm: 8px
  stack-md: 16px
  stack-lg: 32px
  section-gap: 64px
---

## Brand & Style

The design system is rooted in a **Modern Data Minimalism** aesthetic, characterized by a "white-on-cream" palette that provides a warmer, more sophisticated alternative to standard high-tech grays. It aims to evoke the feeling of a premium digital journal or a specialized research institution—authoritative yet highly functional.

The target audience consists of AI researchers, engineers, and decision-makers who require high information density without the cognitive load of cluttered dashboards. By prioritizing generous whitespace, elegant serif headings, and subtle hairline dividers, the UI moves away from "startup-generic" toward a "premium-academic" feel. The visual language is defined by clarity, precision, and an editorial touch.

## Colors

The color strategy uses a **low-contrast foundation** to allow data visualizations and provider-specific branding to command attention. 

- **Canvas & Surfaces:** The primary background is a warm off-white (#FAFAF7), creating a soft, paper-like quality. 
- **Typography:** An "Ink Black" (#0B0B0F) is used for all text to maintain high legibility and an editorial feel.
- **Accents:** A duo of purples serves as the primary brand identifier. The vibrant "Brand Purple" is used for primary actions and highlights, while the "Soft Purple" is reserved for lower-tier informational areas like footers.
- **Provider Palette:** A dedicated semantic set for AI labs ensures instant model recognition within charts and leaderboards.

## Typography

This design system utilizes a high-contrast pairing of an elegant serif and a functional sans-serif to establish a clear information hierarchy.

- **Instrument Serif** is the voice of the product. It is used for large display headings and section titles, providing an academic and premium tone.
- **Inter** handles all functional requirements. It is chosen for its neutrality and excellent legibility at small sizes. 
- **Data Display:** For leaderboard values and metrics, "tabular numbers" (`tnum`) should be enabled in the Inter font settings to ensure vertical alignment in columns.

## Layout & Spacing

The layout follows a **fixed-center grid** philosophy on desktop to maintain the readability of long-form data tables and research text.

- **Grid:** A 12-column system with 24px gutters. Content is primarily housed in cards that span 3, 4, 6, or 12 columns.
- **Whitespace:** Use generous vertical padding (`section-gap`) between major modules to prevent the "data-overload" common in competitive products.
- **Mobile Adaptivity:** On mobile, the 12-column grid collapses to a single column with 16px side margins. Cards become full-width, and horizontal scrolling is permitted for wide data tables.

## Elevation & Depth

To maintain the "Modern Academic" aesthetic, the system avoids heavy shadows and multiple z-index layers.

- **Hairline Dividers:** Use 1px borders (#E8E8E4) as the primary method for separating content sections.
- **Subtle Lift:** Cards use a very soft, diffused shadow (0px 4px 20px rgba(0,0,0,0.03)). 
- **Interactive State:** On hover, cards should "lift" slightly by increasing shadow opacity to 0.08 and applying a -2px Y-axis translation.
- **Tonal Layering:** The canvas is the lowest level. Primary cards sit on the canvas with a pure white (#FFFFFF) background to create a subtle "white-on-cream" contrast.

## Shapes

The shape language is "Softly Geometric." 

- **Cards & Large Containers:** Standardized at a 14px (0.875rem) corner radius to soften the technical nature of the data.
- **Interactive Elements:** Buttons and input fields use a slightly tighter 8px radius.
- **Status Indicators:** Small chips for "New" or "Beta" use a full pill radius to distinguish them from structural elements.

## Components

- **Cards:** The core container. Must have a white background, 1px hairline border, and 14px radius. Content inside should have 24px of internal padding.
- **Buttons:**
  - *Primary:* Solid #7F4BF3 with white text. 
  - *Secondary:* Ghost style with #0B0B0F border and text.
- **Leaderboard Tables:** Use a minimalist approach. No vertical lines. Use horizontal hairline dividers between rows. The header row should use `label-caps` typography with a subtle cream background fill.
- **Provider Chips:** Small, 12px font-size indicators with a 2px colored border matching the provider's palette.
- **Input Fields:** 1px hairline border. On focus, the border transitions to Accent Purple with a subtle glow (2px spread).
- **Metric Highlights:** Large numerals in `headline-md` for key performance indicators (KPIs) at the top of report pages.