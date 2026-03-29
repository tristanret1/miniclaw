import { SCALED_TILE, MAP_COLS, MAP_ROWS } from "@/config";
import { Building } from "@/entities/Building";
import type { ClientMessage, BuildingLayout } from "@/net/Protocol";

type SendFn = (msg: ClientMessage) => void;

/**
 * LayoutEditor — drag-and-drop building repositioning mode.
 * When active, buildings can be dragged and snapped to grid.
 */
export class LayoutEditor {
  private active = false;
  private buildings = new Map<string, Building>();
  private savedPositions = new Map<string, { x: number; y: number }>();
  private sendFn: SendFn;
  private toolbarEl: HTMLElement;
  private overlayEl: HTMLElement;
  private dragging: Building | null = null;
  private dragOffsetX = 0;
  private dragOffsetY = 0;
  private onToggle: ((active: boolean) => void) | null = null;

  constructor(overlayEl: HTMLElement, sendFn: SendFn) {
    this.sendFn = sendFn;
    this.overlayEl = overlayEl;

    // Toolbar (shown when edit mode is active)
    this.toolbarEl = document.createElement("div");
    this.toolbarEl.id = "layout-editor-toolbar";
    this.toolbarEl.style.cssText = `
      display: none;
      position: absolute; top: 12px; right: 12px;
      background: rgba(0,0,0,0.85);
      border: 2px solid #fbbf24;
      border-radius: 8px;
      padding: 10px;
      color: #fff;
      font-family: 'Press Start 2P', monospace;
      font-size: 9px;
      pointer-events: auto;
      z-index: 25;
    `;
    this.toolbarEl.innerHTML = `
      <div style="color:#fbbf24;margin-bottom:8px;">Edit Mode</div>
      <div style="display:flex;gap:8px;">
        <button id="layout-save" style="
          background:#4ade80;color:#000;border:none;border-radius:4px;
          padding:6px 10px;cursor:pointer;
          font-family:'Press Start 2P',monospace;font-size:8px;
        ">Save</button>
        <button id="layout-cancel" style="
          background:#ef4444;color:#fff;border:none;border-radius:4px;
          padding:6px 10px;cursor:pointer;
          font-family:'Press Start 2P',monospace;font-size:8px;
        ">Cancel</button>
      </div>
    `;
    overlayEl.appendChild(this.toolbarEl);

    this.toolbarEl.querySelector("#layout-save")!.addEventListener("click", () => this.save());
    this.toolbarEl.querySelector("#layout-cancel")!.addEventListener("click", () => this.cancel());
  }

  setOnToggle(cb: (active: boolean) => void): void {
    this.onToggle = cb;
  }

  setBuildings(buildings: Map<string, Building>): void {
    this.buildings = buildings;
  }

  isActive(): boolean {
    return this.active;
  }

  toggle(): void {
    if (this.active) {
      this.cancel();
    } else {
      this.enter();
    }
  }

  enter(): void {
    this.active = true;
    this.toolbarEl.style.display = "block";

    // Save current positions for revert
    this.savedPositions.clear();
    for (const [id, building] of this.buildings) {
      this.savedPositions.set(id, { x: building.tileX, y: building.tileY });
    }

    // Make buildings draggable
    for (const building of this.buildings.values()) {
      building.container.eventMode = "static";
      building.container.cursor = "grab";
      building.container.on("pointerdown", (e) => this.onDragStart(building, e));
    }

    // Global move/up handlers
    this.overlayEl.style.pointerEvents = "auto";
    window.addEventListener("pointermove", this.onDragMove);
    window.addEventListener("pointerup", this.onDragEnd);

    this.onToggle?.(true);
  }

  private exit(): void {
    this.active = false;
    this.toolbarEl.style.display = "none";

    // Remove draggable from buildings
    for (const building of this.buildings.values()) {
      if (building.type !== "cottage") {
        building.container.eventMode = "none";
      }
      building.container.cursor = "default";
      building.container.off("pointerdown");
    }

    window.removeEventListener("pointermove", this.onDragMove);
    window.removeEventListener("pointerup", this.onDragEnd);
    this.overlayEl.style.pointerEvents = "none";

    this.onToggle?.(false);
  }

  private save(): void {
    const layouts: BuildingLayout[] = [];
    for (const [id, building] of this.buildings) {
      layouts.push({ id, x: building.tileX, y: building.tileY });
    }
    this.sendFn({ type: "save_layout", buildings: layouts });
    this.exit();
  }

  private cancel(): void {
    // Revert to saved positions
    for (const [id, pos] of this.savedPositions) {
      const building = this.buildings.get(id);
      if (building) {
        building.moveTo(pos.x, pos.y);
      }
    }
    this.exit();
  }

  private onDragStart = (building: Building, e: { global: { x: number; y: number } }): void => {
    if (!this.active) return;
    this.dragging = building;
    this.dragOffsetX = e.global.x - building.container.x;
    this.dragOffsetY = e.global.y - building.container.y;
    building.container.cursor = "grabbing";
  };

  private onDragMove = (e: PointerEvent): void => {
    if (!this.dragging) return;
    const rawX = e.clientX - this.dragOffsetX;
    const rawY = e.clientY - this.dragOffsetY;

    // Snap to grid
    const tileX = Math.round(rawX / SCALED_TILE);
    const tileY = Math.round(rawY / SCALED_TILE);

    // Clamp to map bounds
    const clampedX = Math.max(0, Math.min(MAP_COLS - this.dragging.widthTiles, tileX));
    const clampedY = Math.max(0, Math.min(MAP_ROWS - this.dragging.heightTiles, tileY));

    this.dragging.moveTo(clampedX, clampedY);
  };

  private onDragEnd = (): void => {
    if (this.dragging) {
      this.dragging.container.cursor = "grab";
      this.dragging = null;
    }
  };
}
