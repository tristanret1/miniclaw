import { TiledMap } from "@/map/types";

/** Attempt to load a Tiled map JSON from /maps/tiled.json. Returns null if not found. */
export async function loadTiledMap(): Promise<TiledMap | null> {
  try {
    const resp = await fetch("/maps/tiled.json", { cache: "no-cache" });
    if (!resp.ok) return null;
    const json = (await resp.json()) as TiledMap;
    return json;
  } catch {
    return null;
  }
}

