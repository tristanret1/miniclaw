/**
 * Interior Editor mode — room furniture editing.
 * Renders a room view with floor, walls, divider, doorway, and allows
 * placing/selecting/moving/deleting furniture from the FURNITURE_CATALOG.
 */

import { Container, Graphics } from "pixi.js";
import { SCALED_TILE } from "@/config";
import { CommandHistory, EditorCommand } from "../CommandHistory";
import type { InteriorConfig, RoomLayout, FurniturePlacement } from "../types";
import {
  FURNITURE_CATALOG,
  type FurnitureTheme,
  type FurnitureCatalogEntry,
  DEFAULT_THEME,
  drawSofa,
  drawBed,
  drawDesk,
  drawBookshelf,
  drawCoffeeTable,
  drawWardrobe,
  drawNightstand,
  drawFireplace,
  drawChair,
  drawRug,
  drawWallClock,
  drawPictureFrame,
  drawMirror,
  drawBedroomRug,
} from "../renderers/FurnitureRenderer";

const T = SCALED_TILE;
const PX = T / 16;

// ---------------------------------------------------------------------------
// Theme definitions (warm / forest / lavender) — matches HouseScene.getTheme()
// ---------------------------------------------------------------------------

const THEMES: { name: string; theme: FurnitureTheme }[] = [
  {
    name: "Warm / Classic",
    theme: {
      wall: 0xd4c5a9, wainscot: 0xc4b599, floorA: 0x9b7b55, floorB: 0x8b6b45,
      rug: 0x8b2252, rugAccent: 0xdaa520, blanket: 0x4169e1, blanketDark: 0x2c4ba0,
      sofa: 0xc0392b, sofaFrame: 0x6b3a2a, pillow: 0xe8c840,
      painting: 0x87ceeb, paintingMtn: 0x4a7a4a, bedroomRug: 0x9370db,
    },
  },
  {
    name: "Cozy / Forest",
    theme: {
      wall: 0xc8d5c0, wainscot: 0xb0c4a8, floorA: 0x8a7a5a, floorB: 0x7a6a4a,
      rug: 0x2e5e4e, rugAccent: 0x8fbc8f, blanket: 0xd2691e, blanketDark: 0xa0522d,
      sofa: 0x5f9ea0, sofaFrame: 0x3a6a6e, pillow: 0xfaf0e6,
      painting: 0xffd700, paintingMtn: 0x8b4513, bedroomRug: 0x8fbc8f,
    },
  },
  {
    name: "Elegant / Lavender",
    theme: {
      wall: 0xd8cce8, wainscot: 0xc8b8d8, floorA: 0x9a8a7a, floorB: 0x8a7a6a,
      rug: 0x6a3d7a, rugAccent: 0xdda0dd, blanket: 0x9370db, blanketDark: 0x7b60bb,
      sofa: 0xda70d6, sofaFrame: 0x8b4585, pillow: 0xfffaf0,
      painting: 0xffb6c1, paintingMtn: 0x9370db, bedroomRug: 0xdda0dd,
    },
  },
];

/** Lookup a catalog entry by type string. */
function catalogLookup(type: string): FurnitureCatalogEntry | undefined {
  return FURNITURE_CATALOG.find((e) => e.type === type);
}

// ---------------------------------------------------------------------------
// Commands
// ---------------------------------------------------------------------------

export class PlaceFurnitureCommand implements EditorCommand {
  readonly description: string;
  constructor(
    private editor: InteriorEditor,
    private roomId: string,
    private placement: FurniturePlacement,
  ) {
    this.description = `Place ${placement.type}`;
  }
  execute(): void {
    const furniture = this.editor.getFurnitureList(this.roomId);
    furniture.push({ ...this.placement });
    this.editor.redraw();
  }
  undo(): void {
    const furniture = this.editor.getFurnitureList(this.roomId);
    // Remove last matching placement
    for (let i = furniture.length - 1; i >= 0; i--) {
      const f = furniture[i];
      if (f.type === this.placement.type && f.x === this.placement.x && f.y === this.placement.y) {
        furniture.splice(i, 1);
        break;
      }
    }
    this.editor.redraw();
  }
}

