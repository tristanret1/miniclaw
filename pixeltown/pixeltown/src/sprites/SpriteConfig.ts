/**
 * Sprite configuration — maps agent IDs to spritesheets and animation frames.
 *
 * To add a new sprite:
 * 1. Place the spritesheet PNG in public/sprites/
 * 2. Add a SpriteSheet entry below with frame size, count, and animation mapping
 * 3. Assign it to an agent ID in AGENT_SPRITES
 */

export interface AnimFrames {
  walk_down: number[];
  walk_up: number[];
  walk_right: number[];
  walk_left: number[];
  idle_down: number[];
  idle_up: number[];
  idle_right: number[];
  idle_left: number[];
}

export interface SpriteSheet {
  /** Path relative to public/ (served as static asset) */
  path: string;
  /** Width & height of each frame in pixels */
  frameSize: number;
  /** Total number of frames in the sheet */
  frameCount: number;
  /** Animation frame indices */
  anims: AnimFrames;
  /** Animation speed in ms per frame */
  animSpeed?: number;
}

// ── Shared animation layout (all generated sheets use the same frame indices) ──

const STANDARD_ANIMS: AnimFrames = {
  walk_down:  [0, 1, 2],
  walk_up:    [9, 10, 11],
  walk_right: [12, 13, 14],
  walk_left:  [18, 19, 17],
  idle_down:  [35],
  idle_up:    [37],
  idle_right: [34],
  idle_left:  [36],
};

function sheet(name: string, anims = STANDARD_ANIMS): SpriteSheet {
  return { path: `/sprites/${name}Sprite.png`, frameSize: 32, frameCount: 39, anims };
}

// ── Spritesheet definitions ──

export const SHEETS: Record<string, SpriteSheet> = {
  noob:      sheet("Noob"),
  mage:      sheet("Mage"),
  knight:    sheet("Knight"),
  ranger:    sheet("Ranger"),
  scholar:   sheet("Scholar"),
  merchant:  sheet("Merchant"),
  witch:     sheet("Witch"),
  farmer:    sheet("Farmer"),
  pirate:    sheet("Pirate"),
  priestess: sheet("Priestess"),
  fairy:     sheet("Fairy"),
  archer:    sheet("Archer"),
};

/** Default spritesheet used when agent has no specific mapping. */
export const DEFAULT_SHEET = "noob";

/**
 * Agent ID → spritesheet key mapping.
 * Agents not listed here use DEFAULT_SHEET.
 */
export const AGENT_SPRITES: Record<string, string> = {
  peter: "mage",
  Kokiri: "priestess",
};

/** Resolve which SpriteSheet config to use for a given agent ID. */
export function getSheetForAgent(agentId: string): SpriteSheet {
  const key = AGENT_SPRITES[agentId] ?? DEFAULT_SHEET;
  return SHEETS[key] ?? SHEETS[DEFAULT_SHEET];
}

/**
 * Apply editor-exported character config at runtime.
 * Call this after loadEditorConfig() resolves.
 */
export function applyCharacterConfig(config: { agents: Record<string, { sheet: string }>; defaultSheet: string }): void {
  // Merge agent-sprite mappings
  for (const [agentId, entry] of Object.entries(config.agents)) {
    if (entry.sheet && SHEETS[entry.sheet]) {
      AGENT_SPRITES[agentId] = entry.sheet;
    }
  }
  console.log("[SpriteConfig] Applied character config:", Object.keys(config.agents));
}
