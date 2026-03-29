import { Graphics } from "pixi.js";
import { SCALED_TILE } from "@/config";

const T = SCALED_TILE;
const PX = T / 16;

/**
 * Theme palette for furniture rendering — matches HouseScene.getTheme().
 * Furniture renderers that accept a theme parameter use these fields.
 */
export interface FurnitureTheme {
  wall: number;
  wainscot: number;
  floorA: number;
  floorB: number;
  rug: number;
  rugAccent: number;
  blanket: number;
  blanketDark: number;
  sofa: number;
  sofaFrame: number;
  pillow: number;
  painting: number;
  paintingMtn: number;
  bedroomRug: number;
}

/** Default warm/classic theme — same as HouseScene themes[0]. */
export const DEFAULT_THEME: FurnitureTheme = {
  wall: 0xd4c5a9,
  wainscot: 0xc4b599,
  floorA: 0x9b7b55,
  floorB: 0x8b6b45,
  rug: 0x8b2252,
  rugAccent: 0xdaa520,
  blanket: 0x4169e1,
  blanketDark: 0x2c4ba0,
  sofa: 0xc0392b,
  sofaFrame: 0x6b3a2a,
  pillow: 0xe8c840,
  painting: 0x87ceeb,
  paintingMtn: 0x4a7a4a,
  bedroomRug: 0x9370db,
};

/**
 * Draw a sofa (side view, back on left side).
 * Extracted from HouseScene.drawLivingRoom().
 * x, y are pixel positions of the top-left corner.
 */
export function drawSofa(
  g: Graphics,
  x: number,
  y: number,
  theme: FurnitureTheme = DEFAULT_THEME,
): void {
  const sofaW = T * 1.2;
  const sofaH = T * 3;
  // Back
  g.rect(x, y, PX * 8, sofaH);
  g.fill(theme.sofaFrame);
  // Cushions
  g.roundRect(x + PX * 8, y + PX * 2, sofaW - PX * 8, sofaH / 2 - PX * 2, PX * 3);
  g.fill(theme.sofa);
  g.roundRect(x + PX * 8, y + sofaH / 2 + PX, sofaW - PX * 8, sofaH / 2 - PX * 3, PX * 3);
  g.fill(theme.sofa);
  // Arm rests
  g.roundRect(x, y - PX * 3, sofaW, PX * 5, PX * 2);
  g.fill(theme.sofaFrame);
  g.roundRect(x, y + sofaH - PX * 2, sofaW, PX * 5, PX * 2);
  g.fill(theme.sofaFrame);
  // Throw pillow
  g.roundRect(x + PX * 10, y + PX * 6, PX * 10, PX * 10, PX * 3);
  g.fill(theme.pillow);
}

/**
 * Draw a bed (top-down view with headboard, mattress, blanket, pillows).
 * Extracted from HouseScene.drawBedroom().
 * x, y are pixel positions of the top-left corner.
 */
export function drawBed(
  g: Graphics,
  x: number,
  y: number,
  theme: FurnitureTheme = DEFAULT_THEME,
): void {
  const bedW = T * 2;
  const bedH = T * 3.5;
  // Frame
  g.roundRect(x, y, bedW, bedH, PX * 2);
  g.fill(0x8b6914);
  g.roundRect(x, y, bedW, bedH, PX * 2);
  g.stroke({ width: 2, color: 0x654321 });
  // Headboard
  g.roundRect(x, y, bedW, PX * 8, PX * 3);
  g.fill(0x654321);
  // Mattress
  g.rect(x + PX * 3, y + PX * 10, bedW - PX * 6, bedH - PX * 14);
  g.fill(0xfaf0e6);
  // Blanket
  const mattressH = bedH - PX * 14;
  g.rect(x + PX * 3, y + PX * 10 + mattressH * 0.4, bedW - PX * 6, mattressH * 0.6);
  g.fill(theme.blanket);
  g.rect(x + PX * 3, y + PX * 10 + mattressH * 0.4, bedW - PX * 6, mattressH * 0.6);
  g.stroke({ width: 1, color: theme.blanketDark });
  // Blanket fold
  g.moveTo(x + PX * 3, y + PX * 10 + mattressH * 0.4 + PX * 2);
  g.lineTo(x + bedW - PX * 3, y + PX * 10 + mattressH * 0.4 + PX * 2);
  g.stroke({ width: 1, color: 0xffffff, alpha: 0.3 });
  // Pillows
  g.roundRect(x + PX * 5, y + PX * 12, PX * 12, PX * 8, PX * 3);
  g.fill(0xffffff);
  g.roundRect(x + PX * 5, y + PX * 12, PX * 12, PX * 8, PX * 3);
  g.stroke({ width: 1, color: 0xe0e0e0 });
  g.roundRect(x + PX * 20, y + PX * 12, PX * 12, PX * 8, PX * 3);
  g.fill(0xffffff);
  g.roundRect(x + PX * 20, y + PX * 12, PX * 12, PX * 8, PX * 3);
  g.stroke({ width: 1, color: 0xe0e0e0 });
}