export class MoveFurnitureCommand implements EditorCommand {
  readonly description: string;
  constructor(
    private editor: InteriorEditor,
    private roomId: string,
    private index: number,
    private oldX: number,
    private oldY: number,
    private newX: number,
    private newY: number,
  ) {
    this.description = "Move furniture";
  }
  execute(): void {
    const furniture = this.editor.getFurnitureList(this.roomId);
    if (this.index < furniture.length) {
      furniture[this.index].x = this.newX;
      furniture[this.index].y = this.newY;
    }
    this.editor.redraw();
  }
  undo(): void {
    const furniture = this.editor.getFurnitureList(this.roomId);
    if (this.index < furniture.length) {
      furniture[this.index].x = this.oldX;
      furniture[this.index].y = this.oldY;
    }
    this.editor.redraw();
  }
}

export class DeleteFurnitureCommand implements EditorCommand {
  readonly description: string;
  private deleted: FurniturePlacement;
  constructor(
    private editor: InteriorEditor,
    private roomId: string,
    private index: number,
  ) {
    this.deleted = { type: "", x: 0, y: 0 };
    this.description = "Delete furniture";
  }
  execute(): void {
    const furniture = this.editor.getFurnitureList(this.roomId);
    if (this.index < furniture.length) {
      this.deleted = { ...furniture[this.index] };
      furniture.splice(this.index, 1);
    }
    this.editor.redraw();
  }
  undo(): void {
    const furniture = this.editor.getFurnitureList(this.roomId);
    furniture.splice(this.index, 0, { ...this.deleted });
    this.editor.redraw();
  }
}

export class ChangeThemeCommand implements EditorCommand {
  readonly description = "Change theme";
  constructor(
    private editor: InteriorEditor,
    private roomId: string,
    private oldThemeIndex: number,
    private newThemeIndex: number,
  ) {}
  execute(): void {
    this.editor.setThemeIndex(this.roomId, this.newThemeIndex);
    this.editor.redraw();
  }
  undo(): void {
    this.editor.setThemeIndex(this.roomId, this.oldThemeIndex);
    this.editor.redraw();
  }
}

// ---------------------------------------------------------------------------
// InteriorEditor
// ---------------------------------------------------------------------------

/**
 * Internal room state stored per room ID. The "layouts" in InteriorConfig
 * store serialized RoomLayout, but in the editor we also track theme index
 * and selected furniture per room.
 */
interface RoomState {
  furniture: FurniturePlacement[];
  themeIndex: number;
}

export class InteriorEditor {
  private container: Container | null = null;
  private gfx: Graphics = new Graphics();
  private selectionGfx: Graphics = new Graphics();
  private commandHistory: CommandHistory | null = null;

  /** Room state keyed by building ID. */
  private rooms: Map<string, RoomState> = new Map();

  /** Currently active room ID. */
  private _currentRoomId = "default";

  /** Index of selected furniture in the current room's list, or -1. */
  private _selectedIndex = -1;

  /** The furniture type selected from the palette for placement. */
  private _placementType: string | null = null;

  // Drag state
  private _dragging = false;
  private _dragStartX = 0;
  private _dragStartY = 0;
  private _dragOrigX = 0;
  private _dragOrigY = 0;

  // Room geometry (computed on draw)
  private _roomOx = 0;
  private _roomOy = 0;
  private _roomW = 0;
  private _roomH = 0;
  private _wallH = 0;
  private _dividerX = 0;

  // Canvas element for mouse events
  private _canvas: HTMLCanvasElement | null = null;

  // Bound event handlers for cleanup
  private _onPointerDown: ((e: PointerEvent) => void) | null = null;
  private _onPointerMove: ((e: PointerEvent) => void) | null = null;
  private _onPointerUp: ((e: PointerEvent) => void) | null = null;
  private _onKeyDown: ((e: KeyboardEvent) => void) | null = null;

  // Properties panel element
  private _propsEl: HTMLElement | null = null;

