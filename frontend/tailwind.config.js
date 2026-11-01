/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        scout: {
          bg: "#061321",
          sidebar: "#0B1B2C",
          "surface-1": "#10243A",
          "surface-2": "#172D45",
          "surface-3": "#203A54",
          border: "#29445F",
          "border-subtle": "#1E354D",
          "text-primary": "#F1F5F9",
          "text-secondary": "#9BAFC4",
          "text-muted": "#71869D",
          cyan: "#28BCEB",
          blue: "#278BC4",
          orange: "#FF781F",
          red: "#EF4444",
          yellow: "#FBBF24",
          green: "#34D399",
        },
      },
      fontFamily: {
        sans: ["Inter", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "Roboto", "sans-serif"],
        mono: ["JetBrains Mono", "SFMono-Regular", "Menlo", "Monaco", "Consolas", "monospace"],
      },
      boxShadow: {
        "scout-card": "0 4px 20px -2px rgba(6, 19, 33, 0.7), 0 0 1px 1px rgba(41, 68, 95, 0.3)",
        "scout-glow": "0 0 15px -3px rgba(40, 188, 235, 0.25)",
        "scout-alert": "0 0 15px -3px rgba(255, 120, 31, 0.3)",
      },
    },
  },
  plugins: [],
};
