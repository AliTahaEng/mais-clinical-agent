import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        medical: {
          blue: "#1e40af",
          "blue-light": "#3b82f6",
          green: "#15803d",
          "green-light": "#22c55e",
          red: "#b91c1c",
          "red-light": "#ef4444",
          amber: "#b45309",
          "amber-light": "#f59e0b",
          gray: "#374151",
          "gray-light": "#9ca3af",
        },
      },
    },
  },
  plugins: [],
};

export default config;
