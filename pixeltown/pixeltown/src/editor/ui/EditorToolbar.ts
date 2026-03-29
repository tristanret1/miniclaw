/**
 * Editor toolbar with tool selection buttons.
 * Integrates with the existing toolbar HTML in editor/index.html.
 */

import type { TownTool } from "../modes/TownMapEditor";

export type ToolChangeCallback = (tool: TownTool) => void;

interface ToolDef {
  id: TownTool;
  label: string;
  icon: string;
  title: string;
}

const TOOLS: ToolDef[] = [
  { id: "paint", label: "Paint", icon: "\u{1F58C}", title: "Paint Brush (B)" },
  { id: "place", label: "Place", icon: "\u{1F4CD}", title: "Place Item (P)" },
  { id: "erase", label: "Erase", icon: "\u{1F9F9}", title: "Eraser (E)" },
];

export class EditorToolbar {
  private container: HTMLElement;
  private buttons: Map<TownTool, HTMLButtonElement> = new Map();
  private _activeTool: TownTool = "paint";
  private _onToolChange: ToolChangeCallback | null = null;

  constructor() {
    // Create a toolbar group and insert it into #toolbar.
    this.container = document.createElement("div");
    this.container.className = "toolbar-group";
    this.container.id = "tool-buttons";

    for (const tool of TOOLS) {
      const btn = document.createElement("button");
      btn.textContent = `${tool.icon} ${tool.label}`;
      btn.title = tool.title;
      btn.dataset.tool = tool.id;

      // Match existing toolbar button styling.
      btn.style.cssText =
        "background:#0f3460;color:#e0e0e0;border:1px solid #1a1a4e;" +
        "padding:4px 10px;border-radius:3px;cursor:pointer;font-size:12px;";

      btn.addEventListener("click", () => this.setActiveTool(tool.id));
      this.container.appendChild(btn);
      this.buttons.set(tool.id, btn);
    }

    // Insert into toolbar after the tab buttons group.
    const toolbar = document.getElementById("toolbar");
    if (toolbar) {
      // Find the first toolbar-group (tabs) and insert after it.
      const groups = toolbar.querySelectorAll(".toolbar-group");
      if (groups.length > 0) {
        const firstGroup = groups[0];
        firstGroup.after(this.container);
      } else {
        toolbar.prepend(this.container);
      }
    }

    this.highlightActive();
  }

  set onToolChange(cb: ToolChangeCallback | null) {
    this._onToolChange = cb;
  }

  get activeTool(): TownTool {
    return this._activeTool;
  }

  setActiveTool(tool: TownTool): void {
    if (tool === this._activeTool) return;
    this._activeTool = tool;
    this.highlightActive();
    this._onToolChange?.(tool);
  }

  /** Update highlight to match external tool changes (e.g. from palette selection). */
  syncTool(tool: TownTool): void {
    this._activeTool = tool;
    this.highlightActive();
  }

  private highlightActive(): void {
    for (const [id, btn] of this.buttons) {
      if (id === this._activeTool) {
        btn.style.background = "#e94560";
        btn.style.borderColor = "#e94560";
      } else {
        btn.style.background = "#0f3460";
        btn.style.borderColor = "#1a1a4e";
      }
    }
  }
}
