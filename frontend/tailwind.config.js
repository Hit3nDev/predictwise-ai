/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      // RGB triplets live in index.css so every colour works with opacity modifiers (bg-ink/10).
      colors: {
        ink: "rgb(var(--ink) / <alpha-value>)",       // text, black surfaces
        bone: "rgb(var(--bone) / <alpha-value>)",     // the canvas
        sheet: "rgb(var(--sheet) / <alpha-value>)",   // white surfaces
        line: "rgb(var(--line) / <alpha-value>)",     // hairlines
        mute: "rgb(var(--mute) / <alpha-value>)",     // secondary text
        cobalt: "rgb(var(--cobalt) / <alpha-value>)", // the one accent
        lime: "rgb(var(--lime) / <alpha-value>)",     // highlighter
        signal: "rgb(var(--signal) / <alpha-value>)", // warnings, forecasts
        rail: "rgb(var(--rail) / <alpha-value>)",     // the technical pipeline rail
        railink: "rgb(var(--railink) / <alpha-value>)", // text on the rail
      },
      fontFamily: {
        sans: ["'Bricolage Grotesque'", "'Noto Sans Devanagari'", "'Nirmala UI'", "system-ui", "sans-serif"],
        display: ["Fraunces", "Georgia", "serif"],
        mono: ["'Spline Sans Mono'", "ui-monospace", "Menlo", "monospace"],
      },
      borderRadius: { DEFAULT: "6px", sm: "4px", md: "6px", lg: "10px", xl: "14px", "2xl": "20px" },
      boxShadow: {
        lift: "0 30px 60px -30px rgb(17 17 17 / .35), 0 2px 6px rgb(17 17 17 / .06)",
        ring: "0 0 0 3px rgb(var(--cobalt) / .18)",
      },
      keyframes: {
        rise: { from: { opacity: 0, transform: "translateY(6px)" }, to: { opacity: 1, transform: "none" } },
        slide: { from: { opacity: 0, transform: "translateX(24px)" }, to: { opacity: 1, transform: "none" } },
        pulseDot: { "0%,100%": { opacity: 1 }, "50%": { opacity: .3 } },
      },
      animation: {
        rise: "rise .4s cubic-bezier(.2,.7,.3,1) both",
        slide: "slide .3s cubic-bezier(.2,.7,.3,1) both",
        pulseDot: "pulseDot 2.2s ease-in-out infinite",
      },
    },
  },
  plugins: [],
}
