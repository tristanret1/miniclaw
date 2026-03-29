/**
 * Furniture selection palette for the Interior Editor.
 * Renders grouped furniture items in the sidebar with color swatches.
 */

import {
  FURNITURE_CATALOG,
  type FurnitureCategory,
  type FurnitureCatalogEntry,
} from "../renderers/FurnitureRenderer";

/** Category display labels. */
const CATEGORY_LABELS: Record<FurnitureCategory, string> = {
  living: "Living Room",
  bedroom: "Bedroom",
  decor: "Decor",
};

/** Approximate swatch colors for each furniture type (for the palette preview). */
const SWATCH_COLORS: Record<string, string> = {
  sofa: "#c0392b",
  coffee_table: "#a0522d",
  bookshelf: "#654321",
  fireplace: "#808080",
  wall_clock: "#faf0e6",
  picture_frame: "#8b6914",
  rug: "#8b2252",
  bed: "#8b6914",
  nightstand: "#8b6914",
  wardrobe: "#8b6914",
  desk: "#a0522d",
  chair: "#333333",
  mirror: "#87ceeb",
  bedroom_rug: "#9370db",
};

export class FurniturePalette {
  private container: HTMLElement | null = null;
  private _selected: string | null = null;
  private _onSelect: ((furnitureType: string) => void) | null = null;

  set onSelect(cb: ((furnitureType: string) => void) | null) {
    this._onSelect = cb;
  }

  get selected(): string | null {
    return this._selected;
  }

  /** Render the palette into the given sidebar element. */
  attach(sidebarEl: HTMLElement): void {
    this.container = sidebarEl;
    this.render();
  }

  /** Remove palette content from the sidebar. */
  detach(): void {
    if (this.container) {
      this.container.innerHTML = "";
    }
    this.container = null;
    this._selected = null;
  }

  /** Clear the current selection. */
  clearSelection(): void {
    this._selected = null;
    this.render();
  }

  private render(): void {
    if (!this.container) return;

    const grouped = new Map<FurnitureCategory, FurnitureCatalogEntry[]>();
    for (const entry of FURNITURE_CATALOG) {
      let list = grouped.get(entry.category);
      if (!list) {
        list = [];
        grouped.set(entry.category, list);
      }
      list.push(entry);
    }

    let html = "";
    const categoryOrder: FurnitureCategory[] = ["living", "bedroom", "decor"];
    for (const cat of categoryOrder) {
      const items = grouped.get(cat);
      if (!items || items.length === 0) continue;

      html += `<h3 style="
        padding:8px 10px; font-size:11px; color:#e94560;
        border-bottom:1px solid #0f3460; margin:0;
      ">${CATEGORY_LABELS[cat]}</h3>`;

      html += `<div style="display:flex; flex-direction:column; gap:2px; padding:6px 8px;">`;
      for (const item of items) {
        const isSelected = this._selected === item.type;
        const swatchColor = SWATCH_COLORS[item.type] ?? "#888";
        html += `<div class="furniture-palette-item" data-type="${item.type}" style="
          display:flex; align-items:center; gap:8px;
          padding:5px 8px; border-radius:3px; cursor:pointer;
          background:${isSelected ? "#2a1a3e" : "#1a1a2e"};
          border:2px solid ${isSelected ? "#e94560" : "transparent"};
          font-size:11px; color:#e0e0e0;
        ">
          <span style="
            display:inline-block; width:14px; height:14px;
            border-radius:2px; background:${swatchColor};
            border:1px solid rgba(255,255,255,0.15);
            flex-shrink:0;
          "></span>
          <span>${item.name}</span>
        </div>`;
      }
      html += `</div>`;
    }

    this.container.innerHTML = html;

    // Wire click handlers
    for (const el of this.container.querySelectorAll<HTMLElement>(".furniture-palette-item")) {
      el.addEventListener("click", () => {
        const type = el.dataset.type;
        if (!type) return;
        this._selected = type;
        this._onSelect?.(type);
        this.render();
      });
      el.addEventListener("mouseenter", () => {
        if (el.dataset.type !== this._selected) {
          el.style.borderColor = "#e94560";
        }
      });
      el.addEventListener("mouseleave", () => {
        if (el.dataset.type !== this._selected) {
          el.style.borderColor = "transparent";
        }
      });
    }
  }
}
