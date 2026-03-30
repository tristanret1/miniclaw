import { Assets, Container, Sprite, Texture, Rectangle } from "pixi.js";
import type { TiledMap, TiledLayer, TiledTileset } from "@/map/types";
import { SCALED_TILE } from "@/config";

/** Bitmask for Tiled GID flip flags */
const FLIPPED_HORIZONTALLY_FLAG = 0x80000000;
const FLIPPED_VERTICALLY_FLAG = 0x40000000;
const FLIPPED_DIAGONALLY_FLAG = 0x20000000;
const GID_MASK = ~(FLIPPED_HORIZONTALLY_FLAG | FLIPPED_VERTICALLY_FLAG | FLIPPED_DIAGONALLY_FLAG);

interface TilesetTextures {
  tileset: TiledTileset;
  textures: Texture[];
}

async function buildTilesetTextures(ts: TiledTileset): Promise<TilesetTextures> {
  const baseTex = await Assets.load<Texture>(ts.image);
  const textures: Texture[] = [];
  for (let i = 0; i < ts.tilecount; i++) {
    const col = i % ts.columns;
    const row = Math.floor(i / ts.columns);
    const frame = new Rectangle(col * ts.tilewidth, row * ts.tileheight, ts.tilewidth, ts.tileheight);
    textures.push(new Texture({ source: baseTex.source, frame }));
  }
  return { tileset: ts, textures };
}

function findTilesetForGid(tilesets: TiledTileset[], rawGid: number): { ts: TiledTileset; localId: number } | null {
  const gid = rawGid & GID_MASK;
  if (gid === 0) return null;
  let chosen: TiledTileset | null = null;
  for (let i = 0; i < tilesets.length; i++) {
    const ts = tilesets[i];
    const nextFirst = tilesets[i + 1]?.firstgid ?? Number.MAX_SAFE_INTEGER;
    if (gid >= ts.firstgid && gid < nextFirst) {
      chosen = ts;
      break;
    }
  }
  if (!chosen) return null;
  return { ts: chosen, localId: gid - chosen.firstgid };
}

/**
 * Render Tiled map to sprite containers per层（地表、装饰），并导出水域/阻挡网格。
 */
export async function renderTiledToContainers(map: TiledMap): Promise<{ ground: Container; decorations: Container; waterGrid: number[][]; blockGrid: number[][] }> {
  const ground = new Container();
  const decorations = new Container();
  const cols = map.width;
  const rows = map.height;
  const waterGrid = Array.from({ length: rows }, () => Array.from({ length: cols }, () => 0));
  const blockGrid = Array.from({ length: rows }, () => Array.from({ length: cols }, () => 0));

  // Prepare tileset textures
  const tilesetTextures: TilesetTextures[] = [];
  for (const ts of map.tilesets) {
    tilesetTextures.push(await buildTilesetTextures(ts));
  }

  const pickTexture = (rawGid: number): { tex: Texture; flipH: boolean; flipV: boolean; flipD: boolean } | null => {
    const flipH = (rawGid & FLIPPED_HORIZONTALLY_FLAG) !== 0;
    const flipV = (rawGid & FLIPPED_VERTICALLY_FLAG) !== 0;
    const flipD = (rawGid & FLIPPED_DIAGONALLY_FLAG) !== 0;
    const found = findTilesetForGid(map.tilesets, rawGid);
    if (!found) return null;
    const pack = tilesetTextures.find((p) => p.tileset === found.ts)!;
    const tex = pack.textures[found.localId];
    if (!tex) return null;
    return { tex, flipH, flipV, flipD };
  };

  const drawLayer = (layer: TiledLayer) => {
    if (layer.type !== "tilelayer" || !layer.data) return;
    const name = layer.name.toLowerCase();
    for (let ty = 0; ty < layer.height; ty++) {
      for (let tx = 0; tx < layer.width; tx++) {
        const idx = ty * layer.width + tx;
        const rawGid = layer.data[idx] || 0;
        if (rawGid === 0) continue;
        const picked = pickTexture(rawGid);
        if (!picked) continue;
        const sprite = new Sprite(picked.tex);
        // Position and flipping
        sprite.x = tx * SCALED_TILE;
        sprite.y = ty * SCALED_TILE;
        // Scale sprite to SCALED_TILE if tileset tile size differs
        sprite.width = SCALED_TILE;
        sprite.height = SCALED_TILE;
        if (picked.flipH) sprite.scale.x *= -1, sprite.x += SCALED_TILE;
        if (picked.flipV) sprite.scale.y *= -1, sprite.y += SCALED_TILE;
        // Diagonal flip（Tiled 特殊处理）：简化先忽略，后续如需支持可用矩阵变换

        if (name.includes("decor")) decorations.addChild(sprite);
        else ground.addChild(sprite);
        if (name.includes("water")) waterGrid[ty][tx] = 1;
        if (name.includes("block") || name.includes("collision")) blockGrid[ty][tx] = 1;
      }
    }
  };

  for (const layer of map.layers) drawLayer(layer);
  return { ground, decorations, waterGrid, blockGrid };
}
