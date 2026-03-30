import { Graphics } from "pixi.js";
import type { TiledMap, TiledLayer } from "@/map/types";
import { SCALED_TILE } from "@/config";

/**
 * Render simple colored tiles from a Tiled map when no tileset textures are integrated yet.
 * This is a placeholder pipeline that enables collision layering and pre-rendering now.
 */
export function renderTiledToGraphics(map: TiledMap): { ground: Graphics; decorations: Graphics; waterGrid: number[][]; blockGrid: number[][] } {
  const ground = new Graphics();
  const decorations = new Graphics();

  const cols = map.width;
  const rows = map.height;
  const waterGrid = Array.from({ length: rows }, () => Array.from({ length: cols }, () => 0));
  const blockGrid = Array.from({ length: rows }, () => Array.from({ length: cols }, () => 0));

  const tileSize = SCALED_TILE; // assume 1:1 mapping
  const PX = tileSize / 16;

  const layerColor = (name: string, gid: number): number => {
    // Simple color palette per layer
    if (name.toLowerCase().includes("water")) return 0x3b82f6;
    if (name.toLowerCase().includes("path")) return 0xc9b99a;
    if (name.toLowerCase().includes("dirt")) return 0xb5651d;
    if (name.toLowerCase().includes("stone")) return 0x888888;
    if (name.toLowerCase().includes("sand")) return 0xf5deb3;
    // default grass variation
    const grass = [0x7ec850, 0x72b847, 0x85d155, 0x6aad3e, 0x7bc04d];
    return grass[gid % grass.length];
  };

  const drawLayer = (layer: TiledLayer) => {
    if (layer.type !== "tilelayer" || !layer.data) return;
    const name = layer.name.toLowerCase();
    for (let ty = 0; ty < layer.height; ty++) {
      for (let tx = 0; tx < layer.width; tx++) {
        const idx = ty * layer.width + tx;
        const gid = layer.data[idx] || 0;
        if (gid === 0) continue;
        const x = tx * tileSize;
        const y = ty * tileSize;
        const color = layerColor(name, gid);
        if (name.includes("decor")) {
          decorations.rect(x, y, tileSize, tileSize);
          decorations.fill(color);
        } else {
          ground.rect(x, y, tileSize, tileSize);
          ground.fill(color);
        }
        if (name.includes("water")) waterGrid[ty][tx] = 1;
        if (name.includes("block") || name.includes("collision")) blockGrid[ty][tx] = 1;
      }
    }
  };

  for (const layer of map.layers) drawLayer(layer);

  return { ground, decorations, waterGrid, blockGrid };
}