  // ---------------------------------------------------------------------------
  // Room ID management (for the dropdown)
  // ---------------------------------------------------------------------------

  /** Available building IDs to edit. */
  private _roomIds: string[] = ["default"];

  get currentRoomId(): string {
    return this._currentRoomId;
  }

  set currentRoomId(id: string) {
    this._currentRoomId = id;
    this._selectedIndex = -1;
    this._placementType = null;
    this.ensureRoom(id);
    this.redraw();
    this.renderProperties();
  }

  /** Set the list of available room IDs (typically from buildings in town config). */
  setRoomIds(ids: string[]): void {
    this._roomIds = ids.length > 0 ? ids : ["default"];
    if (!this._roomIds.includes(this._currentRoomId)) {
      this._currentRoomId = this._roomIds[0];
    }
    this.renderProperties();
  }

  // ---------------------------------------------------------------------------
  // Palette integration
  // ---------------------------------------------------------------------------

  /** Called by the palette when a furniture type is selected for placement. */
  setPlacementType(type: string | null): void {
    this._placementType = type;
    // Deselect any existing furniture when entering placement mode
    if (type !== null) {
      this._selectedIndex = -1;
      this.drawSelection();
    }
  }

  // ---------------------------------------------------------------------------
  // Room state helpers
  // ---------------------------------------------------------------------------

  private ensureRoom(id: string): RoomState {
    let state = this.rooms.get(id);
    if (!state) {
      state = { furniture: [], themeIndex: 0 };
      this.rooms.set(id, state);
    }
    return state;
  }

  private currentRoom(): RoomState {
    return this.ensureRoom(this._currentRoomId);
  }

  /** Public accessor for commands to mutate the furniture list. */
  getFurnitureList(roomId: string): FurniturePlacement[] {
    return this.ensureRoom(roomId).furniture;
  }

  /** Public accessor for commands to change theme. */
  setThemeIndex(roomId: string, index: number): void {
    this.ensureRoom(roomId).themeIndex = index;
  }

  private currentTheme(): FurnitureTheme {
    const room = this.currentRoom();
    return THEMES[room.themeIndex % THEMES.length].theme;
  }

  // ---------------------------------------------------------------------------
  // Attach / Detach
  // ---------------------------------------------------------------------------

  attach(pixiContainer: Container, commandHistory: CommandHistory): void {
    this.container = pixiContainer;
    this.commandHistory = commandHistory;

    this.gfx = new Graphics();
    this.gfx.label = "InteriorEditorGfx";
    this.container.addChild(this.gfx);

    this.selectionGfx = new Graphics();
    this.selectionGfx.label = "InteriorSelection";
    this.container.addChild(this.selectionGfx);

    // Find canvas
    this._canvas = document.getElementById("editor-canvas") as HTMLCanvasElement | null;
    this._propsEl = document.getElementById("prop-content");

    // Wire events
    this._onPointerDown = this.handlePointerDown.bind(this);
    this._onPointerMove = this.handlePointerMove.bind(this);
    this._onPointerUp = this.handlePointerUp.bind(this);
    this._onKeyDown = this.handleKeyDown.bind(this);

    this._canvas?.addEventListener("pointerdown", this._onPointerDown);
    this._canvas?.addEventListener("pointermove", this._onPointerMove);
    this._canvas?.addEventListener("pointerup", this._onPointerUp);
    window.addEventListener("keydown", this._onKeyDown);

    this.ensureRoom(this._currentRoomId);
    this.redraw();
    this.renderProperties();
  }

  detach(): void {
    if (this._canvas && this._onPointerDown) {
      this._canvas.removeEventListener("pointerdown", this._onPointerDown);
    }
    if (this._canvas && this._onPointerMove) {
      this._canvas.removeEventListener("pointermove", this._onPointerMove);
    }
    if (this._canvas && this._onPointerUp) {
      this._canvas.removeEventListener("pointerup", this._onPointerUp);
    }
    if (this._onKeyDown) {
      window.removeEventListener("keydown", this._onKeyDown);
    }
    this._onPointerDown = null;
    this._onPointerMove = null;
    this._onPointerUp = null;
    this._onKeyDown = null;

    if (this.container) {
      this.container.removeChild(this.gfx);
      this.container.removeChild(this.selectionGfx);
    }
    this.container = null;
    this._canvas = null;
    this._selectedIndex = -1;
    this._dragging = false;

    // Clear properties
    if (this._propsEl) {
      this._propsEl.innerHTML = `<p style="color:#666; font-size:11px;">Select an element to view properties.</p>`;
    }
    this._propsEl = null;
  }