/**
 * Draw a desk with monitor, keyboard, and legs.
 * Extracted from HouseScene.drawBedroom().
 * x, y are pixel positions of the top-left of the desk surface.
 */
export function drawDesk(
  g: Graphics,
  x: number,
  y: number,
  _theme: FurnitureTheme = DEFAULT_THEME,
): void {
  const dkW = T * 2.5;
  const dkH = T * 1.2;
  // Desk surface
  g.rect(x, y, dkW, dkH);
  g.fill(0xa0522d);
  g.rect(x, y, dkW, dkH);
  g.stroke({ width: 2, color: 0x5c3a1e });
  // Desk legs
  g.rect(x + PX * 2, y + dkH, PX * 3, T * 0.6);
  g.fill(0x8b4513);
  g.rect(x + dkW - PX * 5, y + dkH, PX * 3, T * 0.6);
  g.fill(0x8b4513);
  // Monitor
  g.rect(x + PX * 8, y - T * 0.8, T * 1.4, T * 0.8);
  g.fill(0x333333);
  g.rect(x + PX * 8, y - T * 0.8, T * 1.4, T * 0.8);
  g.stroke({ width: 2, color: 0x222222 });
  // Screen
  g.rect(x + PX * 10, y - T * 0.8 + PX * 2, T * 1.4 - PX * 4, T * 0.8 - PX * 6);
  g.fill(0x2a4a6a);
  // Monitor stand
  g.rect(x + T * 0.6, y - PX * 2, PX * 8, PX * 4);
  g.fill(0x444444);
  // Keyboard
  g.roundRect(x + PX * 6, y + PX * 3, T * 1, PX * 6, PX);
  g.fill(0xd0d0d0);
  g.roundRect(x + PX * 6, y + PX * 3, T * 1, PX * 6, PX);
  g.stroke({ width: 1, color: 0xaaaaaa });
}

/**
 * Draw a bookshelf (with three shelves of colorful books).
 * Extracted from HouseScene.drawLivingRoom().
 * x, y are pixel positions of the top-left corner.
 */
export function drawBookshelf(g: Graphics, x: number, y: number): void {
  const bsW = T * 2;
  const bsH = T * 2;
  // Frame
  g.rect(x, y, bsW, bsH);
  g.fill(0x654321);
  g.rect(x, y, bsW, bsH);
  g.stroke({ width: 2, color: 0x4a3018 });
  // Shelves
  for (let s = 0; s < 3; s++) {
    const sy = y + (s + 1) * (bsH / 3);
    g.rect(x, sy - PX * 2, bsW, PX * 2);
    g.fill(0x7a5a38);
  }
  // Books
  const bookColors = [0xcc3333, 0x3366cc, 0x339933, 0xcc9933, 0x9933cc, 0xcc6633, 0x3399cc, 0xcc3366];
  for (let s = 0; s < 3; s++) {
    const sy = y + s * (bsH / 3) + PX * 2;
    for (let b = 0; b < 5; b++) {
      const bx = x + PX * 3 + b * PX * 6;
      const bh = PX * 8 + (b % 3) * PX;
      g.rect(bx, sy + (bsH / 3 - PX * 4 - bh), PX * 4, bh);
      g.fill(bookColors[(s * 5 + b) % bookColors.length]);
    }
  }
}

