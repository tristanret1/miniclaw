import { TiledMap } from "@/map/types";

/** Attempt to load a Tiled map JSON from /maps/tiled.json. Returns null if not found.
 * Be lenient: support JSON with // and block comments by stripping before parse. */
export async function loadTiledMap(): Promise<TiledMap | null> {
  try {
    const resp = await fetch("/maps/tiled.json", { cache: "no-cache" });
    if (!resp.ok) return null;
    const raw = await resp.text();
    // Strip block comments and line comments
    const noBlock = raw.replace(/\/\*[\s\S]*?\*\//g, "");
    const noLine = noBlock.replace(/(^|\s)\/\/.*$/gm, "");
    const json = JSON.parse(noLine) as TiledMap;
    return json;
  } catch (e) {
    console.warn("[TilemapLoader] Failed to load/parse tiled.json:", e);
    return null;
  }
}
