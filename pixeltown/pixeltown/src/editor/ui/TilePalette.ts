/**
 * Sidebar tile palette for selecting terrain, buildings, and decorations.
 * Renders into a provided HTML element using HTML/CSS (not PixiJS).
 */

import { TERRAIN_COLORS, TerrainType, TERRAIN_NAMES } from "../types";
import type { DecorationType } from "../types";

// ---------------------------------------------------------------------------
// Palette data
// ---------------------------------------------------------------------------

interface PaletteItem {
  id: string;
  label: string;
  color: number;
  category: "terrain" | "building" | "decoration";
}

const TERRAIN_ITEMS: PaletteItem[] = [
  { id: "grass", label: "Grass", color: TERRAIN_COLORS[TerrainType.grass], category: "terrain" },
  { id: "dirt", label: "Dirt", color: TERRAIN_COLORS[TerrainType.dirt], category: "terrain" },
  { id: "stone", label: "Stone", color: TERRAIN_COLORS[TerrainType.stone], category: "terrain" },
  { id: "water", label: "Water", color: TERRAIN_COLORS[TerrainType.water], category: "terrain" },
  { id: "sand", label: "Sand", color: TERRAIN_COLORS[TerrainType.sand], category: "terrain" },
  { id: "path", label: "Path", color: TERRAIN_COLORS[TerrainType.path], category: "terrain" },
];

const BUILDING_ITEMS: PaletteItem[] = [
  { id: "cottage", label: "Cottage", color: 0xf5deb3, category: "building" },
  { id: "library", label: "Library", color: 0xd2b48c, category: "building" },
  { id: "shop", label: "Shop", color: 0xe8d5b7, category: "building" },
  { id: "plaza", label: "Plaza", color: 0xc9b99a, category: "building" },
];

const DECORATION_ITEMS: PaletteItem[] = [
  { id: "tree_oak", label: "Oak Tree", color: 0x228b22, category: "decoration" },
  { id: "tree_pine", label: "Pine Tree", color: 0x006400, category: "decoration" },
  { id: "bush", label: "Bush", color: 0x32cd32, category: "decoration" },
  { id: "flower", label: "Flower", color: 0xff69b4, category: "decoration" },
  { id: "rock", label: "Rock", color: 0x808080, category: "decoration" },
  { id: "fence_h", label: "Fence H", color: 0xdeb887, category: "decoration" },
  { id: "fence_v", label: "Fence V", color: 0xdeb887, category: "decoration" },
  { id: "mushroom", label: "Mushroom", color: 0xff6347, category: "decoration" },
  { id: "bench", label: "Bench", color: 0x8b4513, category: "decoration" },
];

// ---------------------------------------------------------------------------
// TilePalette
// ---------------------------------------------------------------------------

export type PaletteSelectCallback = (category: string, itemId: string) => void;

export class TilePalette {
  private rootEl: HTMLElement;
  private selectedEl: HTMLElement | null = null;
  private _onSelect: PaletteSelectCallback | null = null;

  constructor(container: HTMLElement) {
    this.rootEl = container;
    this.buildUI();
    // Select grass by default.
    const first = this.rootEl.querySelector<HTMLElement>('[data-item-id="grass"]');
    if (first) this.selectElement(first);
  }

  set onSelect(cb: PaletteSelectCallback | null) {
    this._onSelect = cb;
  }

  // -----------------------------------------------------------------------
  // Build HTML
  // -----------------------------------------------------------------------

  private buildUI(): void {
    this.rootEl.innerHTML = "";

    this.addSection("Terrain", TERRAIN_ITEMS);
    this.addSection("Buildings", BUILDING_ITEMS);
    this.addSection("Decorations", DECORATION_ITEMS);
  }

  private addSection(title: string, items: PaletteItem[]): void {
    // Section header.
    const header = document.createElement("div");
    header.style.cssText =
      "padding:6px 10px;font-size:10px;color:#e94560;font-weight:bold;" +
      "border-bottom:1px solid #0f3460;font-family:'Press Start 2P',monospace;";
    header.textContent = title;
    this.rootEl.appendChild(header);

    // Grid container.
    const grid = document.createElement("div");
    grid.style.cssText =
      "display:grid;grid-template-columns:repeat(3,1fr);gap:4px;padding:6px 8px;";
    this.rootEl.appendChild(grid);

    for (const item of items) {
      const el = this.createItemElement(item);
      grid.appendChild(el);
    }
  }

  private createItemElement(item: PaletteItem): HTMLElement {
    const el = document.createElement("div");
    el.dataset.category = item.category;
    el.dataset.itemId = item.id;
    el.title = item.label;

    const hex = "#" + item.color.toString(16).padStart(6, "0");

    el.style.cssText =
      `display:flex;flex-direction:column;align-items:center;justify-content:center;` +
      `gap:3px;padding:4px 2px;border:2px solid transparent;border-radius:3px;` +
      `cursor:pointer;background:#1a1a2e;transition:border-color 0.15s;`;

    // Swatch.
    const swatch = document.createElement("div");
    swatch.style.cssText =
      `width:28px;height:28px;border-radius:3px;background:${hex};` +
      `border:1px solid rgba(255,255,255,0.1);`;

    // Add an icon shape overlay for non-terrain items.
    if (item.category === "building") {
      swatch.style.cssText += `position:relative;`;
      const icon = document.createElement("div");
      // Small house silhouette via border trick.
      icon.style.cssText =
        `position:absolute;top:4px;left:50%;transform:translateX(-50%);` +
        `width:14px;height:10px;background:rgba(0,0,0,0.25);border-radius:1px;`;
      const roof = document.createElement("div");
      roof.style.cssText =
        `position:absolute;top:0;left:50%;transform:translateX(-50%);` +
        `width:0;height:0;border-left:10px solid transparent;border-right:10px solid transparent;` +
        `border-bottom:6px solid rgba(0,0,0,0.3);`;
      swatch.appendChild(roof);
      swatch.appendChild(icon);
    } else if (item.category === "decoration") {
      swatch.style.borderRadius = this.getDecorationSwatchRadius(item.id);
    }

    // Label.
    const label = document.createElement("span");
    label.style.cssText = "font-size:9px;color:#aaa;text-align:center;line-height:1.1;";
    label.textContent = item.label;

    el.appendChild(swatch);
    el.appendChild(label);

    // Hover.
    el.addEventListener("mouseenter", () => {
      if (el !== this.selectedEl) {
        el.style.borderColor = "#e94560";
      }
    });
    el.addEventListener("mouseleave", () => {
      if (el !== this.selectedEl) {
        el.style.borderColor = "transparent";
      }
    });

    // Click.
    el.addEventListener("click", () => {
      this.selectElement(el);
      this._onSelect?.(item.category, item.id);
    });

    return el;
  }

  private selectElement(el: HTMLElement): void {
    if (this.selectedEl) {
      this.selectedEl.style.borderColor = "transparent";
      this.selectedEl.style.background = "#1a1a2e";
    }
    this.selectedEl = el;
    el.style.borderColor = "#e94560";
    el.style.background = "#2a1a3e";
  }

  private getDecorationSwatchRadius(id: string): string {
    switch (id) {
      case "tree_oak":
      case "tree_pine":
      case "bush":
      case "flower":
      case "mushroom":
        return "50%";
      case "rock":
        return "50%/40%";
      default:
        return "3px";
    }
  }
}
