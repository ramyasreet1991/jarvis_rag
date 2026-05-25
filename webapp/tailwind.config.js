/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0d0f14",
        surface: "#161921",
        border: "#1f2430",
        accent: "#00d4aa",
        danger: "#ff4757",
        warn: "#ffa502",
        muted: "#6b7280",
      },
    },
  },
  plugins: [],
};
