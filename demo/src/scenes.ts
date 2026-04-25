// Each scene mirrors REAL linear-cli output. Verified against the binary.

export interface TermLine {
  text: string;
  color?: string;
  delay?: number;
  typing?: boolean;
  indent?: number;
  spinner?: boolean;
  badge?: { label: string; color: string }[];
}

export interface Scene {
  id: string;
  title: string;
  caption?: string;
  prompt?: string;
  lines: TermLine[];
  durationFrames: number;
  clear?: boolean;
}

const G = '#a3e635';
const W = '#e8e8e8';
const D = '#777777';
const Y = '#facc15';
const C = '#22d3ee';
const R = '#f87171';

export const SCENES: Scene[] = [
  {
    id: 'tasks',
    title: 'TASKS',
    caption: 'Your queue, in the active cycle.',
    lines: [
      { text: '$ linear tasks', color: W, typing: true, delay: 0 },
      { text: '', delay: 18 },
      { text: 'Q2W4 -- Conversion Optimization ($35K MRR) -- 50 task(s)  (2 yours, 48 unowned)', color: D, delay: 22 },
      { text: '', delay: 30 },
      { text: '  ANT-505 Urgent  Todo  --  you   Email truncated before .com -- preserve domain        [Bug]', color: W, delay: 34 },
      { text: '  ANT-507 High    Todo  --  you   Delegate tool title uses slug instead of display     [Bug]', color: W, delay: 42 },
      { text: '  ANT-508 Medium  Todo  --  --    Remove "MCP" from search placeholders                 [Improvement]', color: D, delay: 50 },
      { text: '  ANT-509 Medium  Todo  --  --    Agent preferences select component styling broken     [Bug]', color: D, delay: 58 },
      { text: '  ANT-510 Low     Todo  --  --    Session activity count may not match displayed        [Bug]', color: D, delay: 66 },
    ],
    durationFrames: 140,
  },
  {
    id: 'claim',
    title: 'CLAIM',
    caption: 'Pick it up.',
    clear: true,
    lines: [
      { text: '$ linear update ANT-505 --pickup', color: W, typing: true, delay: 0 },
      { text: '', delay: 24 },
      { text: 'ANT-505 -> In Progress', color: G, delay: 30 },
    ],
    durationFrames: 80,
  },
  {
    id: 'ship',
    title: 'SHIP',
    caption: 'Close with proof in one call.',
    clear: true,
    lines: [
      { text: '$ linear update ANT-505 --done \\', color: W, typing: true, delay: 0 },
      { text: '    --proof https://github.com/phnx-labs/agents/pull/47 \\', color: W, typing: true, delay: 22 },
      { text: '    --proof "Shipped in 0.8.79"', color: W, typing: true, delay: 50 },
      { text: '', delay: 70 },
      { text: 'Proof posted to ANT-505.', color: G, delay: 76 },
      { text: 'ANT-505 -> Done', color: G, delay: 92 },
    ],
    durationFrames: 130,
  },
  {
    id: 'finale',
    title: 'linear-cli',
    clear: true,
    lines: [],
    durationFrames: 170,
  },
];

export const TOTAL_FRAMES = SCENES.reduce((sum, s) => sum + s.durationFrames, 0);
