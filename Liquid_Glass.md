# Liquid Glass Design Reference

## Overview

Liquid Glass is a translucent, refractive design language introduced by Apple at WWDC 2025 on June 9, marking the company's most significant interface overhaul in over a decade. The aesthetic applies across iOS 26, iPadOS 26, macOS Tahoe, watchOS 26, and tvOS 26, establishing a unified visual identity rooted in a single concept: a digital meta-material that behaves like real glass. Apple engineered Liquid Glass to dynamically bend and shape light, reflecting and refracting its surroundings while fluidly adapting to content, context, and user interaction. The result is an interface where controls, navigation bars, app icons, and widgets appear to be crafted from a living, responsive glass substance -- one that produces specular highlights as users move through apps and shifts its translucency between light and dark environments.

Philosophically, Liquid Glass represents a deliberate pivot away from the ultra-flat visual language that had dominated Apple's platforms since iOS 7 in 2013. That decade-long era of flat design stripped interfaces of texture and warmth; Liquid Glass reclaims depth and dimensionality without returning to the skeuomorphic metaphors of earlier years. It occupies a middle ground: surfaces feel tangible and physically present through refraction, shadow, and highlight, yet remain unmistakably digital. The three-layer composition -- highlight, shadow, and illumination -- creates a sense of material authenticity that flat design never achieved. Born from close collaboration between Apple's design and engineering teams, the aesthetic uses real-time rendering to produce glass that genuinely reacts to its environment rather than merely simulating it.

For web designers, Liquid Glass translates into interfaces built on backdrop-filter blurs, layered translucent surfaces, refractive distortion effects, and subtle specular animations. The approach demands careful attention to content legibility -- a challenge Apple itself addressed by offering "Clear" and "Tinted" modes for accessibility. On the web, the aesthetic works best with dark or richly colored backgrounds that give the glass material something meaningful to refract, combined with restrained typography and generous whitespace that let the material language speak. Every surface should feel like it exists within a physical light environment, responding to its context rather than sitting flatly upon it.

---

## Visual Characteristics

### Core Design Traits

- **Refractive translucency** -- surfaces bend and distort the content behind them, creating a lensing effect rather than simple transparency or frosted blur
- **Specular highlights** -- glass elements produce light reflections that shift dynamically as users interact, mimicking how real glass catches light
- **Three-layer material composition** -- every glass surface combines a highlight layer (light casting), shadow layer (depth separation), and illumination layer (adaptive material properties)
- **Adaptive opacity** -- translucency adjusts automatically between light and dark contexts, ensuring the glass always reads as a coherent material
- **Fluid morphing transitions** -- UI elements transform fluidly between states (e.g., tab bars shrink on scroll, then expand on return) rather than snapping between discrete positions
- **Depth blur hierarchy** -- background content blurs at different intensities depending on its distance from the glass surface, establishing spatial relationships
- **Inset glow and inner light** -- subtle inner box-shadows and gradients simulate light trapped within the glass material itself
- **Tinted glass variants** -- glass surfaces can carry color tints derived from surrounding content or brand palette while maintaining their refractive properties
- **Soft environmental shadows** -- diffused, multi-layered shadows ground glass elements in space without harsh edges
- **Rounded, pill-shaped forms** -- generous border-radius values (often fully rounded) complement the liquid, organic quality of the material
- **Content-aware backgrounds** -- the glass material samples and responds to whatever sits behind it, making every instance contextually unique
- **Minimal chrome, maximum material** -- traditional UI borders and dividers are replaced by the glass material itself as the primary means of separating and organizing content

### Design Principles

- Let the material do the work: glass surfaces should communicate hierarchy, boundaries, and interactive states through their physical properties rather than through explicit borders or color fills
- Translucency is functional, not decorative: it reveals what lies beneath a control, helping users understand context and maintain spatial orientation
- Depth should feel natural: layered glass surfaces must create a believable sense of physical stacking without exaggerated parallax or artificial 3D effects
- Light is the primary design element: specular highlights, refractions, and shadow all derive from a coherent simulated light source
- Fluid motion connects states: transitions between UI states should feel like physical transformations of the glass material, not digital switches
- Contrast and legibility come first: the glass effect must never compromise the readability of text or the clarity of interactive affordances
- Restraint amplifies the effect: liquid glass loses its impact when every surface competes for attention; apply it selectively to key interactive and navigational elements
- Context sensitivity is essential: glass surfaces should adapt their blur, tint, and opacity to the content behind them rather than using fixed values

---

## Color Palette

Liquid Glass palettes are deliberately restrained and contextual. Because the glass material derives much of its visual character from what sits behind it, the base palette emphasizes neutral, cool-toned backgrounds and subtle accent colors that harmonize with the refractive effect. Tints are applied sparingly -- the glass itself provides visual richness. The palette below provides a foundation suitable for web implementations, with colors inspired by Apple's Liquid Glass system across light and dark modes.

| Color Name | Hex | Role / Usage |
|------------|-----|-------------|
| **Deep Obsidian** | `#0A0A0F` | Darkest background, page base in dark mode |
| **Slate Depth** | `#1C1C1E` | Primary dark surface, card backdrop |
| **Graphite Mist** | `#2C2C2E` | Elevated surface, secondary dark panels |
| **Silver Fog** | `#F2F2F7` | Light mode background, page base |
| **Cloud White** | `#FFFFFF` | Light mode surfaces, card backdrop |
| **Glass Tint** | `rgba(255,255,255,0.15)` | Default glass fill on dark backgrounds |
| **Glass Tint Light** | `rgba(120,120,128,0.12)` | Default glass fill on light backgrounds |
| **Glass Border** | `rgba(255,255,255,0.25)` | Subtle glass edge highlight on dark |
| **Specular White** | `rgba(255,255,255,0.6)` | Highlight shimmer, inner glow peak |
| **System Blue** | `#007AFF` | Primary accent, interactive elements, links |
| **System Indigo** | `#5856D6` | Secondary accent, tags, supplementary actions |
| **System Teal** | `#5AC8FA` | Tertiary accent, informational states |
| **System Green** | `#34C759` | Success states, positive indicators |
| **Label Primary** | `#000000` / `#FFFFFF` | Primary text (adapts to mode) |
| **Label Secondary** | `rgba(60,60,67,0.6)` / `rgba(235,235,245,0.6)` | Secondary text (adapts to mode) |

