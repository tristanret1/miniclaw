import { Graphics } from "pixi.js";
import { SCALED_TILE } from "@/config";

const PX = SCALED_TILE / 16;

/**
 * Draw an oak tree (broad, layered canopy).
 * Extracted from TownScene.drawGround() tree rendering.
 * x, y are pixel positions of the top-left of the tree's bounding area.
 */
export function drawOakTree(g: Graphics, x: number, y: number): void {
  // Trunk
  g.rect(x + PX * 5, y + PX * 6, PX * 6, PX * 10);
  g.fill(0x8b4513);
  g.rect(x + PX * 5, y + PX * 6, PX * 6, PX * 10);
  g.stroke({ width: 1, color: 0x654321 });
  // Canopy — layered circles for fullness
  const canopyColor = 0x2e8b2e;
  const canopyLight = 0x32cd32;
  g.circle(x + PX * 8, y + PX * 2, PX * 8);
  g.fill(canopyColor);
  g.circle(x + PX * 4, y + PX * 5, PX * 6);
  g.fill(canopyColor);
  g.circle(x + PX * 12, y + PX * 5, PX * 6);
  g.fill(canopyColor);
  g.circle(x + PX * 8, y, PX * 6);
  g.fill(canopyLight);
  // Highlight
  g.circle(x + PX * 6, y - PX * 1, PX * 2);
  g.fill({ color: 0x90ee90, alpha: 0.4 });
}

/**
 * Draw a pine tree (triangular/conical shape).
 * New decoration type for the editor — triangular evergreen.
 * x, y are pixel positions of the top-left of the bounding area.
 */
export function drawPineTree(g: Graphics, x: number, y: number): void {
  // Trunk
  g.rect(x + PX * 6, y + PX * 12, PX * 4, PX * 6);
  g.fill(0x8b4513);
  g.rect(x + PX * 6, y + PX * 12, PX * 4, PX * 6);
  g.stroke({ width: 1, color: 0x654321 });
  // Canopy layers (three triangles, bottom to top)
  const pineGreen = 0x1a6b1a;
  const pineLight = 0x228b22;
  // Bottom layer
  g.moveTo(x + PX * 1, y + PX * 13);
  g.lineTo(x + PX * 8, y + PX * 5);
  g.lineTo(x + PX * 15, y + PX * 13);
  g.closePath();
  g.fill(pineGreen);
  // Middle layer
  g.moveTo(x + PX * 2, y + PX * 9);
  g.lineTo(x + PX * 8, y + PX * 2);
  g.lineTo(x + PX * 14, y + PX * 9);
  g.closePath();
  g.fill(pineLight);
  // Top layer
  g.moveTo(x + PX * 3, y + PX * 5);
  g.lineTo(x + PX * 8, y - PX * 1);
  g.lineTo(x + PX * 13, y + PX * 5);
  g.closePath();
  g.fill(pineGreen);
  // Snow highlight on top
  g.circle(x + PX * 7, y + PX * 1, PX * 1.5);
  g.fill({ color: 0x90ee90, alpha: 0.3 });
}

/**
 * Draw a bush — multi-circle shrub with optional berries.
 * Extracted from TownScene.drawGround() bush rendering.
 * x, y are pixel positions (center-ish of the bush).
 */
export function drawBush(g: Graphics, x: number, y: number): void {
  g.circle(x, y, PX * 5);
  g.fill(0x2e8b2e);
  g.circle(x + PX * 4, y + PX, PX * 4);
  g.fill(0x228b22);
  g.circle(x - PX * 2, y + PX * 2, PX * 3);
  g.fill(0x32cd32);
  // Berry dots
  g.circle(x + PX, y - PX * 2, PX);
  g.fill(0xff4444);
  g.circle(x + PX * 3, y, PX);
  g.fill(0xff4444);
}

/** Available wildflower color variants. */
const FLOWER_COLORS = [0xff6b6b, 0xffb347, 0xff69b4, 0x9370db, 0xffd700, 0xff4500];

/**
 * Draw a wildflower — stem + petals + center.
 * Extracted from TownScene.drawGround() wildflower rendering.
 * x, y are pixel positions of the flower base (bottom of stem).
 * variant selects the petal color (index into FLOWER_COLORS, wraps around).
 */
export function drawFlower(g: Graphics, x: number, y: number, variant = 0): void {
  // Stem
  g.moveTo(x, y);
  g.lineTo(x, y - PX * 4);
  g.stroke({ width: 1, color: 0x228b22 });
  // Petals
  const fc = FLOWER_COLORS[Math.abs(variant) % FLOWER_COLORS.length];
  g.circle(x, y - PX * 4, PX * 2);
  g.fill(fc);
  // Center
  g.circle(x, y - PX * 4, PX * 1);
  g.fill(0xffd700);
}

/**
 * Draw a rock — ellipse with highlight.
 * Extracted from TownScene.drawGround() rock rendering.
 * x, y are pixel positions of the rock center.
 */
