// Guidance text. Both editions share the ergonomics; the company-specific lines come from org.js (one per edition).
import { EDITION, ASSISTANT } from './logo.js';
import * as O from './org.js';

const MK = false;   // company editions (not in the public source) change the look; wording lives in org.js

export const ORG = O.ORG;
export const SOURCE = O.SOURCE;

export const COMMITMENT = `A comfortable, well-adjusted workstation supports your long-term wellbeing, reduces fatigue and helps you do your best work — ${O.WHERE}.`;

export const ESSENTIALS = [
  { id: 'light', page: 'light', title: 'Good light', text: 'At least 500 lux at your desk, with no glare.', color: 'var(--c-light)' },
  { id: 'move', page: 'move', title: 'Keep moving', text: 'Alternate between sitting and standing.', color: 'var(--c-move)' },
  { id: 'posture', page: 'posture', title: 'Neutral posture', text: 'Screen at eye level, elbows at about 90°.', color: 'var(--c-posture)' },
  { id: 'eyes', page: 'eyes', title: 'Rest your eyes', text: 'Follow the 20-20-20 rule.', color: 'var(--c-eyes)' },
];

export const CHECKLIST = [
  { id: 'light', icon: 'light', title: 'Light', text: 'At least 500 lux at my desk, no glare', page: 'light' },
  { id: 'chair', icon: 'chair', title: 'Chair', text: 'Feet flat and lower back supported', page: 'posture' },
  { id: 'desk', icon: 'desk', title: 'Desk', text: 'I alternate between sitting and standing', page: 'move' },
  { id: 'screen', icon: 'eye', title: 'Screen', text: 'Arm’s length away, top at or below eye level', page: 'posture' },
  { id: 'arms', icon: 'posture', title: 'Arms', text: 'Elbows at about 90°, wrists straight', page: 'posture' },
  { id: 'reach', icon: 'reach', title: 'Reach', text: 'Keyboard, mouse and key items close by', page: 'workspace' },
  { id: 'breaks', icon: 'bell', title: 'Breaks', text: 'I follow the 20-20-20 rule and stretch', page: 'eyes' },
  { id: 'cables', icon: 'cable', title: 'Cables', text: O.CABLES_SHORT, page: 'workspace' },
];

export const CABLES = O.CABLES;
export const HELP = O.HELP;
export const LOCAL_RULES = O.LOCAL_RULES;

// The lux meter is a model, not a measurement.
export const LUX_NOTE = 'This result is orientational only — it is based on a mathematical calculation, not a measurement. ' +
  'To measure the light at your desk, a calibrated light meter must be used.' + O.MEASURE_SENTENCE;

// Where each recommendation comes from (shown under Settings → About). Postura is general guidance, not a legal
// assessment; the user's own workplace rules and risk assessment come first.
export const SOURCES = [
  { what: 'Breaks and changes of activity during screen work; information about the workstation',
    src: 'EU Council Directive 90/270/EEC on work with display screen equipment (minimum requirements)' },
  { what: 'Screen work in Denmark',
    src: 'Danish Working Environment Authority (Arbejdstilsynet) — rules and guidance on screen work (at.dk)' },
  { what: '500 lux at the desk, glare control',
    src: 'EN 12464-1 Light and lighting — Lighting of work places (offices: writing, typing, reading, data processing)' },
  { what: '20-20-20 eye breaks',
    src: 'American Academy of Ophthalmology — a rule of thumb for eye strain, not a legal requirement' },
  { what: 'Screen height and distance, elbows about 90°, feet supported, sit-stand variety',
    src: 'Common office-ergonomics guidance, e.g. ISO 9241-5 (workstation layout and postural requirements) and EU-OSHA material on office work' },
  ...O.EXTRA_SOURCES,
];

export const TAGLINE = 'Sit well. Rest your eyes. Keep moving.';
export { ASSISTANT, MK };
export const {
  EDITION_LABEL, AI_FOR, GUIDE_NAME, SEEK_HELP, MEASURE_DASH, MEASURE_SENTENCE, MEASURE_PAREN, ABOUT_HTML,
  SETUP_SUB, SETUP_LIC,
} = O;
