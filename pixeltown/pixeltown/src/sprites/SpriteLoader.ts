/**
 * Sprite texture loader — loads and caches spritesheet frame textures.
 * Each unique spritesheet path is loaded once and shared across agents.
 */

import { Assets, Texture, Rectangle } from "pixi.js";
import type { SpriteSheet } from "./SpriteConfig";

interface CachedSheet {
  textures: Texture[];
  ready: boolean;
  promise: Promise<void>;
}

const cache = new Map<string, CachedSheet>();

/** Load a spritesheet and return its frame textures. */
export function loadSheet(sheet: SpriteSheet): CachedSheet {
  const existing = cache.get(sheet.path);
  if (existing) return existing;

  const textures: Texture[] = [];
  let ready = false;

  const promise = (async () => {
    const source = await Assets.load<Texture>(sheet.path);
    const baseSource = source.source;

    for (let i = 0; i < sheet.frameCount; i++) {
      const frame = new Rectangle(
        i * sheet.frameSize,
        0,
        sheet.frameSize,
        sheet.frameSize,
      );
      textures.push(new Texture({ source: baseSource, frame }));
    }
    ready = true;
  })();

  const entry: CachedSheet = { textures, get ready() { return ready; }, set ready(v) { ready = v; }, promise };
  cache.set(sheet.path, entry);
  return entry;
}

/** Preload all registered sheets. */
export function preloadAll(sheets: SpriteSheet[]): Promise<void[]> {
  return Promise.all(sheets.map((s) => loadSheet(s).promise));
}
