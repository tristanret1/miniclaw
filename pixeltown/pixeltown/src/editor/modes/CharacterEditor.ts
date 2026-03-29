/**
 * Character Editor mode — configure agent-to-spritesheet mappings
 * with live animated sprite previews.
 */

import { Application, Assets, Container, Graphics, Sprite, Text, Texture, Rectangle } from "pixi.js";
import { SHEETS, DEFAULT_SHEET, AGENT_SPRITES } from "@/sprites/SpriteConfig";
import type { SpriteSheet } from "@/sprites/SpriteConfig";
import type { CharacterConfig } from "../types";
import type { CommandHistory, EditorCommand } from "../CommandHistory";

// ---------------------------------------------------------------------------
// Undo/Redo commands
// ---------------------------------------------------------------------------

class ChangeSheetCommand implements EditorCommand {
  readonly description: string;
  constructor(
    private editor: CharacterEditor,
    private agentId: string,
    private oldSheet: string,
    private newSheet: string,
  ) {
    this.description = `Change ${agentId} sheet: ${oldSheet} -> ${newSheet}`;
  }
  execute(): void {
    this.editor.applyAgentSheet(this.agentId, this.newSheet);
  }
  undo(): void {
    this.editor.applyAgentSheet(this.agentId, this.oldSheet);
  }
}

class AddAgentCommand implements EditorCommand {
  readonly description: string;
  constructor(
    private editor: CharacterEditor,
    private agentId: string,
    private sheet: string,
  ) {
    this.description = `Add agent: ${agentId}`;
  }
  execute(): void {
    this.editor.applyAddAgent(this.agentId, this.sheet);
  }
  undo(): void {
    this.editor.applyRemoveAgent(this.agentId);
  }
}

class RemoveAgentCommand implements EditorCommand {
  readonly description: string;
  constructor(
    private editor: CharacterEditor,
    private agentId: string,
    private sheet: string,
  ) {
    this.description = `Remove agent: ${agentId}`;
  }
  execute(): void {
    this.editor.applyRemoveAgent(this.agentId);
  }
  undo(): void {
    this.editor.applyAddAgent(this.agentId, this.sheet);
  }
}

class ChangeDefaultSheetCommand implements EditorCommand {
  readonly description: string;
  constructor(
    private editor: CharacterEditor,
    private oldSheet: string,
    private newSheet: string,
  ) {
    this.description = `Change default sheet: ${oldSheet} -> ${newSheet}`;
  }
  execute(): void {
    this.editor.applyDefaultSheet(this.newSheet);
  }
  undo(): void {
    this.editor.applyDefaultSheet(this.oldSheet);
  }
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface AgentEntry {
  id: string;
  sheet: string;
}

interface PreviewState {
  container: Container;
  sprite: Sprite;
  label: Text;
  bg: Graphics;
  textures: Texture[];
  ready: boolean;
  animFrame: number;
  animTimer: number;
}

// ---------------------------------------------------------------------------
// Texture cache (module-level, survives attach/detach)
// ---------------------------------------------------------------------------

const textureCache = new Map<string, Promise<Texture[]>>();

async function loadSheetTextures(sheetConfig: SpriteSheet): Promise<Texture[]> {
  const existing = textureCache.get(sheetConfig.path);
  if (existing) return existing;

  const promise = (async () => {
    const source = await Assets.load<Texture>(sheetConfig.path);
    const baseSource = source.source;
    const textures: Texture[] = [];
    for (let i = 0; i < sheetConfig.frameCount; i++) {
      const frame = new Rectangle(
        i * sheetConfig.frameSize,
        0,
        sheetConfig.frameSize,
        sheetConfig.frameSize,
      );
      textures.push(new Texture({ source: baseSource, frame }));
    }
    return textures;
  })();

  textureCache.set(sheetConfig.path, promise);
  return promise;
}

// ---------------------------------------------------------------------------
// CharacterEditor
// ---------------------------------------------------------------------------

const SHEET_KEYS = Object.keys(SHEETS);
const PREVIEW_SIZE = 64;
const ANIM_SPEED = 200; // ms per frame

export class CharacterEditor {
  private agents: AgentEntry[] = [];
  private _defaultSheet: string = DEFAULT_SHEET;

