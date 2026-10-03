import { defineConfig, presetWind } from "unocss";

// Token names mirror docs/design-system.md section 6.
const colors = {
  primary: { DEFAULT: "#0062CC", hover: "#0052A8", active: "#00428A", fg: "#FFFFFF" },
  surface: { DEFAULT: "#FFFFFF", muted: "#F3F4F6" },
  border: { DEFAULT: "#D1D5DB", strong: "#6B7280" },
  text: { DEFAULT: "#111827", muted: "#4B5563" },
  nav: { DEFAULT: "#111827", fg: "#E5E7EB" },
  focus: "#1D4ED8",
  success: { DEFAULT: "#15803D", soft: "#DCFCE7", ink: "#166534" },
  warning: { DEFAULT: "#B45309", soft: "#FEF3C7", ink: "#92400E" },
  danger: { DEFAULT: "#B91C1C", soft: "#FEE2E2", ink: "#991B1B" },
  info: { DEFAULT: "#1D4ED8", soft: "#DBEAFE", ink: "#1E40AF" },
  tier: {
    a: { DEFAULT: "#15803D", soft: "#DCFCE7", ink: "#14532D" },
    b: { DEFAULT: "#4D7C0F", soft: "#ECFCCB", ink: "#365314" },
    c: { DEFAULT: "#A16207", soft: "#FEF08A", ink: "#713F12" },
    d: { DEFAULT: "#C2410C", soft: "#FFEDD5", ink: "#7C2D12" },
    e: { DEFAULT: "#B91C1C", soft: "#FEE2E2", ink: "#7F1D1D" },
  },
  event: {
    "harsh-brake": "#C2410C",
    "harsh-accel": "#7E22CE",
    "sharp-corner": "#0E7490",
    speeding: "#B91C1C",
    crash: "#111827",
  },
};

const tiers = ["a", "b", "c", "d", "e"];
const statuses = ["success", "warning", "danger", "info"];
const events = ["harsh-brake", "harsh-accel", "sharp-corner", "speeding", "crash"];

const safelist = [
  ...tiers.flatMap((t) => [`bg-tier-${t}`, `bg-tier-${t}-soft`, `text-tier-${t}-ink`]),
  ...statuses.flatMap((s) => [`bg-${s}-soft`, `text-${s}-ink`, `border-${s}`, `text-${s}`]),
  ...events.map((e) => `bg-event-${e}`),
];

export default defineConfig({
  presets: [presetWind()],
  theme: {
    colors,
    fontFamily: {
      sans: 'ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
      mono: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
    },
    boxShadow: {
      sm: "0 1px 2px 0 rgb(17 24 39 / 0.06)",
      md: "0 4px 8px -2px rgb(17 24 39 / 0.12)",
    },
  },
  shortcuts: {
    "kbd-focus":
      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2",
    btn: "inline-flex items-center justify-center gap-2 rounded-md font-medium text-base min-h-10 px-4 kbd-focus transition-colors duration-150 motion-reduce:transition-none disabled:opacity-50 disabled:cursor-not-allowed",
    "btn-primary": "bg-primary text-primary-fg hover:bg-primary-hover active:bg-primary-active",
    "btn-secondary":
      "bg-surface text-primary border border-primary hover:bg-surface-muted active:bg-surface-muted",
    "btn-danger": "bg-danger text-white hover:bg-danger-ink active:bg-danger-ink",
    "btn-ghost": "text-nav-fg border border-white/30 hover:text-white hover:bg-white/10 focus-visible:ring-white focus-visible:ring-offset-nav",
    "btn-sm": "min-h-8 px-3 text-sm",
    "btn-lg": "min-h-12 px-6",
    input:
      "w-full min-h-10 px-3 rounded-md bg-surface text-text text-base border border-border-strong placeholder:text-text-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:border-primary disabled:bg-surface-muted disabled:text-text-muted disabled:cursor-not-allowed aria-[invalid=true]:border-danger",
    card: "bg-surface rounded-lg border border-border shadow-sm p-4 md:p-6",
    pill: "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium",
    "tier-badge": "inline-flex items-center gap-1 rounded-sm px-2 py-0.5 text-xs font-semibold",
    flash: "rounded-md border px-4 py-3 text-sm flex gap-2",
    "nav-link":
      "px-3 py-2 rounded-md text-sm font-medium text-nav-fg hover:text-white hover:bg-white/10 kbd-focus focus-visible:ring-white focus-visible:ring-offset-nav",
  },
  safelist,
});