  // ---------------------------------------------------------------------------
  // Config I/O
  // ---------------------------------------------------------------------------

  getConfig(): InteriorConfig {
    const layouts: Record<string, RoomLayout> = {};
    for (const [id, state] of this.rooms.entries()) {
      layouts[id] = {
        rooms: [
          {
            id,
            width: 22,
            height: 14,
            floor: [],
            walls: [],
            furniture: state.furniture.map((f) => ({ ...f })),
            doors: [],
          },
        ],
      };
      // Store themeIndex in a custom field (extend type loosely or embed in first room)
      // We store it as metadata in the layout for round-tripping
      (layouts[id] as RoomLayout & { themeIndex?: number }).themeIndex = state.themeIndex;
    }
    return { layouts };
  }

  loadConfig(config: InteriorConfig): void {
    this.rooms.clear();
    for (const [id, layout] of Object.entries(config.layouts)) {
      const furniture: FurniturePlacement[] = [];
      for (const room of layout.rooms) {
        for (const f of room.furniture) {
          furniture.push({ ...f });
        }
      }
      const themeIndex = (layout as RoomLayout & { themeIndex?: number }).themeIndex ?? 0;
      this.rooms.set(id, { furniture, themeIndex });
    }
    // Update room IDs from loaded config
    const loadedIds = Object.keys(config.layouts);
    if (loadedIds.length > 0) {
      // Merge with existing room IDs
      for (const id of loadedIds) {
        if (!this._roomIds.includes(id)) {
          this._roomIds.push(id);
        }
      }
    }
    this.ensureRoom(this._currentRoomId);
    this._selectedIndex = -1;
    this.redraw();
    this.renderProperties();
  }

  // ---------------------------------------------------------------------------
  // Coordinate conversion
  // ---------------------------------------------------------------------------

  /** Convert page pixel coordinates from a pointer event to canvas-space pixels. */
  private canvasCoords(e: PointerEvent): { cx: number; cy: number } {
    if (!this._canvas) return { cx: 0, cy: 0 };
    const rect = this._canvas.getBoundingClientRect();
    const scaleX = this._canvas.width / (rect.width * (window.devicePixelRatio || 1));
    const scaleY = this._canvas.height / (rect.height * (window.devicePixelRatio || 1));
    const cx = (e.clientX - rect.left) * (window.devicePixelRatio || 1) * scaleX;
    const cy = (e.clientY - rect.top) * (window.devicePixelRatio || 1) * scaleY;
    return { cx, cy };
  }

  /** Snap a pixel coordinate to the PX sub-grid. */
  private snapToPx(v: number): number {
    return Math.round(v / PX) * PX;
  }

  // ---------------------------------------------------------------------------
  // Hit testing
  // ---------------------------------------------------------------------------

  /** Return the index of the furniture piece at (cx, cy), or -1. */
  private hitTest(cx: number, cy: number): number {
    const room = this.currentRoom();
    // Iterate in reverse so topmost (last drawn) is tested first
    for (let i = room.furniture.length - 1; i >= 0; i--) {
      const f = room.furniture[i];
      const entry = catalogLookup(f.type);
      if (!entry) continue;
      const fx = this._roomOx + f.x;
      const fy = this._roomOy + this._wallH + f.y;
      if (cx >= fx && cx <= fx + entry.widthPx && cy >= fy && cy <= fy + entry.heightPx) {
        return i;
      }
    }
    return -1;
  }

  // ---------------------------------------------------------------------------
  // Event handlers
  // ---------------------------------------------------------------------------