  private sidebarEl: HTMLElement | null = null;
  private propertiesEl: HTMLElement | null = null;
  private listEl: HTMLElement | null = null;
  private commandHistory: CommandHistory | null = null;

  /** PixiJS application used solely for sprite preview rendering. */
  private previewApp: Application | null = null;
  private previewCanvas: HTMLCanvasElement | null = null;
  private canvasContainer: HTMLElement | null = null;
  private previews = new Map<string, PreviewState>();
  private tickerBound: (() => void) | null = null;
  private attached = false;

  /** Saved sidebar / properties HTML so we can restore on detach. */
  private savedSidebarHTML = "";
  private savedPropertiesHTML = "";

  constructor() {
    // Seed from AGENT_SPRITES defaults.
    for (const [id, sheet] of Object.entries(AGENT_SPRITES)) {
      this.agents.push({ id, sheet });
    }
  }

  // -----------------------------------------------------------------------
  // Attach / Detach lifecycle
  // -----------------------------------------------------------------------

  async attach(
    sidebarEl: HTMLElement,
    propertiesEl: HTMLElement,
    canvasContainer: HTMLElement,
    commandHistory: CommandHistory,
    _parentApp: Application,
  ): Promise<void> {
    if (this.attached) return;
    this.attached = true;
    this.commandHistory = commandHistory;
    this.sidebarEl = sidebarEl;
    this.propertiesEl = propertiesEl;
    this.canvasContainer = canvasContainer;

    // Save existing panel content so we can restore on detach.
    this.savedSidebarHTML = sidebarEl.innerHTML;
    this.savedPropertiesHTML = propertiesEl.innerHTML;

    // Hide the main editor canvas (the town map one) while character tab is active.
    const mainCanvas = canvasContainer.querySelector("canvas");
    if (mainCanvas) mainCanvas.style.display = "none";

    // Create a dedicated PixiJS Application for sprite previews.
    this.previewCanvas = document.createElement("canvas");
    this.previewCanvas.style.cssText =
      "position:absolute;top:0;left:0;width:100%;height:100%;image-rendering:pixelated;";
    canvasContainer.appendChild(this.previewCanvas);

    this.previewApp = new Application();
    await this.previewApp.init({
      canvas: this.previewCanvas,
      width: canvasContainer.clientWidth || 800,
      height: canvasContainer.clientHeight || 600,
      backgroundColor: 0x1a1a2e,
      antialias: false,
      resolution: window.devicePixelRatio || 1,
      autoDensity: true,
    });

    // Animation ticker.
    this.tickerBound = () => this.tick();
    this.previewApp.ticker.add(this.tickerBound);

    // Build HTML panels.
    this.buildSidebar(sidebarEl);
    this.buildProperties(propertiesEl);

    // Build PixiJS previews.
    await this.rebuildAllPreviews();
  }

  detach(): void {
    if (!this.attached) return;
    this.attached = false;

    // Destroy all preview containers.
    for (const pv of this.previews.values()) {
      pv.container.destroy({ children: true });
    }
    this.previews.clear();

    // Destroy preview app.
    if (this.previewApp) {
      if (this.tickerBound) {
        this.previewApp.ticker.remove(this.tickerBound);
      }
      this.previewApp.destroy(true, { children: true });
      this.previewApp = null;
    }

    // Remove preview canvas.
    if (this.previewCanvas?.parentElement) {
      this.previewCanvas.parentElement.removeChild(this.previewCanvas);
    }
    this.previewCanvas = null;

    // Restore the main editor canvas.
    if (this.canvasContainer) {
      const mainCanvas = this.canvasContainer.querySelector("canvas");
      if (mainCanvas) mainCanvas.style.display = "";
    }

    // Restore panel HTML.
    if (this.sidebarEl) this.sidebarEl.innerHTML = this.savedSidebarHTML;
    if (this.propertiesEl) this.propertiesEl.innerHTML = this.savedPropertiesHTML;

    this.sidebarEl = null;
    this.propertiesEl = null;
    this.canvasContainer = null;
    this.listEl = null;
    this.commandHistory = null;
  }

  // -----------------------------------------------------------------------
  // Config I/O
  // -----------------------------------------------------------------------

