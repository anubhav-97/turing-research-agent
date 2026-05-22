/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        clarity: "#3b82f6", // blue
        research: "#8b5cf6", // violet
        validator: "#f59e0b", // amber
        synthesis: "#10b981", // emerald
        interrupt: "#ef4444", // red
      },
      animation: {
        "pulse-slow": "pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite",
      },
    },
  },
  plugins: [],
};
