/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{js,jsx}", "./public/index.html"],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: {
        display: ["Outfit", "system-ui", "sans-serif"],
        sans: ["Manrope", "system-ui", "sans-serif"],
      },
      colors: {
        bg: {
          DEFAULT: "var(--bg)",
          surface: "var(--bg-surface)",
          subtle: "var(--bg-subtle)",
        },
        ink: {
          DEFAULT: "var(--ink)",
          soft: "var(--ink-soft)",
          muted: "var(--ink-muted)",
        },
        primary: {
          DEFAULT: "var(--primary)",
          hover: "var(--primary-hover)",
          light: "var(--primary-light)",
          foreground: "var(--primary-foreground)",
        },
        secondary: {
          DEFAULT: "var(--secondary)",
          hover: "var(--secondary-hover)",
          foreground: "var(--secondary-foreground)",
        },
        terracotta: "var(--terracotta)",
        sand: "var(--sand)",
        sage: "var(--sage)",
        line: {
          DEFAULT: "var(--line)",
          subtle: "var(--line-subtle)",
          strong: "var(--line-strong)",
        },
        status: {
          success: "var(--st-success)",
          "success-bg": "var(--st-success-bg)",
          warning: "var(--st-warning)",
          "warning-bg": "var(--st-warning-bg)",
          danger: "var(--st-danger)",
          "danger-bg": "var(--st-danger-bg)",
          info: "var(--st-info)",
          "info-bg": "var(--st-info-bg)",
        },
      },
      borderRadius: { lg: "0.5rem" },
      boxShadow: {
        soft: "0 1px 2px rgba(47, 62, 46, 0.04), 0 2px 8px rgba(47, 62, 46, 0.05)",
        focus: "0 0 0 3px rgba(78, 91, 58, 0.18)",
      },
      transitionTimingFunction: { custom: "cubic-bezier(0.22, 1, 0.36, 1)" },
    },
  },
  plugins: [],
};