  getConfig(): CharacterConfig {
    const agents: CharacterConfig["agents"] = {};
    for (const entry of this.agents) {
      agents[entry.id] = { sheet: entry.sheet };
    }
    return { agents, defaultSheet: this._defaultSheet };
  }

  loadConfig(config: CharacterConfig): void {
    this.agents = [];
    for (const [id, def] of Object.entries(config.agents)) {
      this.agents.push({ id, sheet: def.sheet });
    }
    this._defaultSheet = config.defaultSheet || DEFAULT_SHEET;

    if (this.attached) {
      this.refreshList();
      this.refreshDefaultDropdown();
      void this.rebuildAllPreviews();
    }
  }

  // -----------------------------------------------------------------------
  // Apply methods — called by commands (no recording, just mutate + refresh)
  // -----------------------------------------------------------------------

  /** @internal Apply a sheet change for undo/redo. */
  applyAgentSheet(agentId: string, sheet: string): void {
    const entry = this.agents.find((a) => a.id === agentId);
    if (!entry) return;
    entry.sheet = sheet;
    if (this.attached) {
      this.refreshList();
      void this.updatePreviewSheet(agentId);
    }
  }

  /** @internal Apply an agent addition for undo/redo. */
  applyAddAgent(agentId: string, sheet: string): void {
    if (this.agents.some((a) => a.id === agentId)) return;
    this.agents.push({ id: agentId, sheet });
    if (this.attached) {
      this.refreshList();
      void this.rebuildAllPreviews();
    }
  }

  /** @internal Apply an agent removal for undo/redo. */
  applyRemoveAgent(agentId: string): void {
    const idx = this.agents.findIndex((a) => a.id === agentId);
    if (idx < 0) return;
    this.agents.splice(idx, 1);
    const pv = this.previews.get(agentId);
    if (pv) {
      pv.container.destroy({ children: true });
      this.previews.delete(agentId);
    }
    if (this.attached) {
      this.refreshList();
      this.layoutPreviews();
    }
  }

  /** @internal Apply a default sheet change for undo/redo. */
  applyDefaultSheet(sheet: string): void {
    this._defaultSheet = sheet;
    if (this.attached) {
      this.refreshDefaultDropdown();
    }
  }

  // -----------------------------------------------------------------------
  // HTML UI — Sidebar (agent list)
  // -----------------------------------------------------------------------

  private buildSidebar(el: HTMLElement): void {
    el.innerHTML = "";

    const header = document.createElement("h3");
    header.textContent = "Characters";
    el.appendChild(header);

    this.listEl = document.createElement("div");
    this.listEl.style.cssText = "padding:8px;overflow-y:auto;flex:1;";
    el.appendChild(this.listEl);

    const addBtn = document.createElement("button");
    addBtn.textContent = "+ Add Agent";
    addBtn.style.cssText =
      "margin:8px;padding:6px 12px;background:#0f3460;color:#e0e0e0;" +
      "border:1px solid #1a1a4e;border-radius:3px;cursor:pointer;font-size:12px;" +
      "width:calc(100% - 16px);";
    addBtn.addEventListener("click", () => this.onAddAgent());
    el.appendChild(addBtn);

    this.refreshList();
  }