export function drawRock(g: Graphics, x: number, y: number): void {
  g.ellipse(x, y, PX * 4, PX * 3);
  g.fill(0x808080);
  g.ellipse(x, y, PX * 4, PX * 3);
  g.stroke({ width: 1, color: 0x606060 });
  // Highlight
  g.ellipse(x - PX, y - PX, PX * 1.5, PX * 1);
  g.fill({ color: 0xaaaaaa, alpha: 0.4 });
}

/**
 * Draw a horizontal fence segment.
 * Extracted from TownScene.drawGround() fence rendering.
 * x, y are pixel positions of the top-left of the fence segment.
 * Draws one SCALED_TILE-wide section with two posts and two rails.
 */
export function drawFenceH(g: Graphics, x: number, y: number): void {
  // Posts
  g.rect(x + PX * 2, y, PX * 2, PX * 8);
  g.fill(0xdeb887);
  g.rect(x + PX * 12, y, PX * 2, PX * 8);
  g.fill(0xdeb887);
  // Rails
  g.rect(x + PX * 2, y + PX * 2, PX * 12, PX * 2);
  g.fill(0xdeb887);
  g.rect(x + PX * 2, y + PX * 5, PX * 12, PX * 2);
  g.fill(0xdeb887);
}

/**
 * Draw a vertical fence segment.
 * Mirror of horizontal fence, rotated for vertical orientation.
 * x, y are pixel positions of the top-left of the fence segment.
 */
export function drawFenceV(g: Graphics, x: number, y: number): void {
  // Posts
  g.rect(x, y + PX * 2, PX * 8, PX * 2);
  g.fill(0xdeb887);
  g.rect(x, y + PX * 12, PX * 8, PX * 2);
  g.fill(0xdeb887);
  // Rails
  g.rect(x + PX * 2, y + PX * 2, PX * 2, PX * 12);
  g.fill(0xdeb887);
  g.rect(x + PX * 5, y + PX * 2, PX * 2, PX * 12);
  g.fill(0xdeb887);
}

/**
 * Draw a mushroom (red cap with white spots).
 * Extracted from TownScene.drawGround() mushroom rendering.
 * x, y are pixel positions of the mushroom center-top area.
 */
export function drawMushroom(g: Graphics, x: number, y: number): void {
  // Stem
  g.rect(x - PX, y, PX * 3, PX * 4);
  g.fill(0xf5deb3);
  // Cap
  g.ellipse(x + PX * 0.5, y, PX * 4, PX * 3);
  g.fill(0xcc3333);
  // Spots
  g.circle(x - PX, y - PX, PX * 0.8);
  g.fill(0xffffff);
  g.circle(x + PX * 2, y - PX * 1.5, PX * 0.6);
  g.fill(0xffffff);
}

/**
 * Draw a bench (wooden seat with back and legs).
 * Extracted from Building.drawBench() (used in plaza).
 * x, y are pixel positions of the top-left of the bench.
 */
export function drawBench(g: Graphics, x: number, y: number): void {
  // Back
  g.rect(x, y, PX * 16, PX * 3);
  g.fill(0x8b4513);
  g.rect(x, y, PX * 16, PX * 3);
  g.stroke({ width: 1, color: 0x654321 });
  // Seat
  g.rect(x, y + PX * 2, PX * 16, PX * 4);
  g.fill(0x8b4513);
  g.rect(x, y + PX * 2, PX * 16, PX * 4);
  g.stroke({ width: 1, color: 0x654321 });
  // Legs
  g.rect(x + PX, y + PX * 6, PX * 2, PX * 4);
  g.fill(0x654321);
  g.rect(x + PX * 13, y + PX * 6, PX * 2, PX * 4);
  g.fill(0x654321);
}

/** Catalog entry describing a placeable decoration. */
export interface DecorationCatalogEntry {
  type: string;
  name: string;
  draw: (g: Graphics, x: number, y: number, variant?: number) => void;
  /** Width in tiles that this decoration occupies. */
  widthTiles: number;
  /** Height in tiles that this decoration occupies. */
  heightTiles: number;
}

/** Registry of all available decoration types for the resource editor. */
export const DECORATION_CATALOG: DecorationCatalogEntry[] = [
  { type: "oak_tree", name: "Oak Tree", draw: drawOakTree, widthTiles: 1, heightTiles: 1 },
  { type: "pine_tree", name: "Pine Tree", draw: drawPineTree, widthTiles: 1, heightTiles: 1 },
  { type: "bush", name: "Bush", draw: drawBush, widthTiles: 1, heightTiles: 1 },
  { type: "flower", name: "Wildflower", draw: drawFlower, widthTiles: 1, heightTiles: 1 },
  { type: "rock", name: "Rock", draw: drawRock, widthTiles: 1, heightTiles: 1 },
  { type: "fence_h", name: "Fence (Horizontal)", draw: drawFenceH, widthTiles: 1, heightTiles: 1 },
  { type: "fence_v", name: "Fence (Vertical)", draw: drawFenceV, widthTiles: 1, heightTiles: 1 },
  { type: "mushroom", name: "Mushroom", draw: drawMushroom, widthTiles: 1, heightTiles: 1 },
  { type: "bench", name: "Bench", draw: drawBench, widthTiles: 1, heightTiles: 1 },
];