/**
 * Draw a coffee table with cup, saucer, and book.
 * Extracted from HouseScene.drawLivingRoom().
 * x, y are pixel positions of the top-left corner.
 */
export function drawCoffeeTable(g: Graphics, x: number, y: number): void {
  const ctW = T * 2;
  const ctH = T * 1.2;
  // Table surface
  g.roundRect(x, y, ctW, ctH, PX * 2);
  g.fill(0xa0522d);
  g.roundRect(x, y, ctW, ctH, PX * 2);
  g.stroke({ width: 2, color: 0x5c3a1e });
  // Cup on table
  g.rect(x + PX * 6, y + PX * 4, PX * 6, PX * 8);
  g.fill(0xffffff);
  g.rect(x + PX * 6, y + PX * 4, PX * 6, PX * 8);
  g.stroke({ width: 1, color: 0xcccccc });
  // Saucer
  g.ellipse(x + PX * 9, y + PX * 13, PX * 5, PX * 2);
  g.fill(0xffffff);
  // Book on table
  g.rect(x + T + PX * 4, y + PX * 3, PX * 14, PX * 10);
  g.fill(0x2e4057);
  g.rect(x + T + PX * 4, y + PX * 3, PX * 14, PX * 10);
  g.stroke({ width: 1, color: 0x1a2a3a });
}

/**
 * Draw a wardrobe (double-door armoire with handles).
 * Extracted from HouseScene.drawBedroom().
 * x, y are pixel positions of the top-left corner.
 */
export function drawWardrobe(g: Graphics, x: number, y: number): void {
  const wdW = T * 1.8;
  const wdH = T * 2;
  // Body
  g.rect(x, y, wdW, wdH);
  g.fill(0x8b6914);
  g.rect(x, y, wdW, wdH);
  g.stroke({ width: 2, color: 0x654321 });
  // Double doors
  g.moveTo(x + wdW / 2, y + PX * 2);
  g.lineTo(x + wdW / 2, y + wdH - PX * 2);
  g.stroke({ width: 2, color: 0x654321 });
  // Handles
  g.circle(x + wdW / 2 - PX * 3, y + wdH / 2, PX * 1.5);
  g.fill(0xdaa520);
  g.circle(x + wdW / 2 + PX * 3, y + wdH / 2, PX * 1.5);
  g.fill(0xdaa520);
}

/**
 * Draw a nightstand with drawer, knob, and lamp.
 * Extracted from HouseScene.drawBedroom().
 * x, y are pixel positions of the top-left corner.
 */
export function drawNightstand(g: Graphics, x: number, y: number): void {
  const nsW = T * 0.7;
  const nsH = T * 1;
  // Body
  g.rect(x, y, nsW, nsH);
  g.fill(0x8b6914);
  g.rect(x, y, nsW, nsH);
  g.stroke({ width: 1, color: 0x654321 });
  // Drawer
  g.rect(x + PX * 2, y + T * 0.5, nsW - PX * 4, PX * 6);
  g.stroke({ width: 1, color: 0x654321 });
  // Knob
  g.circle(x + T * 0.35, y + T * 0.5 + PX * 3, PX);
  g.fill(0xdaa520);
  // Lamp stem
  g.rect(x + PX * 6, y - PX * 10, PX * 3, PX * 10);
  g.fill(0x808080);
  // Lampshade
  g.moveTo(x + PX * 2, y - PX * 10);
  g.lineTo(x + PX * 7, y - PX * 18);
  g.lineTo(x + PX * 12, y - PX * 10);
  g.closePath();
  g.fill(0xfff8dc);
  g.moveTo(x + PX * 2, y - PX * 10);
  g.lineTo(x + PX * 7, y - PX * 18);
  g.lineTo(x + PX * 12, y - PX * 10);
  g.closePath();
  g.stroke({ width: 1, color: 0xdaa520 });
}

/**
 * Draw a fireplace with mantel, firebox, flames, and logs.
 * Extracted from HouseScene.drawLivingRoom().
 * x, y are pixel positions of the top-left of the mantel area.
 */