### CSS Custom Properties

```css
:root {
  /* Dark mode backgrounds */
  --lg-obsidian: #0a0a0f;
  --lg-slate: #1c1c1e;
  --lg-graphite: #2c2c2e;

  /* Light mode backgrounds */
  --lg-fog: #f2f2f7;
  --lg-white: #ffffff;

  /* Glass material */
  --lg-glass-bg: rgba(255, 255, 255, 0.15);
  --lg-glass-bg-light: rgba(120, 120, 128, 0.12);
  --lg-glass-border: rgba(255, 255, 255, 0.25);
  --lg-glass-border-light: rgba(0, 0, 0, 0.08);
  --lg-glass-specular: rgba(255, 255, 255, 0.6);
  --lg-glass-shadow: rgba(0, 0, 0, 0.25);
  --lg-glass-blur: 20px;
  --lg-glass-saturate: 180%;

  /* System accents */
  --lg-blue: #007aff;
  --lg-indigo: #5856d6;
  --lg-teal: #5ac8fa;
  --lg-green: #34c759;
  --lg-orange: #ff9500;
  --lg-red: #ff3b30;

  /* Text */
  --lg-text-primary: #ffffff;
  --lg-text-secondary: rgba(235, 235, 245, 0.6);
  --lg-text-tertiary: rgba(235, 235, 245, 0.3);

  /* Refraction gradient (for decorative lensing effects) */
  --lg-refraction: linear-gradient(
    135deg,
    rgba(255, 255, 255, 0.1) 0%,
    rgba(255, 255, 255, 0.05) 40%,
    rgba(255, 255, 255, 0.15) 60%,
    rgba(255, 255, 255, 0.05) 100%
  );

  /* Specular highlight gradient */
  --lg-specular-gradient: linear-gradient(
    165deg,
    rgba(255, 255, 255, 0.4) 0%,
    rgba(255, 255, 255, 0.0) 50%
  );
}
```

---

## Typography

### Typeface Philosophy

Liquid Glass typography is defined by clarity and quietness. The glass material provides visual richness, so type must remain clean, highly legible, and unobtrusive. Apple's own implementation uses San Francisco, but for web contexts, system fonts and geometric sans-serifs with excellent screen rendering serve best. Weights lean toward medium and semibold for headings (ensuring readability over refractive backgrounds) with regular weight for body text. Letter-spacing is neutral to slightly tight on display sizes, and line-height is generous. The typography should feel like precision-etched labels on a glass surface -- sharp, refined, and effortlessly readable.

### Recommended Google Fonts

