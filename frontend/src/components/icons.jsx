/* Line icons on a 24px grid, drawn inline so the app ships no icon library. */

const P = {
  spark: "M12 3l1.9 4.9L19 9.8l-4.1 3.3L16.2 18 12 15.3 7.8 18l1.3-4.9L5 9.8l5.1-1.9z",
  upload: "M12 16V4m0 0l-4 4m4-4l4 4M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2",
  file: "M14 3H7a2 2 0 00-2 2v14a2 2 0 002 2h10a2 2 0 002-2V8zM14 3v5h5M9 13h6M9 17h4",
  store: "M4 10l1.5-5h13L20 10M4 10h16M4 10v9a1 1 0 001 1h14a1 1 0 001-1v-9M9 20v-5h6v5",
  users: "M16 19v-1a4 4 0 00-4-4H7a4 4 0 00-4 4v1M9.5 10a3.5 3.5 0 100-7 3.5 3.5 0 000 7zM21 19v-1a4 4 0 00-3-3.9M15.5 3.2a3.5 3.5 0 010 6.6",
  cake: "M4 20h16M5 20v-6a2 2 0 012-2h10a2 2 0 012 2v6M5 16c1.5 1 3 1 4.5 0s3-1 4.5 0 3 1 5 0M12 12V8M12 5.5v.01",
  basket: "M5 10h14l-1.5 9a2 2 0 01-2 1.7h-7a2 2 0 01-2-1.7zM9 10l3-6 3 6M10 14v3M14 14v3",
  send: "M5 12h13M13 6l6 6-6 6",
  up: "M12 19V5M5 12l7-7 7 7",
  mic: "M12 15a3 3 0 003-3V6a3 3 0 00-6 0v6a3 3 0 003 3zM19 11a7 7 0 01-14 0M12 18v3",
  sound: "M4 10v4h4l5 4V6l-5 4H4zM16 9a4 4 0 010 6M18.5 6.5a8 8 0 010 11",
  lock: "M6 11h12v9H6zM8.5 11V7.5a3.5 3.5 0 017 0V11",
  share: "M4 12v7a1 1 0 001 1h14a1 1 0 001-1v-7M16 6l-4-4-4 4M12 2v13",
  download: "M12 4v12m0 0l-4-4m4 4l4-4M4 18v1a1 1 0 001 1h14a1 1 0 001-1v-1",
  swap: "M7 4L3 8l4 4M3 8h14M17 20l4-4-4-4M21 16H7",
  compare: "M9 3v18M15 3v18M4 7h5M4 12h5M15 12h5M15 17h5",
  check: "M5 12.5l4.5 4.5L19 7.5",
  chart: "M4 20V10M10 20V4M16 20v-7M22 20H2",
  shield: "M12 3l8 3v6c0 4.5-3.4 8.2-8 9-4.6-.8-8-4.5-8-9V6z",
  bolt: "M13 2L4 14h7l-1 8 9-12h-7z",
  cloud: "M7 18a4.5 4.5 0 01-.6-8.96A6 6 0 0118 9a4.5 4.5 0 01-.5 9z",
  arrow: "M5 12h14M13 6l6 6-6 6",
  chevron: "M9 6l6 6-6 6",
  globe: "M12 21a9 9 0 100-18 9 9 0 000 18zM3.5 9h17M3.5 15h17M12 3a14 14 0 010 18M12 3a14 14 0 000 18",
  x: "M6 6l12 12M18 6L6 18",
  info: "M12 21a9 9 0 100-18 9 9 0 000 18zM12 11v5M12 8v.01",
  menu: "M4 7h16M4 12h16M4 17h16",
  sliders: "M4 7h9M17 7h3M4 17h3M11 17h9M13 4.5v5M7 14.5v5",
  plus: "M12 5v14M5 12h14",
  minus: "M5 12h14",
  copy: "M9 9h11v11H9zM4 15V4h11",
  external: "M14 4h6v6M20 4l-9 9M19 14v5a1 1 0 01-1 1H5a1 1 0 01-1-1V6a1 1 0 011-1h5",
  clock: "M12 21a9 9 0 100-18 9 9 0 000 18zM12 7v5l3 2",
  sun: "M12 17a5 5 0 100-10 5 5 0 000 10zM12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4",
  moon: "M20 14.5A8 8 0 019.5 4a8 8 0 1010.5 10.5z",
  key: "M14 10a4 4 0 10-3.9 4l1.9-1.9M15 10l5-5M17 5l2 2M10 14l-1.5 1.5M20 4l-1 1",
  book: "M4 5a2 2 0 012-2h13v16H6a2 2 0 00-2 2zM4 19V5M8 3v16",
  grid: "M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z",
  search: "M11 18a7 7 0 100-14 7 7 0 000 14zM20 20l-4-4",
};

export function Icon({ name, size = 18, className = "", strokeWidth = 1.8 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d={P[name] || P.spark} />
    </svg>
  );
}

/* The mark: a disc in the text colour with a lime moon rising at its edge. Today's records,
   tomorrow's answer. It follows the theme (dark disc on paper, light disc on the dark canvas);
   tone="paper" draws it for the technical rail. */
export function LogoMark({ size = 28, tone = "ink", className = "" }) {
  const base = tone === "paper" ? "rgb(var(--railink))" : "rgb(var(--ink))";
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" className={className} aria-hidden="true">
      <circle cx="13" cy="19" r="10" style={{ fill: base }} />
      <circle cx="23.5" cy="8.5" r="5.5" fill="#D6F546" strokeWidth="2" style={{ stroke: base }} />
    </svg>
  );
}

/* The same mark, thinking: the moon dips into the disc and back. */
export function ThinkingMark({ size = 24 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <circle cx="13" cy="19" r="10" style={{ fill: "rgb(var(--ink))" }} />
      <g className="animate-bob">
        <circle cx="23.5" cy="8.5" r="5.5" fill="#D6F546" strokeWidth="2" style={{ stroke: "rgb(var(--ink))" }} />
      </g>
    </svg>
  );
}
