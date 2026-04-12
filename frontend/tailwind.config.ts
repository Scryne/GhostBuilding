import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // ── Core Palette ──────────────────────────────────────────────
        primary: {
          DEFAULT: "#1A3A5C",
          50: "#E8EEF4",
          100: "#C5D4E4",
          200: "#9BB5CE",
          300: "#7196B8",
          400: "#4D78A0",
          500: "#1A3A5C",
          600: "#163250",
          700: "#122943",
          800: "#0E2036",
          900: "#0A172A",
        },
        secondary: {
          DEFAULT: "#2E6DA4",
          50: "#EAF1F8",
          100: "#CBDDED",
          200: "#A1C2DD",
          300: "#77A7CC",
          400: "#518DB8",
          500: "#2E6DA4",
          600: "#275D8C",
          700: "#204D74",
          800: "#193D5C",
          900: "#122D44",
        },
        accent: {
          DEFAULT: "#E63946",
          50: "#FDE8EA",
          100: "#FAC5C9",
          200: "#F49DA4",
          300: "#EE757E",
          400: "#EA5762",
          500: "#E63946",
          600: "#D42D3B",
          700: "#B12431",
          800: "#8E1B27",
          900: "#6B131D",
        },
        ghost: {
          DEFAULT: "#F4A261",
          50: "#FEF3E8",
          100: "#FDE1C4",
          200: "#FBCD9C",
          300: "#F9B974",
          400: "#F6AB68",
          500: "#F4A261",
          600: "#E89040",
          700: "#D67B2A",
          800: "#B06421",
          900: "#8A4E19",
        },
        hidden: {
          DEFAULT: "#E63946",
        },
        censored: {
          DEFAULT: "#9B2226",
          50: "#F8E5E6",
          100: "#EDBFC1",
          200: "#DB9396",
          300: "#C9676C",
          400: "#B74349",
          500: "#9B2226",
          600: "#871D21",
          700: "#70181C",
          800: "#591316",
          900: "#420E11",
        },
        discrepancy: {
          DEFAULT: "#457B9D",
          50: "#EBF2F5",
          100: "#CDDFE7",
          200: "#A8C7D6",
          300: "#83AFC5",
          400: "#6499B1",
          500: "#457B9D",
          600: "#3B6A87",
          700: "#315871",
          800: "#27465B",
          900: "#1D3445",
        },

        // ── Surface / Background ──────────────────────────────────────
        background: "#0A0E1A",
        surface: {
          DEFAULT: "#111827",
          50: "#1C2640",
          100: "#182236",
          200: "#151E30",
          300: "#121A2A",
          400: "#111827",
        },
        border: {
          DEFAULT: "#1F2937",
          light: "#374151",
        },

        // ── Semantic ──────────────────────────────────────────────────
        foreground: "#F9FAFB",
        muted: "#9CA3AF",
        "muted-foreground": "#6B7280",
      },

      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "Fira Code", "monospace"],
      },

      borderRadius: {
        "2xl": "1rem",
        "3xl": "1.25rem",
      },

      backdropBlur: {
        xs: "2px",
      },

      boxShadow: {
        glow: "0 0 20px rgba(46, 109, 164, 0.3)",
        "glow-accent": "0 0 20px rgba(230, 57, 70, 0.3)",
        "glow-ghost": "0 0 20px rgba(244, 162, 97, 0.3)",
        "glow-sm": "0 0 10px rgba(46, 109, 164, 0.2)",
        panel:
          "0 4px 24px -4px rgba(0, 0, 0, 0.4), 0 0 0 1px rgba(255, 255, 255, 0.03)",
      },

      animation: {
        "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "fade-in": "fadeIn 0.3s ease-out",
        "slide-up": "slideUp 0.3s ease-out",
        "slide-down": "slideDown 0.3s ease-out",
        "slide-in-right": "slideInRight 0.3s ease-out",
        shimmer: "shimmer 2s linear infinite",
      },

      keyframes: {
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        slideUp: {
          "0%": { transform: "translateY(12px)", opacity: "0" },
          "100%": { transform: "translateY(0)", opacity: "1" },
        },
        slideDown: {
          "0%": { transform: "translateY(-12px)", opacity: "0" },
          "100%": { transform: "translateY(0)", opacity: "1" },
        },
        slideInRight: {
          "0%": { transform: "translateX(24px)", opacity: "0" },
          "100%": { transform: "translateX(0)", opacity: "1" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
