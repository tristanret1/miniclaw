/**
 * ConfigLoader — loads editor-exported pixeltown-config.json at runtime.
 *
 * Usage:
 *   1. Export config from editor (Save button → pixeltown-config.json)
 *   2. Place it in public/pixeltown-config.json
 *   3. Game auto-loads it on startup; falls back to hardcoded defaults if absent
 *
 * Import { getEditorConfig } in TownScene/HouseScene/SpriteConfig to consume.
 */

import type { EditorConfig, TownMapConfig, InteriorConfig, CharacterConfig } from "./editor/types";

let loaded: EditorConfig | null = null;
let attempted = false;

/** Fetch and cache the editor config. Returns null if not found. */
export async function loadEditorConfig(): Promise<EditorConfig | null> {
  if (attempted) return loaded;
  attempted = true;
  try {
    const resp = await fetch("/pixeltown-config.json");
    if (!resp.ok) return null;
    loaded = (await resp.json()) as EditorConfig;
    console.log("[ConfigLoader] Loaded pixeltown-config.json");
    return loaded;
  } catch {
    return null;
  }
}

/** Get the cached config (call loadEditorConfig first). */
export function getEditorConfig(): EditorConfig | null {
  return loaded;
}

export function getTownMapConfig(): TownMapConfig | null {
  return loaded?.townMap ?? null;
}

export function getInteriorConfig(): InteriorConfig | null {
  return loaded?.interior ?? null;
}

export function getCharacterConfig(): CharacterConfig | null {
  return loaded?.characters ?? null;
}
