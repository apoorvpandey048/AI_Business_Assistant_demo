import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class", '[data-theme="dark"]'],
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      colors: {
        ink: "#0b1220",
        // Semantic tokens → CSS vars. Dark mode swaps the var values only,
        // so components keep using bg-surface / text-text-muted / ring-line etc.
        bg: "var(--bg)",
        surface: {
          DEFAULT: "var(--surface)",
          muted: "var(--surface-muted)",
          raised: "var(--surface-raised)",
        },
        text: {
          DEFAULT: "var(--text)",
          strong: "var(--text-strong)",
          muted: "var(--text-muted)",
          faint: "var(--text-faint)",
        },
        line: {
          DEFAULT: "var(--border)",
          strong: "var(--border-strong)",
        },
        accent: {
          DEFAULT: "var(--accent)",
          hover: "var(--accent-hover)",
          soft: "var(--accent-soft)",
        },
        success: { DEFAULT: "var(--success)", soft: "var(--success-soft)" },
        warn: { DEFAULT: "var(--warn)", soft: "var(--warn-soft)" },
        danger: { DEFAULT: "var(--danger)", soft: "var(--danger-soft)" },
        triage: {
          red: "var(--triage-red)",
          "red-soft": "var(--triage-red-soft)",
          green: "var(--triage-green)",
          "green-soft": "var(--triage-green-soft)",
          blue: "var(--triage-blue)",
          "blue-soft": "var(--triage-blue-soft)",
        },
      },
      boxShadow: {
        card: "var(--shadow-sm)",
        pop: "var(--shadow-md)",
        float: "var(--shadow-lg)",
      },
    },
  },
  plugins: [],
};
export default config;
