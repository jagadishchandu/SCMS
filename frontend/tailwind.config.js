/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{js,jsx}", "./public/index.html"],
  theme: {
    extend: {
      fontFamily: {
        display: ["Outfit", "system-ui", "sans-serif"],
        sans: ["Manrope", "system-ui", "sans-serif"],
      },
      colors: {
        bg: {
          DEFAULT: "#F9F8F6",
          surface: "#FFFFFF",
          subtle: "#F2EFEB",
        },
        ink: {
          DEFAULT: "#2F3E2E",
          soft: "#5C6656",
          muted: "#8A9382",
        },
        primary: {
          DEFAULT: "#4E5B3A",
          hover: "#3A452B",
          light: "#E6EADF",
          foreground: "#FFFFFF",
        },
        secondary: {
          DEFAULT: "#B7A77A",
          hover: "#8A7F4F",
          foreground: "#2F3E2E",
        },
        terracotta: "#D4A373",
        sand: "#E6E1D6",
        sage: "#8F9C82",
        line: {
          DEFAULT: "#E6E1D6",
          subtle: "#F2EFEB",
          strong: "#D5CFC1",
        },
        status: {
          success: "#6B8E23",
          "success-bg": "#F0F4E8",
          warning: "#C49A2C",
          "warning-bg": "#FDF8E8",
          danger: "#C0573B",
          "danger-bg": "#FCECE8",
          info: "#4A7C59",
          "info-bg": "#EDF3EF",
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
