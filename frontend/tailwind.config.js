/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        slate: "var(--slate)",
        paper: "var(--paper)",
        field: "var(--field)",
        rule: "var(--rule)",
        ink: "var(--ink)",
        clay: "var(--clay)",
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