  private handlePointerDown(e: PointerEvent): void {
    const { cx, cy } = this.canvasCoords(e);

    // If we have a placement type from the palette, place it on click
    if (this._placementType) {
      const entry = catalogLookup(this._placementType);
      if (!entry) return;

      // Compute position relative to room interior (floor area)
      const relX = cx - this._roomOx;
      const relY = cy - (this._roomOy + this._wallH);

      // Check click is within room floor area
      if (relX < 0 || relY < 0 || relX > this._roomW || relY > this._roomH - this._wallH) {
        return;
      }

      const snappedX = this.snapToPx(relX);
      const snappedY = this.snapToPx(relY);

      const placement: FurniturePlacement = {
        type: this._placementType,
        x: snappedX,
        y: snappedY,
      };

      this.commandHistory?.execute(
        new PlaceFurnitureCommand(this, this._currentRoomId, placement),
      );
      this.updateStatus(`Placed ${entry.name}`);
      return;
    }

    // Otherwise, try to select or start dragging existing furniture
    const idx = this.hitTest(cx, cy);
    if (idx >= 0) {
      this._selectedIndex = idx;
      const f = this.currentRoom().furniture[idx];
      this._dragging = true;
      this._dragStartX = cx;
      this._dragStartY = cy;
      this._dragOrigX = f.x;
      this._dragOrigY = f.y;
      this.drawSelection();
      this.renderProperties();
      return;
    }

    // Clicked empty space — deselect
    this._selectedIndex = -1;
    this.drawSelection();
    this.renderProperties();
  }

  private handlePointerMove(e: PointerEvent): void {
    if (!this._dragging || this._selectedIndex < 0) return;
    const { cx, cy } = this.canvasCoords(e);
    const dx = cx - this._dragStartX;
    const dy = cy - this._dragStartY;

    const newX = this.snapToPx(this._dragOrigX + dx);
    const newY = this.snapToPx(this._dragOrigY + dy);

    const room = this.currentRoom();
    if (this._selectedIndex < room.furniture.length) {
      room.furniture[this._selectedIndex].x = newX;
      room.furniture[this._selectedIndex].y = newY;
      this.redraw();
    }
  }

  private handlePointerUp(_e: PointerEvent): void {
    if (!this._dragging || this._selectedIndex < 0) return;
    this._dragging = false;

    const room = this.currentRoom();
    if (this._selectedIndex >= room.furniture.length) return;

    const f = room.furniture[this._selectedIndex];
    const newX = f.x;
    const newY = f.y;

    // Only create a command if the position actually changed
    if (newX !== this._dragOrigX || newY !== this._dragOrigY) {
      // Restore original position — the command execute() will set new position
      f.x = this._dragOrigX;
      f.y = this._dragOrigY;

      this.commandHistory?.execute(
        new MoveFurnitureCommand(
          this,
          this._currentRoomId,
          this._selectedIndex,
          this._dragOrigX,
          this._dragOrigY,
          newX,
          newY,
        ),
      );
      this.updateStatus("Moved furniture");
    }
  }

  private handleKeyDown(e: KeyboardEvent): void {
    const tag = (e.target as HTMLElement).tagName;
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;

    if ((e.key === "Delete" || e.key === "Backspace") && this._selectedIndex >= 0) {
      e.preventDefault();
      this.commandHistory?.execute(
        new DeleteFurnitureCommand(this, this._currentRoomId, this._selectedIndex),
      );
      this.updateStatus("Deleted furniture");
      this._selectedIndex = -1;
      this.drawSelection();
      this.renderProperties();
    }

    // Escape clears placement mode and selection
    if (e.key === "Escape") {
      this._placementType = null;
      this._selectedIndex = -1;
      this.drawSelection();
      this.renderProperties();
    }
  }

  // ---------------------------------------------------------------------------
  // Properties panel
  // ---------------------------------------------------------------------------