  private refreshList(): void {
    if (!this.listEl) return;
    this.listEl.innerHTML = "";

    for (const entry of this.agents) {
      const row = document.createElement("div");
      row.style.cssText =
        "display:flex;align-items:center;gap:4px;margin-bottom:6px;" +
        "padding:4px;background:#1a1a2e;border-radius:3px;";

      // Agent ID input.
      const idInput = document.createElement("input");
      idInput.type = "text";
      idInput.value = entry.id;
      idInput.style.cssText =
        "width:70px;background:#0d0d1a;color:#e0e0e0;border:1px solid #0f3460;" +
        "padding:2px 4px;border-radius:2px;font-size:11px;";
      idInput.addEventListener("change", () => {
        const newId = idInput.value.trim();
        if (!newId || newId === entry.id || this.agents.some((a) => a.id === newId)) {
          idInput.value = entry.id;
          return;
        }
        const oldId = entry.id;
        entry.id = newId;
        // Move preview under new key.
        const pv = this.previews.get(oldId);
        if (pv) {
          this.previews.delete(oldId);
          this.previews.set(newId, pv);
          pv.label.text = newId;
        }
      });
      row.appendChild(idInput);

      // Sheet dropdown.
      const sheetSelect = document.createElement("select");
      sheetSelect.style.cssText =
        "flex:1;background:#0d0d1a;color:#e0e0e0;border:1px solid #0f3460;" +
        "padding:2px 4px;border-radius:2px;font-size:11px;";
      for (const key of SHEET_KEYS) {
        const opt = document.createElement("option");
        opt.value = key;
        opt.textContent = key;
        if (key === entry.sheet) opt.selected = true;
        sheetSelect.appendChild(opt);
      }
      sheetSelect.addEventListener("change", () => {
        const oldSheet = entry.sheet;
        const newSheet = sheetSelect.value;
        if (oldSheet === newSheet) return;
        this.commandHistory?.execute(
          new ChangeSheetCommand(this, entry.id, oldSheet, newSheet),
        );
      });
      row.appendChild(sheetSelect);

      // Remove button.
      const removeBtn = document.createElement("button");
      removeBtn.textContent = "X";
      removeBtn.title = "Remove agent";
      removeBtn.style.cssText =
        "background:#e94560;color:#fff;border:none;border-radius:2px;" +
        "cursor:pointer;padding:2px 6px;font-size:11px;font-weight:bold;";
      removeBtn.addEventListener("click", () => {
        this.commandHistory?.execute(
          new RemoveAgentCommand(this, entry.id, entry.sheet),
        );
      });
      row.appendChild(removeBtn);

      this.listEl.appendChild(row);
    }
  }

  // -----------------------------------------------------------------------
  // HTML UI — Properties (default sheet)
  // -----------------------------------------------------------------------

  private buildProperties(el: HTMLElement): void {
    el.innerHTML = "";

    const header = document.createElement("h3");
    header.textContent = "Defaults";
    el.appendChild(header);

    const row = document.createElement("div");
    row.className = "prop-row";

    const label = document.createElement("label");
    label.textContent = "Default Sheet";
    row.appendChild(label);

    const select = document.createElement("select");
    select.id = "char-default-sheet";
    for (const key of SHEET_KEYS) {
      const opt = document.createElement("option");
      opt.value = key;
      opt.textContent = key;
      if (key === this._defaultSheet) opt.selected = true;
      select.appendChild(opt);
    }
    select.addEventListener("change", () => {
      const oldVal = this._defaultSheet;
      const newVal = select.value;
      if (oldVal === newVal) return;
      this.commandHistory?.execute(
        new ChangeDefaultSheetCommand(this, oldVal, newVal),
      );
    });
    row.appendChild(select);
    el.appendChild(row);

    const info = document.createElement("p");
    info.style.cssText = "color:#666;font-size:11px;margin-top:12px;padding:0 2px;";
    info.textContent = "Agents not listed use the default sheet.";
    el.appendChild(info);
  }

  private refreshDefaultDropdown(): void {
    const select = document.getElementById("char-default-sheet") as HTMLSelectElement | null;
    if (select) select.value = this._defaultSheet;
  }

  // -----------------------------------------------------------------------
  // Add agent
  // -----------------------------------------------------------------------

  private onAddAgent(): void {
    let idx = this.agents.length + 1;
    let newId = `agent_${idx}`;
    while (this.agents.some((a) => a.id === newId)) {
      idx++;
      newId = `agent_${idx}`;
    }
    this.commandHistory?.execute(
      new AddAgentCommand(this, newId, this._defaultSheet),
    );
  }

  // -----------------------------------------------------------------------
  // PixiJS sprite previews
  // -----------------------------------------------------------------------

