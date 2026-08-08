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
          DEFAULT: "#4A7CF7",
          50: "#EBF0FE",
          100: "#CBDAFD",
          200: "#A3BDFC",
          300: "#7BA0FA",
          400: "#5E8FF8",
          500: "#4A7CF7",
          600: "#3A64D6",
          700: "#2E50B4",
          800: "#233E92",
          900: "#1A2E70",
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

        // ── Surface / Background — Dashboard-inspired warm darks ─────
        background: "#0F1117",
        surface: {
          DEFAULT: "#181A20",
          50: "#22252E",
          100: "#1E2128",
          200: "#1A1D24",
          300: "#161920",
          400: "#181A20",
        },
        card: {
          DEFAULT: "#1E2028",
          hover: "#252730",
          elevated: "#282A34",
        },
        border: {
          DEFAULT: "#2A2D38",
          light: "#363944",
          subtle: "#1F2230",
        },

        // ── Semantic ──────────────────────────────────────────────────
        foreground: "#F0F2F5",
        muted: "#8B8FA3",
        "muted-foreground": "#6B6F82",

        // ── Status Colors ─────────────────────────────────────────────
        success: {
          DEFAULT: "#10B981",
          light: "#34D399",
          dark: "#059669",
        },
        warning: {
          DEFAULT: "#F59E0B",
          light: "#FBBF24",
          dark: "#D97706",
        },
        danger: {
          DEFAULT: "#EF4444",
          light: "#F87171",
          dark: "#DC2626",
        },
        info: {
          DEFAULT: "#3B82F6",
          light: "#60A5FA",
          dark: "#2563EB",
        },
      },

      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "Fira Code", "monospace"],
      },

      borderRadius: {
        "2xl": "1rem",
        "3xl": "1.25rem",
        "4xl": "1.5rem",
      },

      backdropBlur: {
        xs: "2px",
      },

      boxShadow: {
        glow: "0 0 20px rgba(74, 124, 247, 0.25)",
        "glow-accent": "0 0 20px rgba(230, 57, 70, 0.25)",
        "glow-ghost": "0 0 20px rgba(244, 162, 97, 0.25)",
        "glow-sm": "0 0 10px rgba(74, 124, 247, 0.15)",
        "glow-success": "0 0 12px rgba(16, 185, 129, 0.2)",
        panel:
          "0 4px 24px -4px rgba(0, 0, 0, 0.45), 0 0 0 1px rgba(255, 255, 255, 0.03)",
        "card-hover":
          "0 8px 32px -8px rgba(0, 0, 0, 0.5), 0 0 0 1px rgba(74, 124, 247, 0.08)",
        "card-float":
          "0 12px 40px -12px rgba(0, 0, 0, 0.6), 0 0 0 1px rgba(255, 255, 255, 0.04)",
        inner: "inset 0 2px 4px rgba(0, 0, 0, 0.3)",
      },

      animation: {
        "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "fade-in": "fadeIn 0.4s ease-out",
        "slide-up": "slideUp 0.35s ease-out",
        "slide-down": "slideDown 0.35s ease-out",
        "slide-in-right": "slideInRight 0.35s ease-out",
        "slide-in-left": "slideInLeft 0.3s ease-out",
        shimmer: "shimmer 2s linear infinite",
        "float": "float 6s ease-in-out infinite",
        "glow-pulse": "glowPulse 2s ease-in-out infinite",
        "scale-in": "scaleIn 0.2s ease-out",
      },

      keyframes: {
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        slideUp: {
          "0%": { transform: "translateY(16px)", opacity: "0" },
          "100%": { transform: "translateY(0)", opacity: "1" },
        },
        slideDown: {
          "0%": { transform: "translateY(-16px)", opacity: "0" },
          "100%": { transform: "translateY(0)", opacity: "1" },
        },
        slideInRight: {
          "0%": { transform: "translateX(24px)", opacity: "0" },
          "100%": { transform: "translateX(0)", opacity: "1" },
        },
        slideInLeft: {
          "0%": { transform: "translateX(-24px)", opacity: "0" },
          "100%": { transform: "translateX(0)", opacity: "1" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
        float: {
          "0%, 100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-8px)" },
        },
        glowPulse: {
          "0%, 100%": { boxShadow: "0 0 0 0 rgba(74, 124, 247, 0)" },
          "50%": { boxShadow: "0 0 16px 4px rgba(74, 124, 247, 0.15)" },
        },
        scaleIn: {
          "0%": { transform: "scale(0.95)", opacity: "0" },
          "100%": { transform: "scale(1)", opacity: "1" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