  private renderProperties(): void {
    if (!this._propsEl) return;

    const room = this.currentRoom();
    const themeEntry = THEMES[room.themeIndex % THEMES.length];

    let html = "";

    // Room selector
    html += `<div style="margin-bottom:12px;">`;
    html += `<div class="prop-row"><label>Room</label>
      <select id="interior-room-select" style="
        width:120px; background:#1a1a2e; color:#e0e0e0; border:1px solid #0f3460;
        padding:3px 6px; border-radius:2px; font-size:12px;
      ">`;
    for (const id of this._roomIds) {
      html += `<option value="${id}"${id === this._currentRoomId ? " selected" : ""}>${id}</option>`;
    }
    html += `</select></div>`;

    // Theme selector
    html += `<div class="prop-row"><label>Theme</label>
      <select id="interior-theme-select" style="
        width:120px; background:#1a1a2e; color:#e0e0e0; border:1px solid #0f3460;
        padding:3px 6px; border-radius:2px; font-size:12px;
      ">`;
    for (let i = 0; i < THEMES.length; i++) {
      html += `<option value="${i}"${i === room.themeIndex ? " selected" : ""}>${THEMES[i].name}</option>`;
    }
    html += `</select></div>`;
    html += `</div>`;

    // Selected furniture info
    if (this._selectedIndex >= 0 && this._selectedIndex < room.furniture.length) {
      const f = room.furniture[this._selectedIndex];
      const entry = catalogLookup(f.type);
      html += `<h3 style="font-size:11px; color:#e94560; margin-bottom:8px;">Selected: ${entry?.name ?? f.type}</h3>`;
      html += `<div class="prop-row"><label>X</label><span style="color:#e0e0e0;">${Math.round(f.x)}</span></div>`;
      html += `<div class="prop-row"><label>Y</label><span style="color:#e0e0e0;">${Math.round(f.y)}</span></div>`;
      if (entry) {
        html += `<div class="prop-row"><label>Size</label><span style="color:#e0e0e0;">${Math.round(entry.widthPx)}x${Math.round(entry.heightPx)}</span></div>`;
      }
      html += `<div style="margin-top:8px;">
        <button id="interior-delete-btn" style="
          background:#e94560; color:#fff; border:none; border-radius:3px;
          padding:5px 12px; cursor:pointer; font-size:11px;
        ">Delete</button>
      </div>`;
    } else {
      html += `<p style="color:#666; font-size:11px; margin-top:8px;">
        ${this._placementType ? "Click in room to place furniture." : "Click furniture to select, or choose from palette."}
      </p>`;
    }

    // Furniture count
    html += `<div style="margin-top:12px; color:#666; font-size:10px;">
      Furniture: ${room.furniture.length} items
    </div>`;

    this._propsEl.innerHTML = html;

    // Wire events
    const roomSelect = this._propsEl.querySelector("#interior-room-select") as HTMLSelectElement | null;
    roomSelect?.addEventListener("change", () => {
      this.currentRoomId = roomSelect.value;
    });

    const themeSelect = this._propsEl.querySelector("#interior-theme-select") as HTMLSelectElement | null;
    themeSelect?.addEventListener("change", () => {
      const newIndex = parseInt(themeSelect.value, 10);
      const oldIndex = room.themeIndex;
      if (newIndex !== oldIndex) {
        this.commandHistory?.execute(
          new ChangeThemeCommand(this, this._currentRoomId, oldIndex, newIndex),
        );
        this.updateStatus(`Theme: ${THEMES[newIndex].name}`);
        this.renderProperties();
      }
    });

    const deleteBtn = this._propsEl.querySelector("#interior-delete-btn");
    deleteBtn?.addEventListener("click", () => {
      if (this._selectedIndex >= 0) {
        this.commandHistory?.execute(
          new DeleteFurnitureCommand(this, this._currentRoomId, this._selectedIndex),
        );
        this._selectedIndex = -1;
        this.drawSelection();
        this.renderProperties();
      }
    });
  }

  // ---------------------------------------------------------------------------
  // Drawing
  // ---------------------------------------------------------------------------