export function drawFireplace(g: Graphics, x: number, y: number): void {
  const fpW = T * 1.5;
  const fpH = T * 2;
  // Mantel
  g.rect(x, y - PX * 4, fpW, PX * 4);
  g.fill(0x808080);
  // Firebox interior
  g.rect(x + PX * 4, y, fpW - PX * 8, T * 1.8);
  g.fill(0x333333);
  // Brick outline
  g.rect(x, y, fpW, fpH);
  g.stroke({ width: 2, color: 0x808080 });
  // Fire glow
  g.circle(x + fpW / 2, y + T * 1.2, PX * 6);
  g.fill({ color: 0xff6600, alpha: 0.6 });
  g.circle(x + fpW / 2 - PX * 2, y + T, PX * 4);
  g.fill({ color: 0xffcc00, alpha: 0.5 });
  // Logs
  g.roundRect(x + PX * 8, y + T * 1.4, fpW - PX * 16, PX * 4, PX);
  g.fill(0x5c3a1e);
  g.roundRect(x + PX * 6, y + T * 1.2, fpW - PX * 12, PX * 3, PX);
  g.fill(0x6b4226);
}

/**
 * Draw an office/desk chair.
 * Extracted from HouseScene.drawBedroom().
 * x, y are pixel positions of the top-left corner.
 */
export function drawChair(g: Graphics, x: number, y: number): void {
  const chW = T * 0.8;
  const chH = T * 0.6;
  // Seat
  g.roundRect(x, y, chW, chH, PX * 2);
  g.fill(0x333333);
  g.roundRect(x, y, chW, chH, PX * 2);
  g.stroke({ width: 1, color: 0x222222 });
  // Back
  g.roundRect(x + PX * 2, y - PX * 8, chW - PX * 4, PX * 10, PX * 3);
  g.fill(0x333333);
}

/**
 * Draw a rug (rectangle with decorative border).
 * Extracted from HouseScene.drawLivingRoom() rug rendering.
 * x, y are pixel positions of the top-left corner.
 * color overrides the rug fill color (default: maroon).
 */
export function drawRug(g: Graphics, x: number, y: number, color = 0x8b2252): void {
  const rugW = T * 4;
  const rugH = T * 3;
  g.roundRect(x, y, rugW, rugH, PX * 4);
  g.fill(color);
  g.roundRect(x + PX * 4, y + PX * 4, rugW - PX * 8, rugH - PX * 8, PX * 2);
  g.stroke({ width: 2, color: 0xdaa520, alpha: 0.6 });
  // Inner pattern
  g.roundRect(x + PX * 8, y + PX * 8, rugW - PX * 16, rugH - PX * 16, PX * 2);
  g.stroke({ width: 1, color: 0xcd853f, alpha: 0.4 });
}

/**
 * Draw a wall clock (round face with hands).
 * Extracted from HouseScene.drawLivingRoom().
 * x, y are pixel positions of the clock center.
 */
export function drawWallClock(g: Graphics, x: number, y: number): void {
  // Face
  g.circle(x, y, PX * 8);
  g.fill(0xfaf0e6);
  g.circle(x, y, PX * 8);
  g.stroke({ width: 2, color: 0x8b6914 });
  // Hour hand
  g.moveTo(x, y);
  g.lineTo(x, y - PX * 5);
  g.stroke({ width: 2, color: 0x333333 });
  // Minute hand
  g.moveTo(x, y);
  g.lineTo(x + PX * 3, y + PX * 2);
  g.stroke({ width: 1.5, color: 0x333333 });
  // Center dot
  g.circle(x, y, PX * 1);
  g.fill(0x333333);
}

/**
 * Draw a picture frame with a mountain painting.
 * Extracted from HouseScene.drawLivingRoom().
 * x, y are pixel positions of the top-left corner.
 */
