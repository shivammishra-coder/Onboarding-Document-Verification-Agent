/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        // Matches the reference dark dashboard theme
        surface: {
          DEFAULT: "#0f1420",
          panel: "#151b2b",
          card: "#1a2236",
          border: "#26304a",
        },
        accent: {
          DEFAULT: "#3b82f6",
          hover: "#2563eb",
        },
        success: "#22c55e",
        warning: "#f59e0b",
        danger: "#ef4444",
      },
    },
  },
  plugins: [],
};
