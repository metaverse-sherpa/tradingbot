/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./**/*.{html,js}"],
  darkMode: "class",
  theme: {
      extend: {
          "colors": {
              "primary": "#ffffff",
              "on-primary-container": "#7d7e82",
              "outline-variant": "#45474a",
              "on-error-container": "#ffdad6",
              "primary-fixed-dim": "#c6c6ca",
              "surface-container-lowest": "#0f131f",
              "on-primary": "#2f3034",
              "primary-fixed": "#e2e2e6",
              "outline": "#8f9094",
              "surface-container-highest": "#353437",
              "secondary-fixed-dim": "#e9c349",
              "surface-dim": "#131316",
              "tertiary-fixed-dim": "#68dba9",
              "on-secondary-fixed-variant": "#574500",
              "on-tertiary": "#003825",
              "surface-container-high": "#2a2a2d",
              "error-container": "#93000a",
              "on-secondary": "#3c2f00",
              "inverse-surface": "#e4e1e5",
              "on-background": "#e4e1e5",
              "on-surface": "#e4e1e5",
              "on-primary-fixed-variant": "#45474a",
              "on-secondary-container": "#342800",
              "inverse-primary": "#5d5e62",
              "secondary-container": "#af8d11",
              "background": "#0f131f",
              "on-tertiary-container": "#009065",
              "surface-bright": "#39393c",
              "tertiary": "#0099ff",
              "surface-tint": "#c6c6ca",
              "primary-container": "#121417",
              "inverse-on-surface": "#303033",
              "on-surface-variant": "#c6c6ca",
              "on-primary-fixed": "#1a1c1f",
              "on-tertiary-fixed": "#002114",
              "on-tertiary-fixed-variant": "#005137",
              "secondary-fixed": "#ffe088",
              "tertiary-fixed": "#85f8c4",
              "surface": "#131620",
              "on-secondary-fixed": "#241a00",
              "error": "#ffb4ab",
              "surface-container-low": "#1b1b1e",
              "surface-variant": "#1f2028",
              "secondary": "#3cd7ff",
              "surface-container": "#1f1f22",
              "tertiary-container": "#00180e",
              "on-error": "#690005"
          },
          "borderRadius": {
              "DEFAULT": "0.125rem",
              "lg": "0.25rem",
              "xl": "0.5rem",
              "full": "0.75rem"
          },
          "spacing": {
              "margin-desktop": "64px",
              "margin-mobile": "20px",
              "gutter": "24px",
              "unit": "4px",
              "container-max": "1440px"
          },
          "fontSize": {
              "headline-md": ["32px", { "lineHeight": "40px", "letterSpacing": "-0.01em", "fontWeight": "500" }],
              "data-display": ["24px", { "lineHeight": "32px", "fontWeight": "500" }],
              "headline-lg-mobile": ["32px", { "lineHeight": "40px", "letterSpacing": "-0.02em", "fontWeight": "600" }],
              "headline-lg": ["48px", { "lineHeight": "56px", "letterSpacing": "-0.02em", "fontWeight": "600" }],
              "body-md": ["16px", { "lineHeight": "24px", "fontWeight": "400" }],
              "data-signal": ["14px", { "lineHeight": "20px", "letterSpacing": "0.02em", "fontWeight": "400" }],
              "label-caps": ["12px", { "lineHeight": "16px", "letterSpacing": "0.1em", "fontWeight": "700" }],
              "body-lg": ["18px", { "lineHeight": "28px", "fontWeight": "400" }]
          }
      }
  },
  plugins: [
    require('@tailwindcss/forms'),
    require('@tailwindcss/container-queries')
  ],
}
