/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "media",
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "Vazirmatn", "system-ui", "sans-serif"],
      },
      colors: {
        cream: { 50: "#fbf9f6", 100: "#f7f3ee", 200: "#ede5da", 300: "#dccfbe" },
        cocoa: {
          400: "#a08672",
          500: "#7d6553",
          600: "#5f4b3d",
          700: "#43352b",
          800: "#2c231d",
          900: "#211a15",
        },
      },
      boxShadow: {
        soft: "0 1px 2px rgb(33 26 21 / 0.04), 0 8px 24px -12px rgb(33 26 21 / 0.18)",
      },
    },
  },
  plugins: [],
};
