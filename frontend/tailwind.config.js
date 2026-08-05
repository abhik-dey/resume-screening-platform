/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: { DEFAULT: "var(--ink)", soft: "var(--ink-soft)", faint: "var(--ink-faint)" },
        surface: { DEFAULT: "var(--surface)", sunk: "var(--surface-sunk)" },
        line: "var(--line)",
        signal: { DEFAULT: "var(--signal)", soft: "var(--signal-soft)", line: "var(--signal-line)" },
        accent: { DEFAULT: "var(--accent)", soft: "var(--accent-soft)" },
        positive: "var(--positive)",
        caution: "var(--caution)",
        negative: "var(--negative)",
      },
      borderRadius: { card: "6px" },
    },
  },
  plugins: [],
};
