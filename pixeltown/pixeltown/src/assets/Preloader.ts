import { Assets } from "pixi.js";
import { SHEETS, type SpriteSheet } from "@/sprites/SpriteConfig";
import { preloadAll } from "@/sprites/SpriteLoader";

/**
 * Preload core assets (spritesheets) so first frame is smooth and avoid hitches.
 */
export async function preloadCoreAssets(): Promise<void> {
  // Register base URL for assets if needed (vite serves from public/ at root)
  // Assets.init({ manifest: { bundles: [] } });

  const sheets: SpriteSheet[] = Object.values(SHEETS);
  await Promise.all([
    // Ensure PIXI Assets is initialized (no-op if already used)
    Assets.init(),
    preloadAll(sheets),
  ]);
}

