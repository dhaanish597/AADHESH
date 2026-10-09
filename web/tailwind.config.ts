import type { Config } from "tailwindcss";

// Tailwind v4 is configured in CSS-first style inside app/globals.css (@theme inline).
// This file now only declares content discovery; all colours, fonts, radii and shadows
// live as named tokens in globals.css and are never slate/zinc/gray defaults.
const config: Config = {
  // v4 discovers template files automatically, but we keep an explicit content list so the
  // repo stays legible to readers who still expect a config file.
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  plugins: [],
};

export default config;