| Font | Weight(s) | Usage | Link |
|------|-----------|-------|------|
| **Inter** | 400, 500, 600, 700 | Body text, UI labels, all-purpose | [fonts.google.com/specimen/Inter](https://fonts.google.com/specimen/Inter) |
| **SF Pro Display** (system) | 400, 500, 600, 700 | Headings (Apple system font fallback) | System font |
| **Plus Jakarta Sans** | 400, 500, 600, 700 | Headings, display text | [fonts.google.com/specimen/Plus+Jakarta+Sans](https://fonts.google.com/specimen/Plus+Jakarta+Sans) |
| **Outfit** | 300, 400, 500, 600 | Headings, clean modern feel | [fonts.google.com/specimen/Outfit](https://fonts.google.com/specimen/Outfit) |
| **Geist** | 400, 500, 600, 700 | Body text, technical UI | [vercel.com/font](https://vercel.com/font) |
| **DM Sans** | 400, 500, 600, 700 | Body text, compact UI | [fonts.google.com/specimen/DM+Sans](https://fonts.google.com/specimen/DM+Sans) |
| **Figtree** | 400, 500, 600 | Body text, friendly and open | [fonts.google.com/specimen/Figtree](https://fonts.google.com/specimen/Figtree) |
| **Sora** | 400, 500, 600, 700 | Display headings, geometric precision | [fonts.google.com/specimen/Sora](https://fonts.google.com/specimen/Sora) |

### Font Pairing Suggestions

| Heading | Body | Vibe |
|---------|------|------|
| **Plus Jakarta Sans** (600) | **Inter** (400) | Clean, modern, Apple-adjacent warmth |
| **Outfit** (600) | **DM Sans** (400) | Geometric precision, compact and sharp |
| **Sora** (600) | **Figtree** (400) | Bold display meets friendly readability |
| **Inter** (700) | **Inter** (400) | Unified system; minimal, engineering-forward |
| **Plus Jakarta Sans** (700) | **DM Sans** (400) | Warm headings, crisp technical body |

### CSS Example

```css
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&family=Inter:wght@400;500;600&display=swap');

body {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  font-weight: 400;
  font-size: 1rem;
  line-height: 1.65;
  color: var(--lg-text-primary);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

h1, h2, h3, h4, h5, h6 {
  font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
  font-weight: 600;
  line-height: 1.2;
  letter-spacing: -0.02em;
  color: var(--lg-text-primary);
}

.lg-display {
  font-family: 'Plus Jakarta Sans', sans-serif;
  font-size: clamp(2.5rem, 5vw, 4.5rem);
  font-weight: 700;
  letter-spacing: -0.03em;
  line-height: 1.08;
}

.lg-subhead {
  font-family: 'Inter', sans-serif;
  font-weight: 400;
  font-size: 1.2rem;
  line-height: 1.6;
  color: var(--lg-text-secondary);
}

.lg-label {
  font-family: 'Inter', sans-serif;
  font-weight: 500;
  font-size: 0.8rem;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--lg-text-tertiary);
}

.lg-caption {
  font-family: 'Inter', sans-serif;
  font-weight: 400;
  font-size: 0.85rem;
  color: var(--lg-text-secondary);
}
```

---

## Layout Principles

- **Content-first hierarchy** -- glass surfaces exist to elevate and frame content, not to decorate empty space; every glass layer should contain meaningful information
- **Floating card architecture** -- primary content lives in glass cards that hover above background imagery or color fields, creating natural depth through layering
- **Centered, constrained containers** -- max-width between 1000-1200px prevents glass surfaces from becoming too wide and losing their material intimacy
- **Generous vertical spacing** -- 80-120px between major sections allows the background to breathe through the glass gaps, reinforcing the layered spatial model
- **Adaptive tab and nav compression** -- following Apple's pattern, navigation elements should fluidly shrink on scroll to maximize content space and expand when the user scrolls back up
- **Minimal grid divisions** -- prefer 2-3 column layouts that give each glass panel enough surface area for the refractive effect to register visually
- **Edge-to-edge hero sections** -- full-width hero areas with vibrant or photographic backgrounds provide rich visual material for the glass to refract
- **Z-axis layering model** -- design in explicit layers (background, mid-ground glass surfaces, foreground content) rather than flat, single-plane layouts
- **Responsive glass scaling** -- on smaller viewports, reduce blur intensity and increase glass opacity slightly to maintain legibility without sacrificing the effect
- **Pill-shaped interactive clusters** -- group related actions into rounded, glass-enclosed toolbars or segmented controls rather than scattering individual buttons
- **Sidebar and panel glass** -- secondary navigation or settings panels benefit from heavier glass tinting to differentiate them from primary content glass

---

## CSS / Design Techniques

### Glass Card

The foundational Liquid Glass component. Combines backdrop blur, saturation boost, subtle border highlighting, and inset glow to create a convincing glass surface.

```css
.lg-card {
  background: var(--lg-glass-bg);
  backdrop-filter: blur(var(--lg-glass-blur)) saturate(var(--lg-glass-saturate));
  -webkit-backdrop-filter: blur(var(--lg-glass-blur)) saturate(var(--lg-glass-saturate));
  border: 1px solid var(--lg-glass-border);
  border-radius: 20px;
  padding: 32px;
  position: relative;
  overflow: hidden;
  box-shadow:
    0 8px 32px var(--lg-glass-shadow),
    inset 0 1px 0 rgba(255, 255, 255, 0.15);
  transition: background 0.3s ease, box-shadow 0.3s ease, transform 0.3s ease;
}

/* Specular highlight layer */
.lg-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 50%;
  background: var(--lg-specular-gradient);
  border-radius: 20px 20px 0 0;
  pointer-events: none;
}

.lg-card:hover {
  background: rgba(255, 255, 255, 0.2);
  box-shadow:
    0 12px 40px rgba(0, 0, 0, 0.3),
    inset 0 1px 0 rgba(255, 255, 255, 0.2);
  transform: translateY(-2px);
}
```

### Glass Button

Buttons rendered as small glass surfaces with their own specular highlight. Tap and hover states intensify the glass effect rather than changing color.

```css
.lg-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px 28px;
  background: rgba(255, 255, 255, 0.18);
  backdrop-filter: blur(12px) saturate(150%);
  -webkit-backdrop-filter: blur(12px) saturate(150%);
  border: 1px solid rgba(255, 255, 255, 0.3);
  border-radius: 980px; /* pill shape */
  color: var(--lg-text-primary);
  font-family: 'Inter', sans-serif;
  font-weight: 600;
  font-size: 0.95rem;
  cursor: pointer;
  text-decoration: none;
  position: relative;
  overflow: hidden;
  transition: all 0.25s ease;
  box-shadow:
    0 2px 12px rgba(0, 0, 0, 0.15),
    inset 0 1px 0 rgba(255, 255, 255, 0.25);
}

.lg-button::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 50%;
  background: linear-gradient(
    180deg,
    rgba(255, 255, 255, 0.3) 0%,
    rgba(255, 255, 255, 0.0) 100%
  );
  border-radius: 980px 980px 0 0;
  pointer-events: none;
}

.lg-button:hover {
  background: rgba(255, 255, 255, 0.25);
  box-shadow:
    0 4px 20px rgba(0, 0, 0, 0.2),
    inset 0 1px 0 rgba(255, 255, 255, 0.35);
  transform: scale(1.02);
}

.lg-button:active {
  transform: scale(0.98);
  background: rgba(255, 255, 255, 0.12);
}

/* Accent variant */
.lg-button--accent {
  background: rgba(0, 122, 255, 0.6);
  backdrop-filter: blur(12px) saturate(180%);
  -webkit-backdrop-filter: blur(12px) saturate(180%);
  border-color: rgba(0, 122, 255, 0.4);
}

.lg-button--accent:hover {
  background: rgba(0, 122, 255, 0.75);
}
```

### Glass Navigation Bar

A navigation bar that uses the Liquid Glass material, becoming more opaque as the user scrolls to maintain content legibility.

```css
.lg-nav {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 100;
  padding: 16px 40px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: rgba(255, 255, 255, 0.08);
  backdrop-filter: blur(24px) saturate(180%);
  -webkit-backdrop-filter: blur(24px) saturate(180%);
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  transition: background 0.3s ease, padding 0.3s ease;
}

.lg-nav.scrolled {
  background: rgba(255, 255, 255, 0.15);
  padding: 10px 40px;
  border-bottom-color: rgba(255, 255, 255, 0.15);
}

.lg-nav__logo {
  font-family: 'Plus Jakarta Sans', sans-serif;
  font-weight: 700;
  font-size: 1.25rem;
  color: var(--lg-text-primary);
  text-decoration: none;
  letter-spacing: -0.01em;
}

.lg-nav__links {
  display: flex;
  gap: 32px;
  list-style: none;
  margin: 0;
  padding: 0;
}

.lg-nav__links a {
  font-family: 'Inter', sans-serif;
  font-weight: 500;
  font-size: 0.9rem;
  color: var(--lg-text-secondary);
  text-decoration: none;
  transition: color 0.2s ease;
  padding: 6px 12px;
  border-radius: 8px;
}

.lg-nav__links a:hover {
  color: var(--lg-text-primary);
  background: rgba(255, 255, 255, 0.08);
}

.lg-nav__cta {
  padding: 8px 20px;
  background: rgba(255, 255, 255, 0.15);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 980px;
  color: var(--lg-text-primary);
  font-weight: 600;
  font-size: 0.85rem;
  text-decoration: none;
  transition: background 0.2s ease;
}

.lg-nav__cta:hover {
  background: rgba(255, 255, 255, 0.25);
}
```

### Hero Section

A full-viewport hero that provides a rich visual backdrop for glass elements to refract. Uses a gradient mesh background that gives the glass material varied content to distort.

```css
.lg-hero {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 120px 40px 80px;
  position: relative;
  overflow: hidden;
}

/* Gradient mesh background for refraction */
.lg-hero__bg {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(ellipse at 25% 20%, rgba(0, 122, 255, 0.35) 0%, transparent 50%),
    radial-gradient(ellipse at 75% 60%, rgba(88, 86, 214, 0.3) 0%, transparent 50%),
    radial-gradient(ellipse at 50% 90%, rgba(90, 200, 250, 0.2) 0%, transparent 50%),
    radial-gradient(ellipse at 10% 80%, rgba(0, 122, 255, 0.15) 0%, transparent 40%);
  background-color: var(--lg-obsidian);
  animation: liquidShift 25s ease-in-out infinite alternate;
}

@keyframes liquidShift {
  0% { transform: scale(1) translate(0, 0); }
  33% { transform: scale(1.05) translate(-2%, 1%); }
  66% { transform: scale(1.02) translate(1%, -1%); }
  100% { transform: scale(1) translate(0, 0); }
}

.lg-hero__content {
  position: relative;
  z-index: 1;
  max-width: 720px;
}

.lg-hero__content h1 {
  font-size: clamp(2.5rem, 6vw, 5rem);
  font-weight: 700;
  letter-spacing: -0.03em;
  line-height: 1.06;
  margin-bottom: 1.5rem;
  color: var(--lg-text-primary);
}

.lg-hero__content p {
  font-size: 1.2rem;
  line-height: 1.7;
  color: var(--lg-text-secondary);
  margin-bottom: 2.5rem;
  max-width: 560px;
  margin-left: auto;
  margin-right: auto;
}
```

### Refraction Distortion Effect

A CSS-only technique that simulates the lensing/warping quality of real glass using SVG filters and backdrop manipulation.

```css
/* SVG filter for refraction (place in HTML) */
/*
<svg style="position:absolute;width:0;height:0">
  <filter id="liquid-refraction">
    <feTurbulence type="fractalNoise" baseFrequency="0.015" numOctaves="3" result="noise" />
    <feDisplacementMap in="SourceGraphic" in2="noise" scale="8" xChannelSelector="R" yChannelSelector="G" />
  </filter>
</svg>
*/

.lg-refract {
  position: relative;
  overflow: hidden;
  border-radius: 24px;
}

.lg-refract::after {
  content: '';
  position: absolute;
  inset: 0;
  backdrop-filter: blur(1px);
  -webkit-backdrop-filter: blur(1px);
  filter: url(#liquid-refraction);
  opacity: 0.6;
  pointer-events: none;
  mix-blend-mode: overlay;
}

/* Simpler CSS-only refraction alternative */
.lg-refract-simple {
  background: var(--lg-glass-bg);
  backdrop-filter: blur(20px) saturate(200%) contrast(1.05);
  -webkit-backdrop-filter: blur(20px) saturate(200%) contrast(1.05);
  border: 1px solid var(--lg-glass-border);
  border-radius: 24px;
  position: relative;
  overflow: hidden;
}

.lg-refract-simple::before {
  content: '';
  position: absolute;
  top: -50%;
  left: -50%;
  width: 200%;
  height: 200%;
  background: conic-gradient(
    from 0deg at 50% 50%,
    rgba(255, 255, 255, 0.04) 0deg,
    rgba(255, 255, 255, 0.0) 60deg,
    rgba(255, 255, 255, 0.06) 120deg,
    rgba(255, 255, 255, 0.0) 180deg,
    rgba(255, 255, 255, 0.04) 240deg,
    rgba(255, 255, 255, 0.0) 300deg,
    rgba(255, 255, 255, 0.04) 360deg
  );
  animation: refractionRotate 20s linear infinite;
  pointer-events: none;
}

@keyframes refractionRotate {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
```

### Specular Shimmer Animation

A highlight effect that simulates light moving across a glass surface as the user scrolls or hovers, adding the "living material" quality central to Liquid Glass.

```css
.lg-shimmer {
  position: relative;
  overflow: hidden;
}

.lg-shimmer::after {
  content: '';
  position: absolute;
  top: -100%;
  left: -100%;
  width: 60%;
  height: 200%;
  background: linear-gradient(
    105deg,
    transparent 40%,
    rgba(255, 255, 255, 0.15) 45%,
    rgba(255, 255, 255, 0.3) 50%,
    rgba(255, 255, 255, 0.15) 55%,
    transparent 60%
  );
  transform: rotate(25deg);
  transition: left 0.8s ease, top 0.8s ease;
  pointer-events: none;
}

.lg-shimmer:hover::after {
  top: -30%;
  left: 120%;
}

/* Continuous ambient shimmer for hero elements */
@keyframes ambientShimmer {
  0% { transform: rotate(25deg) translateX(-200%); }
  100% { transform: rotate(25deg) translateX(200%); }
}

.lg-shimmer--ambient::after {
  animation: ambientShimmer 6s ease-in-out infinite;
  transition: none;
}
```

### Glass Segmented Control

Apple's Liquid Glass prominently features pill-shaped segmented controls with a sliding glass indicator. This pattern translates well to web tab navigation and toggle groups.

```css
.lg-segment {
  display: inline-flex;
  background: rgba(255, 255, 255, 0.06);
  border-radius: 980px;
  padding: 4px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  position: relative;
}

.lg-segment__item {
  padding: 8px 20px;
  font-family: 'Inter', sans-serif;
  font-weight: 500;
  font-size: 0.875rem;
  color: var(--lg-text-secondary);
  background: none;
  border: none;
  border-radius: 980px;
  cursor: pointer;
  transition: color 0.25s ease;
  position: relative;
  z-index: 1;
}

.lg-segment__item:hover {
  color: var(--lg-text-primary);
}

.lg-segment__item.active {
  color: var(--lg-text-primary);
}

/* Sliding glass indicator */
.lg-segment__indicator {
  position: absolute;
  top: 4px;
  bottom: 4px;
  border-radius: 980px;
  background: rgba(255, 255, 255, 0.18);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  border: 1px solid rgba(255, 255, 255, 0.25);
  box-shadow:
    0 2px 8px rgba(0, 0, 0, 0.15),
    inset 0 1px 0 rgba(255, 255, 255, 0.2);
  transition: left 0.3s cubic-bezier(0.4, 0, 0.2, 1), width 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  z-index: 0;
}
```

---

## Design Do's and Don'ts

### Do's

- **Use rich, colorful backgrounds** behind glass surfaces so the translucency and refraction have meaningful visual material to work with
- **Layer glass surfaces at different blur intensities** to create a natural depth hierarchy (heavier blur = further back, lighter blur = closer)
- **Apply specular highlights consistently** from a single implied light direction across all glass elements on the page
- **Test legibility rigorously** -- use the "Tinted" approach (increased opacity) for text-heavy glass surfaces and provide high-contrast fallbacks
- **Embrace pill shapes and rounded corners** -- border-radius values of 16px-24px for panels and 980px for buttons and controls align with the liquid aesthetic
- **Animate transitions fluidly** -- use cubic-bezier easing and transform properties to make state changes feel like physical glass morphing
- **Provide backdrop-filter fallbacks** -- for browsers or devices that do not support backdrop-filter, degrade to a solid semi-transparent background with appropriate opacity
- **Keep the glass palette neutral** -- tint glass surfaces subtly rather than using saturated color fills that fight with the refractive effect

### Don'ts

- **Don't use Liquid Glass on flat white or solid-color backgrounds** -- without visual complexity behind the glass, the effect reads as a basic semi-transparent box with no refractive character
- **Don't over-blur** -- excessive blur values (>30px) destroy the lensing quality and make surfaces look like frosted shower doors rather than refined glass
- **Don't stack too many glass layers** -- each layer of backdrop-filter is computationally expensive and visually muddying; limit to 2-3 overlapping glass surfaces
- **Don't mix glass with heavy borders or drop shadows** -- the material itself should define boundaries; adding thick borders contradicts the glass metaphor
- **Don't use small text on glass without contrast reinforcement** -- body text below 14px on glass surfaces requires a solid background chip or increased glass opacity
- **Don't apply uniform glass treatment everywhere** -- if every element is glass, nothing feels special; reserve the effect for key interactive and navigational surfaces
- **Don't ignore performance** -- backdrop-filter with blur is GPU-intensive; reduce blur values and disable animations on low-power devices and older mobile browsers
- **Don't forget dark mode adaptation** -- glass that looks elegant on dark backgrounds can wash out entirely in light mode; adjust tint, border, and shadow for each context

---

## Related Aesthetics

| Aesthetic | Relationship |
|-----------|-------------|
| **Glassmorphism** | Direct predecessor and technical foundation; Liquid Glass extends glassmorphism with refraction, specular highlights, and adaptive material behavior |
| **Frutiger Aero** | Shares glossy, nature-integrated transparency; Liquid Glass evolves this into a more refined, less decorative material language |
| **Dark Aero** | Dark translucent surfaces overlap significantly; Liquid Glass adds refractive lensing and fluid motion to Dark Aero's static panels |
| **Neumorphism** | Both pursue tactile, 3D surface quality; neumorphism uses shadow extrusion while Liquid Glass uses transparency and light refraction |
| **Flat Design** | Philosophical opposite; Liquid Glass is a deliberate departure from flat design's rejection of depth, shadow, and material texture |
| **Material Design** | Google's elevation/shadow system parallels Liquid Glass's layering model, but uses opaque surfaces rather than transparent ones |
| **Skeuomorphism** | The original Apple design language Liquid Glass partially revives; both pursue physical realism, but Liquid Glass abstracts it to a pure material rather than mimicking real objects |
| **Aurora Gradient** | Gradient mesh backgrounds pair naturally with Liquid Glass overlays; aurora provides the colorful substrate that glass refracts |
| **Minimalism** | Liquid Glass requires minimalist UI structure to work -- cluttered interfaces prevent the material from being perceived |
| **Claymorphism** | Both add dimensionality to flat UI; claymorphism uses soft, matte, clay-like surfaces while Liquid Glass uses hard, transparent, light-catching ones |

---

## Quick-Start HTML Template

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Liquid Glass Page</title>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    :root {
      --lg-obsidian: #0a0a0f;
      --lg-slate: #1c1c1e;
      --lg-graphite: #2c2c2e;
      --lg-glass-bg: rgba(255, 255, 255, 0.12);
      --lg-glass-border: rgba(255, 255, 255, 0.2);
      --lg-glass-specular: rgba(255, 255, 255, 0.6);
      --lg-glass-shadow: rgba(0, 0, 0, 0.25);
      --lg-glass-blur: 20px;
      --lg-glass-saturate: 180%;
      --lg-blue: #007aff;
      --lg-indigo: #5856d6;
      --lg-teal: #5ac8fa;
      --lg-green: #34c759;
      --lg-text-primary: #ffffff;
      --lg-text-secondary: rgba(235, 235, 245, 0.6);
      --lg-text-tertiary: rgba(235, 235, 245, 0.3);
      --lg-specular-gradient: linear-gradient(
        165deg,
        rgba(255, 255, 255, 0.35) 0%,
        rgba(255, 255, 255, 0.0) 50%
      );
    }

    * {
      margin: 0;
      padding: 0;
      box-sizing: border-box;
    }

    body {
      background: var(--lg-obsidian);
      color: var(--lg-text-secondary);
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      font-weight: 400;
      line-height: 1.65;
      overflow-x: hidden;
      -webkit-font-smoothing: antialiased;
      -moz-osx-font-smoothing: grayscale;
    }

    h1, h2, h3, h4 {
      font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
      font-weight: 600;
      color: var(--lg-text-primary);
      line-height: 1.2;
      letter-spacing: -0.02em;
    }

    /* ----------------------------------------
       SVG Filter for subtle refraction
    ---------------------------------------- */
    .svg-filters {
      position: absolute;
      width: 0;
      height: 0;
    }

    /* ----------------------------------------
       Navigation
    ---------------------------------------- */
    .nav {
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      z-index: 100;
      padding: 18px 40px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      background: rgba(255, 255, 255, 0.06);
      backdrop-filter: blur(24px) saturate(180%);
      -webkit-backdrop-filter: blur(24px) saturate(180%);
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
      transition: background 0.3s ease, padding 0.3s ease;
    }

    .nav.scrolled {
      background: rgba(255, 255, 255, 0.12);
      padding: 12px 40px;
    }

    .nav__logo {
      font-family: 'Plus Jakarta Sans', sans-serif;
      font-weight: 700;
      font-size: 1.25rem;
      color: var(--lg-text-primary);
      text-decoration: none;
    }

    .nav__links {
      display: flex;
      gap: 8px;
      list-style: none;
    }

    .nav__links a {
      font-family: 'Inter', sans-serif;
      font-weight: 500;
      font-size: 0.875rem;
      color: var(--lg-text-secondary);
      text-decoration: none;
      padding: 6px 14px;
      border-radius: 8px;
      transition: color 0.2s ease, background 0.2s ease;
    }

    .nav__links a:hover {
      color: var(--lg-text-primary);
      background: rgba(255, 255, 255, 0.08);
    }

    .nav__cta {
      padding: 8px 20px;
      background: rgba(255, 255, 255, 0.15);
      backdrop-filter: blur(8px);
      -webkit-backdrop-filter: blur(8px);
      border: 1px solid rgba(255, 255, 255, 0.2);
      border-radius: 980px;
      color: var(--lg-text-primary);
      font-family: 'Inter', sans-serif;
      font-weight: 600;
      font-size: 0.85rem;
      text-decoration: none;
      transition: background 0.2s ease;
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.15);
    }

    .nav__cta:hover {
      background: rgba(255, 255, 255, 0.25);
    }

    /* ----------------------------------------
       Hero Section
    ---------------------------------------- */
    .hero {
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      text-align: center;
      padding: 120px 40px 80px;
      position: relative;
      overflow: hidden;
    }

    .hero__bg {
      position: absolute;
      inset: 0;
      background:
        radial-gradient(ellipse at 30% 25%, rgba(0, 122, 255, 0.3) 0%, transparent 55%),
        radial-gradient(ellipse at 70% 65%, rgba(88, 86, 214, 0.25) 0%, transparent 50%),
        radial-gradient(ellipse at 50% 85%, rgba(90, 200, 250, 0.2) 0%, transparent 45%),
        radial-gradient(ellipse at 15% 70%, rgba(52, 199, 89, 0.12) 0%, transparent 40%);
      background-color: var(--lg-obsidian);
      animation: bgShift 25s ease-in-out infinite alternate;
    }

    @keyframes bgShift {
      0%   { transform: scale(1) translate(0, 0); }
      33%  { transform: scale(1.04) translate(-1.5%, 1%); }
      66%  { transform: scale(1.02) translate(1%, -0.5%); }
      100% { transform: scale(1) translate(0, 0); }
    }

    .hero__content {
      position: relative;
      z-index: 1;
      max-width: 700px;
    }

    .hero__content h1 {
      font-size: clamp(2.5rem, 6vw, 4.8rem);
      font-weight: 700;
      letter-spacing: -0.035em;
      line-height: 1.06;
      margin-bottom: 1.5rem;
    }

    .hero__content p {
      font-size: 1.15rem;
      line-height: 1.7;
      margin-bottom: 2.5rem;
      max-width: 540px;
      margin-left: auto;
      margin-right: auto;
    }

    /* ----------------------------------------
       Glass Button
    ---------------------------------------- */
    .btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      padding: 14px 32px;
      background: rgba(255, 255, 255, 0.16);
      backdrop-filter: blur(12px) saturate(150%);
      -webkit-backdrop-filter: blur(12px) saturate(150%);
      border: 1px solid rgba(255, 255, 255, 0.28);
      border-radius: 980px;
      color: var(--lg-text-primary);
      font-family: 'Inter', sans-serif;
      font-weight: 600;
      font-size: 0.95rem;
      cursor: pointer;
      text-decoration: none;
      position: relative;
      overflow: hidden;
      transition: all 0.25s ease;
      box-shadow:
        0 2px 12px rgba(0, 0, 0, 0.15),
        inset 0 1px 0 rgba(255, 255, 255, 0.25);
    }

    .btn::before {
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      height: 50%;
      background: linear-gradient(180deg, rgba(255, 255, 255, 0.25) 0%, rgba(255, 255, 255, 0.0) 100%);
      border-radius: 980px 980px 0 0;
      pointer-events: none;
    }

    .btn:hover {
      background: rgba(255, 255, 255, 0.24);
      box-shadow:
        0 4px 20px rgba(0, 0, 0, 0.2),
        inset 0 1px 0 rgba(255, 255, 255, 0.35);
      transform: translateY(-1px);
    }

    .btn:active {
      transform: scale(0.98);
      background: rgba(255, 255, 255, 0.10);
    }

    .btn--accent {
      background: rgba(0, 122, 255, 0.55);
      border-color: rgba(0, 122, 255, 0.35);
    }

    .btn--accent:hover {
      background: rgba(0, 122, 255, 0.7);
    }

    .hero__buttons {
      display: flex;
      gap: 16px;
      justify-content: center;
      flex-wrap: wrap;
    }

    /* ----------------------------------------
       Features Section
    ---------------------------------------- */
    .features {
      padding: 100px 40px;
      max-width: 1160px;
      margin: 0 auto;
      position: relative;
      z-index: 1;
    }

    .features__header {
      text-align: center;
      margin-bottom: 64px;
    }

    .features__header h2 {
      font-size: clamp(1.8rem, 3vw, 2.5rem);
      margin-bottom: 1rem;
    }

    .features__header p {
      max-width: 520px;
      margin: 0 auto;
      font-size: 1.05rem;
    }

    .features__grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 24px;
    }

    /* ----------------------------------------
       Glass Card
    ---------------------------------------- */
    .glass-card {
      background: var(--lg-glass-bg);
      backdrop-filter: blur(var(--lg-glass-blur)) saturate(var(--lg-glass-saturate));
      -webkit-backdrop-filter: blur(var(--lg-glass-blur)) saturate(var(--lg-glass-saturate));
      border: 1px solid var(--lg-glass-border);
      border-radius: 20px;
      padding: 36px;
      position: relative;
      overflow: hidden;
      box-shadow:
        0 8px 32px var(--lg-glass-shadow),
        inset 0 1px 0 rgba(255, 255, 255, 0.12);
      transition: background 0.3s ease, box-shadow 0.3s ease, transform 0.3s ease;
    }

    .glass-card::before {
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      height: 45%;
      background: var(--lg-specular-gradient);
      border-radius: 20px 20px 0 0;
      pointer-events: none;
    }

    .glass-card:hover {
      background: rgba(255, 255, 255, 0.17);
      box-shadow:
        0 12px 40px rgba(0, 0, 0, 0.3),
        inset 0 1px 0 rgba(255, 255, 255, 0.18);
      transform: translateY(-3px);
    }

    .glass-card__icon {
      width: 52px;
      height: 52px;
      border-radius: 14px;
      display: flex;
      align-items: center;
      justify-content: center;
      margin-bottom: 20px;
      background: rgba(255, 255, 255, 0.08);
      border: 1px solid rgba(255, 255, 255, 0.1);
    }

    .glass-card h3 {
      font-size: 1.15rem;
      margin-bottom: 0.75rem;
    }

    .glass-card p {
      font-size: 0.95rem;
      line-height: 1.65;
    }

    /* ----------------------------------------
       Showcase / Stats Section
    ---------------------------------------- */
    .showcase {
      padding: 100px 40px;
      max-width: 1160px;
      margin: 0 auto;
      position: relative;
      z-index: 1;
    }

    .showcase__header {
      text-align: center;
      margin-bottom: 64px;
    }

    .showcase__header h2 {
      font-size: clamp(1.8rem, 3vw, 2.5rem);
      margin-bottom: 1rem;
    }

    .stats-row {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 24px;
    }

    .stat-card {
      text-align: center;
      background: rgba(255, 255, 255, 0.07);
      backdrop-filter: blur(16px) saturate(160%);
      -webkit-backdrop-filter: blur(16px) saturate(160%);
      border: 1px solid rgba(255, 255, 255, 0.12);
      border-radius: 20px;
      padding: 40px 24px;
      position: relative;
      overflow: hidden;
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.1);
    }

    .stat-card::before {
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      height: 50%;
      background: linear-gradient(165deg, rgba(255,255,255,0.2) 0%, transparent 50%);
      pointer-events: none;
    }

    .stat-card .number {
      font-family: 'Plus Jakarta Sans', sans-serif;
      font-size: 2.5rem;
      font-weight: 700;
      color: var(--lg-text-primary);
      margin-bottom: 0.5rem;
      letter-spacing: -0.02em;
    }

    .stat-card .label {
      font-size: 0.85rem;
      color: var(--lg-text-tertiary);
      text-transform: uppercase;
      letter-spacing: 0.04em;
      font-weight: 500;
    }

    /* ----------------------------------------
       CTA Section
    ---------------------------------------- */
    .cta {
      text-align: center;
      padding: 100px 40px;
      position: relative;
      z-index: 1;
    }

    .cta__inner {
      background: rgba(255, 255, 255, 0.08);
      backdrop-filter: blur(24px) saturate(180%);
      -webkit-backdrop-filter: blur(24px) saturate(180%);
      border: 1px solid rgba(255, 255, 255, 0.15);
      border-radius: 28px;
      padding: 72px 48px;
      max-width: 800px;
      margin: 0 auto;
      position: relative;
      overflow: hidden;
      box-shadow:
        0 16px 48px rgba(0, 0, 0, 0.25),
        inset 0 1px 0 rgba(255, 255, 255, 0.15);
    }

    .cta__inner::before {
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      height: 40%;
      background: linear-gradient(165deg, rgba(255,255,255,0.25) 0%, transparent 50%);
      border-radius: 28px 28px 0 0;
      pointer-events: none;
    }

    .cta h2 {
      font-size: clamp(1.8rem, 3vw, 2.4rem);
      margin-bottom: 1rem;
    }

    .cta p {
      margin-bottom: 2rem;
      font-size: 1.05rem;
      max-width: 480px;
      margin-left: auto;
      margin-right: auto;
    }

    /* ----------------------------------------
       Footer
    ---------------------------------------- */
    footer {
      text-align: center;
      padding: 48px 40px;
      font-size: 0.85rem;
      color: var(--lg-text-tertiary);
      position: relative;
      z-index: 1;
      border-top: 1px solid rgba(255, 255, 255, 0.06);
    }

    footer a {
      color: var(--lg-text-secondary);
      text-decoration: none;
    }

    footer a:hover {
      color: var(--lg-text-primary);
    }

    /* ----------------------------------------
       Responsive
    ---------------------------------------- */
    @media (max-width: 768px) {
      .nav {
        padding: 14px 20px;
      }

      .nav.scrolled {
        padding: 10px 20px;
      }

      .nav__links {
        display: none;
      }

      .hero {
        min-height: 80vh;
        padding: 100px 24px 60px;
      }

      .hero__buttons {
        flex-direction: column;
        align-items: center;
      }

      .features, .showcase, .cta {
        padding: 60px 20px;
      }

      .features__grid {
        grid-template-columns: 1fr;
      }

      .stats-row {
        grid-template-columns: repeat(2, 1fr);
      }

      .cta__inner {
        padding: 48px 24px;
      }

      .glass-card {
        padding: 28px;
        backdrop-filter: blur(12px) saturate(160%);
        -webkit-backdrop-filter: blur(12px) saturate(160%);
      }
    }

    @media (max-width: 480px) {
      .stats-row {
        grid-template-columns: 1fr;
      }
    }

    /* ----------------------------------------
       Reduced motion preference
    ---------------------------------------- */
    @media (prefers-reduced-motion: reduce) {
      .hero__bg {
        animation: none;
      }

      .glass-card,
      .btn {
        transition: none;
      }
    }
  </style>
</head>
<body>

  <!-- SVG Filter for refraction effects -->
  <svg class="svg-filters" aria-hidden="true">
    <filter id="liquid-refraction">
      <feTurbulence type="fractalNoise" baseFrequency="0.015" numOctaves="3" result="noise" />
      <feDisplacementMap in="SourceGraphic" in2="noise" scale="6" xChannelSelector="R" yChannelSelector="G" />
    </filter>
  </svg>

  <!-- Gradient mesh background -->
  <div class="hero__bg" style="position:fixed;z-index:0;"></div>

  <!-- Navigation -->
  <nav class="nav" id="mainNav">
    <a href="#" class="nav__logo">LiquidGlass</a>
    <ul class="nav__links">
      <li><a href="#features">Features</a></li>
      <li><a href="#showcase">Showcase</a></li>
      <li><a href="#about">About</a></li>
    </ul>
    <a href="#cta" class="nav__cta">Get Started</a>
  </nav>

  <!-- Hero -->
  <section class="hero">
    <div class="hero__content">
      <h1>Interfaces that feel like light through glass</h1>
      <p>Experience a new material language where every surface reflects,
        refracts, and responds to its environment with fluid elegance.</p>
      <div class="hero__buttons">
        <a href="#features" class="btn btn--accent">Explore Features</a>
        <a href="#showcase" class="btn">View Showcase</a>
      </div>
    </div>
  </section>

  <!-- Features -->
  <section class="features" id="features">
    <div class="features__header">
      <h2>Crafted with light</h2>
      <p>Every element is a living surface that adapts to content,
        context, and interaction.</p>
    </div>
    <div class="features__grid">

      <div class="glass-card">
        <div class="glass-card__icon">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="rgba(0,122,255,0.9)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 2L2 7l10 5 10-5-10-5z"/>
            <path d="M2 17l10 5 10-5"/>
            <path d="M2 12l10 5 10-5"/>
          </svg>
        </div>
        <h3>Layered Depth</h3>
        <p>Glass surfaces stack in space, each layer refracting what lies beneath
          to create a natural sense of physical hierarchy.</p>
      </div>

      <div class="glass-card">
        <div class="glass-card__icon">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="rgba(88,86,214,0.9)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="5"/>
            <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/>
          </svg>
        </div>
        <h3>Dynamic Light</h3>
        <p>Specular highlights shift as users interact, creating the sensation
          of a real material responding to a coherent light source.</p>
      </div>

      <div class="glass-card">
        <div class="glass-card__icon">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="rgba(90,200,250,0.9)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
          </svg>
        </div>
        <h3>Adaptive Clarity</h3>
        <p>Glass opacity and tint adjust automatically between light and dark contexts,
          ensuring readability without sacrificing the material effect.</p>
      </div>

      <div class="glass-card">
        <div class="glass-card__icon">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="rgba(52,199,89,0.9)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
            <path d="M3 9h18M9 21V9"/>
          </svg>
        </div>
        <h3>Fluid Motion</h3>
        <p>Transitions between states feel like physical transformations
          of the glass material -- morphing, not switching.</p>
      </div>

      <div class="glass-card">
        <div class="glass-card__icon">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="rgba(255,149,0,0.9)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
            <circle cx="12" cy="12" r="3"/>
          </svg>
        </div>
        <h3>Contextual Surfaces</h3>
        <p>Each glass panel samples its surroundings, making
          every instance visually unique to its placement on the page.</p>
      </div>

      <div class="glass-card">
        <div class="glass-card__icon">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="rgba(255,59,48,0.9)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/>
            <line x1="4" y1="22" x2="4" y2="15"/>
          </svg>
        </div>
        <h3>Accessible by Design</h3>
        <p>Tinted glass modes increase opacity for enhanced legibility,
          ensuring the aesthetic never compromises usability.</p>
      </div>

    </div>
  </section>

  <!-- Showcase / Stats -->
  <section class="showcase" id="showcase">
    <div class="showcase__header">
      <h2>The material in numbers</h2>
      <p style="max-width:480px;margin:0 auto;font-size:1.05rem;">Liquid Glass is engineered for real-time rendering
        across every device in the ecosystem.</p>
    </div>
    <div class="stats-row">
      <div class="stat-card">
        <div class="number">3</div>
        <div class="label">Material Layers</div>
      </div>
      <div class="stat-card">
        <div class="number">60fps</div>
        <div class="label">Render Target</div>
      </div>
      <div class="stat-card">
        <div class="number">5</div>
        <div class="label">Platforms Unified</div>
      </div>
      <div class="stat-card">
        <div class="number">2025</div>
        <div class="label">Year Introduced</div>
      </div>
    </div>
  </section>

  <!-- CTA -->
  <section class="cta" id="cta">
    <div class="cta__inner">
      <h2>Start building with glass</h2>
      <p>Bring the depth, light, and fluidity of Liquid Glass
        to your next web project.</p>
      <a href="#" class="btn btn--accent">Get Started Free</a>
    </div>
  </section>

  <!-- Footer -->
  <footer>
    <p>Built with the Liquid Glass aesthetic. Translucent, refractive, alive.</p>
  </footer>

  <!-- Scroll behavior for nav -->
  <script>
    const nav = document.getElementById('mainNav');
    window.addEventListener('scroll', () => {
      if (window.scrollY > 40) {
        nav.classList.add('scrolled');
      } else {
        nav.classList.remove('scrolled');
      }
    });
  </script>

</body>
</html>
```

---

## Implementation Tips

- **Always provide a backdrop-filter fallback** -- wrap glass styles in `@supports (backdrop-filter: blur(1px))` and supply a solid semi-transparent background (e.g., `rgba(30, 30, 30, 0.85)`) for unsupported browsers so the interface remains usable
- **Throttle blur on low-power devices** -- use CSS `@media (prefers-reduced-motion: reduce)` to disable animations, and consider reducing blur from 20px to 8-10px on mobile to prevent jank and battery drain
- **Use `will-change: transform` sparingly** -- applying it to glass cards that animate on hover tells the browser to composite them on the GPU, but overuse can increase memory consumption significantly
- **Test against varied backgrounds** -- because glass appearance depends on what it refracts, verify your glass components against light photos, dark gradients, solid colors, and text-heavy backgrounds to ensure consistent quality
- **Pair with a gradient mesh background** -- static solid backgrounds make glass look flat; use 3-4 radial gradients with subtle animation to give the glass material something dynamic to interact with
- **Mind the contrast ratio** -- WCAG 2.1 requires 4.5:1 for normal text; on glass surfaces, measure contrast against the worst-case background scenario (lightest area behind the glass) and increase opacity or add a text-shadow fallback
- **Limit glass nesting** -- stacking backdrop-filter elements (a glass card inside a glass nav inside a glass page wrapper) compounds blur and kills performance; keep the glass hierarchy to a maximum of 2 overlapping layers
- **Consider a "Tinted" toggle** -- following Apple's own accessibility concession, offer users a high-opacity alternative mode that preserves the rounded, layered layout but increases glass fill opacity to 60-80% for improved readability