export function drawPictureFrame(
  g: Graphics,
  x: number,
  y: number,
  theme: FurnitureTheme = DEFAULT_THEME,
): void {
  const pfW = T * 1.2;
  const pfH = T * 0.9;
  // Frame
  g.rect(x, y, pfW, pfH);
  g.fill(0x8b6914);
  // Canvas
  g.rect(x + PX * 3, y + PX * 3, pfW - PX * 6, pfH - PX * 6);
  g.fill(theme.painting);
  // Mountain
  g.moveTo(x + PX * 5, y + pfH - PX * 4);
  g.lineTo(x + PX * 12, y + PX * 6);
  g.lineTo(x + PX * 19, y + pfH - PX * 4);
  g.closePath();
  g.fill(theme.paintingMtn);
}

/**
 * Draw a mirror (rounded rectangle with blue tint).
 * Extracted from HouseScene.drawBedroom().
 * x, y are pixel positions of the top-left corner.
 */
export function drawMirror(g: Graphics, x: number, y: number): void {
  g.roundRect(x, y, T * 0.8, T * 1.2, PX * 2);
  g.fill(0x87ceeb);
  g.roundRect(x, y, T * 0.8, T * 1.2, PX * 2);
  g.fill({ color: 0xffffff, alpha: 0.2 });
  g.roundRect(x, y, T * 0.8, T * 1.2, PX * 2);
  g.stroke({ width: 2, color: 0xdaa520 });
}

/**
 * Draw a bedroom rug (elliptical).
 * Extracted from HouseScene.drawBedroom().
 * x, y are pixel positions of the center.
 * color overrides the rug fill color.
 */
export function drawBedroomRug(
  g: Graphics,
  x: number,
  y: number,
  color = 0x9370db,
): void {
  g.ellipse(x, y, T * 1, T * 0.8);
  g.fill(color);
  g.ellipse(x, y, T * 0.7, T * 0.5);
  g.stroke({ width: 1.5, color: 0xdaa520, alpha: 0.5 });
}

/** Category for furniture catalog entries. */
export type FurnitureCategory = "living" | "bedroom" | "decor";

/** Catalog entry describing a placeable furniture piece. */
export interface FurnitureCatalogEntry {
  type: string;
  name: string;
  category: FurnitureCategory;
  /** Approximate width in pixels at default scale. */
  widthPx: number;
  /** Approximate height in pixels at default scale. */
  heightPx: number;
}

/** Registry of all available furniture types for the resource editor. */
export const FURNITURE_CATALOG: FurnitureCatalogEntry[] = [
  { type: "sofa", name: "Sofa", category: "living", widthPx: T * 1.2, heightPx: T * 3 },
  { type: "coffee_table", name: "Coffee Table", category: "living", widthPx: T * 2, heightPx: T * 1.2 },
  { type: "bookshelf", name: "Bookshelf", category: "living", widthPx: T * 2, heightPx: T * 2 },
  { type: "fireplace", name: "Fireplace", category: "living", widthPx: T * 1.5, heightPx: T * 2 },
  { type: "wall_clock", name: "Wall Clock", category: "living", widthPx: PX * 16, heightPx: PX * 16 },
  { type: "picture_frame", name: "Picture Frame", category: "decor", widthPx: T * 1.2, heightPx: T * 0.9 },
  { type: "rug", name: "Rug (Rectangle)", category: "living", widthPx: T * 4, heightPx: T * 3 },
  { type: "bed", name: "Bed", category: "bedroom", widthPx: T * 2, heightPx: T * 3.5 },
  { type: "nightstand", name: "Nightstand", category: "bedroom", widthPx: T * 0.7, heightPx: T * 1 },
  { type: "wardrobe", name: "Wardrobe", category: "bedroom", widthPx: T * 1.8, heightPx: T * 2 },
  { type: "desk", name: "Desk", category: "bedroom", widthPx: T * 2.5, heightPx: T * 1.2 },
  { type: "chair", name: "Chair", category: "bedroom", widthPx: T * 0.8, heightPx: T * 0.6 },
  { type: "mirror", name: "Mirror", category: "decor", widthPx: T * 0.8, heightPx: T * 1.2 },
  { type: "bedroom_rug", name: "Rug (Oval)", category: "bedroom", widthPx: T * 2, heightPx: T * 1.6 },
];
