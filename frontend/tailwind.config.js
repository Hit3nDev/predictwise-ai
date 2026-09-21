/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        slate: "rgb(var(--slate) / <alpha-value>)",
        paper: "rgb(var(--paper) / <alpha-value>)",
        field: "rgb(var(--field) / <alpha-value>)",
        rule: "rgb(var(--rule) / <alpha-value>)",
        ink: "rgb(var(--ink) / <alpha-value>)",
        clay: "rgb(var(--clay) / <alpha-value>)",
      },
      fontFamily: {
        sans: ["Archivo", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
      borderRadius: { DEFAULT: "2px", sm: "2px", md: "2px", lg: "2px" },
    },
  },
  plugins: [],
}
