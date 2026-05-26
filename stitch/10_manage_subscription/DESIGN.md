---
name: Metaverse Sherpa
colors:
  surface: '#0f131f'
  surface-dim: '#0f131f'
  surface-bright: '#353946'
  surface-container-lowest: '#0a0e1a'
  surface-container-low: '#171b28'
  surface-container: '#1b1f2c'
  surface-container-high: '#262a37'
  surface-container-highest: '#313442'
  on-surface: '#dfe2f3'
  on-surface-variant: '#bbc9cf'
  inverse-surface: '#dfe2f3'
  inverse-on-surface: '#2c303d'
  outline: '#859398'
  outline-variant: '#3c494e'
  surface-tint: '#3cd7ff'
  primary: '#a8e8ff'
  on-primary: '#003642'
  primary-container: '#00d4ff'
  on-primary-container: '#00586b'
  inverse-primary: '#00677e'
  secondary: '#fff9ef'
  on-secondary: '#3a3000'
  secondary-container: '#ffdb3c'
  on-secondary-container: '#725f00'
  tertiary: '#00ff88'
  on-tertiary: '#003919'
  tertiary-container: '#00df76'
  on-tertiary-container: '#005d2d'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#b4ebff'
  primary-fixed-dim: '#3cd7ff'
  on-primary-fixed: '#001f27'
  on-primary-fixed-variant: '#004e5f'
  secondary-fixed: '#ffe16d'
  secondary-fixed-dim: '#e9c400'
  on-secondary-fixed: '#221b00'
  on-secondary-fixed-variant: '#544600'
  tertiary-fixed: '#60ff99'
  tertiary-fixed-dim: '#00e479'
  on-tertiary-fixed: '#00210c'
  on-tertiary-fixed-variant: '#005228'
  background: '#0f131f'
  on-background: '#dfe2f3'
  surface-variant: '#313442'
typography:
  display-lg:
    fontFamily: Inter
    fontSize: 32px
    fontWeight: '700'
    lineHeight: 40px
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '700'
    lineHeight: 32px
    letterSpacing: -0.01em
  headline-sm:
    fontFamily: Inter
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
  body-lg:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  label-md:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.05em
  label-sm:
    fontFamily: Inter
    fontSize: 10px
    fontWeight: '600'
    lineHeight: 12px
    letterSpacing: 0.08em
  numeric-data:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '700'
    lineHeight: 24px
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  container-margin: 16px
  stack-gap: 12px
  section-gap: 24px
  card-padding: 16px
  inline-gap: 8px
---

## Brand & Style
The design system establishes an elite, institutional-grade atmosphere tailored for high-stakes digital asset trading. It aims to evoke feelings of precision, authority, and technological dominance. 

The aesthetic is a refined **Glassmorphism**, mimicking a high-end trading terminal. It utilizes deep layering, backdrop blurs, and luminous accents to create a sense of three-dimensional space within a mobile viewport. The interface should feel like a specialized hardware tool—dense with information yet impeccably organized. High-performance visuals, such as glowing data points and translucent surfaces, reinforce the "Sherpa" narrative: a sophisticated guide through the complex peaks of the metaverse markets.

## Colors
This design system operates exclusively in a dark "Terminal Mode" to ensure maximum contrast for financial data and reduce eye strain during extended trading sessions.

- **Base Foundation:** The primary background is a deep navy (#0a0e1a), providing a void-like depth.
- **Surface Layering:** Component surfaces use a semi-transparent Slate (#111827) with a 60-80% alpha and a 20px backdrop blur.
- **Accents:** Neon Cyan is used for primary actions, navigation, and the brand's "mountain" motifs. Gold is reserved for premium features, elite tier statuses, and critical highlight data.
- **Semantic Indicators:** Emerald Green represents profit and growth; Crimson Red signifies loss or risk. These must maintain high saturation to "pop" against the dark glass backgrounds.

## Typography
The system relies entirely on **Inter** for its systematic, utilitarian precision. 

- **Headings:** Bold weights (700) are used for portfolio totals and screen titles to provide an immediate visual anchor.
- **Data Display:** For financial figures, use "tabular num" (tnum) OpenType features to ensure columns of numbers align perfectly for easy scanning.
- **Labels:** Small labels use medium/semibold weights with increased letter spacing and uppercase styling to mimic the aesthetic of physical cockpit gauges and military-grade hardware.
- **Hierarchy:** Contrast is achieved through weight and color (e.g., Gold for "Elite" metrics, Cyan for active states) rather than excessive size variations.

## Layout & Spacing
The layout follows a strict **4px/8px grid system** to maintain institutional discipline. 

- **Grid:** A 4-column fluid layout for mobile with 16px side margins. 
- **Density:** Information density is high, but legibility is preserved through consistent use of "stack-gap" (12px) between list items.
- **Vertical Rhythm:** Sections are separated by 24px to give the eye a resting point between different asset classes or data visualizations.
- **Safe Areas:** Ensure bottom navigation does not interfere with the home indicator, maintaining a minimum 34px bottom clearance on modern mobile devices.

## Elevation & Depth
Depth is the core differentiator of this design system. It is achieved through **Tonal Layering** and **Glassmorphism** rather than traditional drop shadows.

- **The Glass Layer:** All cards use a 1px inner stroke. On primary cards, this stroke is a subtle gradient of Cyan-to-Transparent. On "Elite" or "Gold" cards, use a Gold-to-Transparent gradient.
- **Backdrop Blur:** A 20px blur radius is applied to all surface containers, allowing the background colors (or chart gradients) to bleed through softly.
- **Number Glows:** Key financial metrics (like Total Balance) feature an outer glow (`drop-shadow`) matching their semantic color (Cyan, Green, or Red) with a 15% opacity and 12px blur to simulate a luminous display.
- **Separators:** Use 1px solid lines with 10% opacity white to separate data rows within cards, avoiding heavy visual breaks.

## Shapes
The shape language is "Sophisticated Geometric." 

- **Cards & Modals:** Standardized at 16px (`rounded-lg`) to balance the technical nature of the app with a modern, premium feel. 
- **Buttons:** Primary buttons use the same 16px radius. Small tags or chips may use a full pill-shape (3) to differentiate them from interactive action buttons.
- **Icons:** Use linear, 2px stroke icons with sharp or slightly softened corners to match the Inter typeface.

## Components
- **Glass Cards:** The primary container. Must include a 1px border (#ffffff15) and a subtle 2px Cyan/Gold top-edge glow for active or high-priority items.
- **Trading Buttons:** 
    - *Buy:* Solid Emerald Green background with white text.
    - *Sell:* Solid Red background with white text.
    - *Neutral Actions:* Outline buttons with Cyan strokes and semi-transparent fills.
- **Bottom Navigation:** A fixed bar with a 90% opacity navy background and a 40px backdrop blur. Active tabs are highlighted with a Neon Cyan icon and a small 4px glowing dot indicator underneath.
- **Input Fields:** Darker than the surface color, with a 1px Cyan border that "glows" (outer shadow) when focused.
- **Profit/Loss Chips:** Small, high-contrast badges with white text on Emerald or Red backgrounds, using 8px rounded corners.
- **The "Mountain" Logo:** Displayed as a 24x24px Neon Cyan vector peak in the header, paired with "Metaverse Sherpa" in Inter Bold.