  private async createPreview(entry: AgentEntry): Promise<PreviewState> {
    const sheetConfig = SHEETS[entry.sheet] ?? SHEETS[DEFAULT_SHEET];
    const container = new Container();

    // Dark card background.
    const bg = new Graphics();
    bg.roundRect(-4, -4, PREVIEW_SIZE + 8, PREVIEW_SIZE + 24, 4);
    bg.fill({ color: 0x16213e, alpha: 0.9 });
    bg.roundRect(-4, -4, PREVIEW_SIZE + 8, PREVIEW_SIZE + 24, 4);
    bg.stroke({ width: 1, color: 0x0f3460, alpha: 0.8 });
    container.addChild(bg);

    // Sprite.
    const sprite = new Sprite();
    sprite.width = PREVIEW_SIZE;
    sprite.height = PREVIEW_SIZE;
    container.addChild(sprite);

    // Label.
    const label = new Text({
      text: entry.id,
      style: {
        fontFamily: '"Press Start 2P", monospace',
        fontSize: 7,
        fill: 0xe0e0e0,
        align: "center",
      },
    });
    label.anchor.set(0.5, 0);
    label.x = PREVIEW_SIZE / 2;
    label.y = PREVIEW_SIZE + 4;
    container.addChild(label);

    const state: PreviewState = {
      container,
      sprite,
      label,
      bg,
      textures: [],
      ready: false,
      animFrame: 0,
      animTimer: 0,
    };

    try {
      state.textures = await loadSheetTextures(sheetConfig);
      state.ready = true;
      const walkDown = sheetConfig.anims.walk_down;
      if (walkDown.length > 0 && state.textures[walkDown[0]]) {
        sprite.texture = state.textures[walkDown[0]];
      }
    } catch (err) {
      console.warn(`Failed to load sheet for ${entry.id}:`, err);
    }

    return state;
  }

  private async updatePreviewSheet(agentId: string): Promise<void> {
    const entry = this.agents.find((a) => a.id === agentId);
    if (!entry) return;

    const pv = this.previews.get(agentId);
    if (!pv) return;

    const sheetConfig = SHEETS[entry.sheet] ?? SHEETS[DEFAULT_SHEET];
    try {
      pv.textures = await loadSheetTextures(sheetConfig);
      pv.ready = true;
      pv.animFrame = 0;
      pv.animTimer = 0;
      const walkDown = sheetConfig.anims.walk_down;
      if (walkDown.length > 0 && pv.textures[walkDown[0]]) {
        pv.sprite.texture = pv.textures[walkDown[0]];
      }
    } catch (err) {
      console.warn(`Failed to reload sheet for ${agentId}:`, err);
    }
  }

  private async rebuildAllPreviews(): Promise<void> {
    if (!this.previewApp) return;

    // Destroy existing.
    for (const pv of this.previews.values()) {
      pv.container.destroy({ children: true });
    }
    this.previews.clear();

    // Create new.
    for (const entry of this.agents) {
      const pv = await this.createPreview(entry);
      this.previews.set(entry.id, pv);
      this.previewApp.stage.addChild(pv.container);
    }

    this.layoutPreviews();
  }

  private layoutPreviews(): void {
    const padding = 24;
    const gap = 24;
    const cardW = PREVIEW_SIZE + 8;
    const cardH = PREVIEW_SIZE + 28;
    const colWidth = cardW + gap;
    const rowHeight = cardH + gap;

    const width = this.previewApp?.screen.width ?? 800;
    const cols = Math.max(1, Math.floor((width - padding * 2 + gap) / colWidth));

    let i = 0;
    for (const [, pv] of this.previews) {
      const col = i % cols;
      const row = Math.floor(i / cols);
      pv.container.x = padding + col * colWidth;
      pv.container.y = padding + row * rowHeight;
      i++;
    }
  }

  private tick(): void {
    const dt = this.previewApp?.ticker.deltaMS ?? 16;

    for (const [agentId, pv] of this.previews) {
      if (!pv.ready) continue;

      const entry = this.agents.find((a) => a.id === agentId);
      if (!entry) continue;

      const sheetConfig = SHEETS[entry.sheet] ?? SHEETS[DEFAULT_SHEET];
      const walkDown = sheetConfig.anims.walk_down;
      if (walkDown.length <= 1) continue;

      pv.animTimer += dt;
      if (pv.animTimer >= ANIM_SPEED) {
        pv.animTimer -= ANIM_SPEED;
        pv.animFrame = (pv.animFrame + 1) % walkDown.length;
        const frameIdx = walkDown[pv.animFrame];
        if (pv.textures[frameIdx]) {
          pv.sprite.texture = pv.textures[frameIdx];
        }
      }
    }
  }
}