  /** Full redraw of the room and furniture. */
  redraw(): void {
    const g = this.gfx;
    g.clear();

    const theme = this.currentTheme();
    const room = this.currentRoom();

    // Compute room dimensions (similar to HouseScene)
    const viewW = this._canvas?.width
      ? this._canvas.width / (window.devicePixelRatio || 1)
      : 22 * T;
    const viewH = this._canvas?.height
      ? this._canvas.height / (window.devicePixelRatio || 1)
      : 14 * T;
    const margin = T;
    const roomW = Math.min(viewW - margin * 2, 22 * T);
    const roomH = Math.min(viewH - margin * 4, 14 * T);
    const ox = Math.floor((viewW - roomW) / 2 / T) * T;
    const oy = margin;
    const wallH = T * 2.5;
    const dividerX = ox + roomW * 0.55;

    // Store for hit testing / coordinate conversion
    this._roomOx = ox;
    this._roomOy = oy;
    this._roomW = roomW;
    this._roomH = roomH;
    this._wallH = wallH;
    this._dividerX = dividerX;

    // ── Floor ──
    g.rect(ox, oy + wallH, dividerX - ox, roomH - wallH);
    g.fill(theme.floorA);
    g.rect(dividerX, oy + wallH, ox + roomW - dividerX, roomH - wallH);
    g.fill(theme.floorB);

    // Floor board lines
    for (let r = 0; r < Math.ceil(roomH / T); r++) {
      const y = oy + wallH + r * T;
      if (y > oy + roomH) break;
      g.moveTo(ox, y);
      g.lineTo(ox + roomW, y);
      g.stroke({ width: 1, color: 0x7a6040, alpha: 0.35 });
    }

    // ── Back wall ──
    g.rect(ox, oy, roomW, wallH);
    g.fill(theme.wall);
    // Wainscoting
    g.rect(ox, oy + wallH - PX * 6, roomW, PX * 6);
    g.fill(theme.wainscot);
    g.moveTo(ox, oy + wallH - PX * 6);
    g.lineTo(ox + roomW, oy + wallH - PX * 6);
    g.stroke({ width: 2, color: 0x8b7355 });
    // Wall outline
    g.rect(ox, oy, roomW, wallH);
    g.stroke({ width: 3, color: 0x5c3a1e });

    // ── Room divider wall ──
    g.rect(dividerX - PX * 2, oy, PX * 4, roomH);
    g.fill(theme.wainscot);
    g.stroke({ width: 2, color: 0x5c3a1e });
    // Doorway in divider
    const innerDoorY = oy + wallH + T;
    const innerDoorH = T * 2.5;
    g.rect(dividerX - PX * 2, innerDoorY, PX * 4, innerDoorH);
    g.fill(theme.floorA);

    // ── Outer walls (left, right, bottom) ──
    g.rect(ox, oy, roomW, roomH);
    g.stroke({ width: 3, color: 0x5c3a1e });

    // ── Windows on back wall ──
    this.drawWindow(g, ox + T * 2, oy + PX * 8, T * 2, T * 1.5);
    this.drawWindow(g, dividerX + T * 2, oy + PX * 8, T * 2, T * 1.5);

    // ── Front entrance ──
    const doorW = T * 1.5;
    const doorX = ox + (dividerX - ox) / 2 - doorW / 2;
    const doorY = oy + roomH;
    g.rect(doorX, doorY - PX * 4, doorW, PX * 8);
    g.fill(theme.floorA);
    g.rect(doorX - PX * 4, doorY - PX * 6, PX * 4, PX * 10);
    g.fill(0x8b6914);
    g.rect(doorX + doorW, doorY - PX * 6, PX * 4, PX * 10);
    g.fill(0x8b6914);
    g.rect(doorX, doorY - PX * 2, doorW, PX * 2);
    g.fill(0x654321);

    // ── Draw placed furniture ──
    for (const f of room.furniture) {
      this.drawFurniturePiece(g, ox + f.x, oy + wallH + f.y, f.type, theme);
    }

    // Draw selection highlight
    this.drawSelection();
  }

