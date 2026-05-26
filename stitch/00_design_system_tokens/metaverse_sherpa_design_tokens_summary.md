# Metaverse Sherpa Design System Tokens

These tokens are extracted from the Metaverse Sherpa design system for use in your development environment.

## 🎨 Color Palette (Tailwind CSS Configuration)

```javascript
module.exports = {
  theme: {
    extend: {
      colors: {
        primary: '#00d4ff', // Institutional Neon Cyan
        background: '#0f131f', // Deep Dark Navy
        surface: {
          DEFAULT: '#0f131f',
          dim: '#0f131f',
          bright: '#353946',
          container: {
            lowest: '#0a0e1a',
            low: '#171b28',
            high: '#2a2e3a',
          }
        },
        on: {
          surface: '#ffffff',
          'surface-variant': '#9ba1b0',
        },
        outline: '#353946',
        error: '#ff4d4d',
        success: '#00e676',
      },
    },
  },
}
```

## 🔡 Typography (Inter)

| Category | Size (px) | Weight | Letter Spacing |
| :--- | :--- | :--- | :--- |
| **Display Large** | 57px | 700 (Bold) | -0.25px |
| **Headline Medium** | 28px | 600 (Semi-Bold) | 0 |
| **Headline Small** | 24px | 600 (Semi-Bold) | 0 |
| **Title Large** | 22px | 500 (Medium) | 0 |
| **Label Medium** | 12px | 500 (Medium) | 0.5px |
| **Body Large** | 16px | 400 (Regular) | 0.5px |

## 📏 Spacing & Layout

- **Container Margin**: 24px (Mobile), 48px (Desktop)
- **Section Gap**: 40px
- **Inline Gap**: 12px
- **Border Radius**: 8px (Round Eight)

## ✨ Effects

- **Glassmorphism**: `backdrop-blur-xl bg-surface/80 border border-white/10`
- **Glow/Shadow**: `drop-shadow-[0_0_8px_rgba(0,212,255,0.4)]`
