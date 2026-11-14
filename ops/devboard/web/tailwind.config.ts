import type { Config } from "tailwindcss";

// W.Alter colours: pure black surfaces, #01B7FF contrast. The neutrals and state dots are those of the mockup the
// owner validated (2026-11-14); no other palette.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        black: "#000000",
        walter: "#01B7FF",
        line: "#13232c",
        line2: "#1b2f3a",
        row: "#0b161c",
        muted: "#5f7886",
        soft: "#8aa3b0",
        text: "#d7e3ea",
        bright: "#e6f0f5",
        hover: "#07161e",
        sel: "#061823",
        band: "#050b0f",
        ok: "#2ecc71",
        wait: "#ffb020",
        late: "#ff5c5c",
      },
      fontFamily: { sans: ["-apple-system", "BlinkMacSystemFont", "Inter", "Segoe UI", "sans-serif"] },
    },
  },
  plugins: [],
} satisfies Config;