  private drawWindow(g: Graphics, wx: number, wy: number, ww: number, wh: number): void {
    g.rect(wx - PX * 2, wy - PX * 2, ww + PX * 4, wh + PX * 4);
    g.fill(0x8b6914);
    g.rect(wx, wy, ww, wh);
    g.fill(0x87ceeb);
    g.moveTo(wx + ww / 2, wy);
    g.lineTo(wx + ww / 2, wy + wh);
    g.moveTo(wx, wy + wh / 2);
    g.lineTo(wx + ww, wy + wh / 2);
    g.stroke({ width: 2, color: 0x5c3a1e });
    g.rect(wx, wy, PX * 6, wh);
    g.fill({ color: 0xfaf0e6, alpha: 0.5 });
    g.rect(wx + ww - PX * 6, wy, PX * 6, wh);
    g.fill({ color: 0xfaf0e6, alpha: 0.5 });
    g.rect(wx - PX * 4, wy - PX * 4, ww + PX * 8, PX * 2);
    g.fill(0x8b6914);
  }

  /** Draw a single furniture piece using the extracted renderer functions. */
  private drawFurniturePiece(
    g: Graphics,
    x: number,
    y: number,
    type: string,
    theme: FurnitureTheme,
  ): void {
    switch (type) {
      case "sofa":
        drawSofa(g, x, y, theme);
        break;
      case "bed":
        drawBed(g, x, y, theme);
        break;
      case "desk":
        drawDesk(g, x, y, theme);
        break;
      case "bookshelf":
        drawBookshelf(g, x, y);
        break;
      case "coffee_table":
        drawCoffeeTable(g, x, y);
        break;
      case "wardrobe":
        drawWardrobe(g, x, y);
        break;
      case "nightstand":
        drawNightstand(g, x, y);
        break;
      case "fireplace":
        drawFireplace(g, x, y);
        break;
      case "chair":
        drawChair(g, x, y);
        break;
      case "rug":
        drawRug(g, x, y, theme.rug);
        break;
      case "wall_clock":
        // wall_clock uses center coordinates
        drawWallClock(g, x + PX * 8, y + PX * 8);
        break;
      case "picture_frame":
        drawPictureFrame(g, x, y, theme);
        break;
      case "mirror":
        drawMirror(g, x, y);
        break;
      case "bedroom_rug":
        // bedroom_rug uses center coordinates
        drawBedroomRug(g, x + T, y + T * 0.8, theme.bedroomRug);
        break;
      default:
        // Unknown type — draw a placeholder rectangle
        g.rect(x, y, T, T);
        g.fill({ color: 0xff00ff, alpha: 0.4 });
        g.stroke({ width: 1, color: 0xff00ff });
        break;
    }
  }

  /** Draw the selection highlight around the selected furniture piece. */
  private drawSelection(): void {
    const sg = this.selectionGfx;
    sg.clear();

    if (this._selectedIndex < 0) return;
    const room = this.currentRoom();
    if (this._selectedIndex >= room.furniture.length) return;

    const f = room.furniture[this._selectedIndex];
    const entry = catalogLookup(f.type);
    if (!entry) return;

    const fx = this._roomOx + f.x;
    const fy = this._roomOy + this._wallH + f.y;
    const pad = PX * 2;

    sg.rect(fx - pad, fy - pad, entry.widthPx + pad * 2, entry.heightPx + pad * 2);
    sg.stroke({ width: 2, color: 0xe94560, alpha: 0.8 });

    // Corner handles
    const hs = PX * 3;
    const corners = [
      [fx - pad, fy - pad],
      [fx + entry.widthPx + pad - hs, fy - pad],
      [fx - pad, fy + entry.heightPx + pad - hs],
      [fx + entry.widthPx + pad - hs, fy + entry.heightPx + pad - hs],
    ];
    for (const [cx, cy] of corners) {
      sg.rect(cx, cy, hs, hs);
      sg.fill({ color: 0xe94560, alpha: 0.9 });
    }
  }

  // ---------------------------------------------------------------------------
  // Status helper
  // ---------------------------------------------------------------------------

  private updateStatus(text: string): void {
    const el = document.getElementById("status-text");
    if (el) el.textContent = text;
  }
}
