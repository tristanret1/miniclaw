/**
 * Editor entry point.
 * Creates the PixiJS application, wires toolbar buttons and keyboard shortcuts.
 */

import { Application } from "pixi.js";
import { MAP_COLS, MAP_ROWS, SCALED_TILE } from "@/config";
import { EditorApp, EditorMode } from "./EditorApp";
import { TilePalette } from "./ui/TilePalette";
import { EditorToolbar } from "./ui/EditorToolbar";

async function boot(): Promise<void> {
  const canvas = document.getElementById("editor-canvas") as HTMLCanvasElement;
  if (!canvas) throw new Error("#editor-canvas not found");

  const app = new Application();
  await app.init({
    canvas,
    width: MAP_COLS * SCALED_TILE,
    height: MAP_ROWS * SCALED_TILE,
    backgroundColor: 0x1a1a2e,
    antialias: false,
    autoDensity: true,
    resolution: window.devicePixelRatio || 1,
  });

  const editor = new EditorApp(app);

  // ------------------------------------------------------------------
  // Tile Palette (sidebar)
  // ------------------------------------------------------------------
  const paletteContainer = document.getElementById("palette-grid");
  if (!paletteContainer) throw new Error("#palette-grid not found");
  const tilePalette = new TilePalette(paletteContainer);

  tilePalette.onSelect = (category: string, itemId: string) => {
    editor.townMapEditor.setSelectedItem(category, itemId);
    // Sync toolbar highlight to match auto-tool-switch.
    editorToolbar.syncTool(editor.townMapEditor.getTool());
  };

  // ------------------------------------------------------------------
  // Editor Toolbar (tool buttons)
  // ------------------------------------------------------------------
  const editorToolbar = new EditorToolbar();

  editorToolbar.onToolChange = (tool) => {
    editor.townMapEditor.setTool(tool);
  };

  // ------------------------------------------------------------------
  // Canvas mouse interaction → grid hover
  // ------------------------------------------------------------------
  canvas.addEventListener("pointermove", (e: PointerEvent) => {
    const rect = canvas.getBoundingClientRect();
    const scaleX = app.screen.width / rect.width;
    const scaleY = app.screen.height / rect.height;
    const px = (e.clientX - rect.left) * scaleX;
    const py = (e.clientY - rect.top) * scaleY;
    const { col, row } = editor.grid.pixelToTile(px, py);
    editor.grid.setHover(col, row);
  });

  canvas.addEventListener("pointerleave", () => {
    editor.grid.setHover(-1, -1);
  });

  // ------------------------------------------------------------------
  // Toolbar buttons
  // ------------------------------------------------------------------
  const btnUndo = document.getElementById("btn-undo");
  const btnRedo = document.getElementById("btn-redo");
  const btnGrid = document.getElementById("btn-grid");
  const btnSave = document.getElementById("btn-save");
  const btnLoad = document.getElementById("btn-load");
  const fileInput = document.getElementById("file-input") as HTMLInputElement;

  btnUndo?.addEventListener("click", () => editor.history.undo());
  btnRedo?.addEventListener("click", () => editor.history.redo());

  btnGrid?.addEventListener("click", () => {
    editor.grid.toggleVisibility();
    btnGrid.classList.toggle("active", editor.grid.visible);
  });

  btnSave?.addEventListener("click", () => editor.save());

  btnLoad?.addEventListener("click", () => fileInput?.click());
  fileInput?.addEventListener("change", () => {
    const file = fileInput.files?.[0];
    if (file) {
      editor.load(file);
      fileInput.value = "";
    }
  });

  // Tab buttons
  const tabBtns = document.querySelectorAll<HTMLButtonElement>(".tab-btn");
  tabBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      const tab = btn.dataset.tab as EditorMode | undefined;
      if (!tab) return;
      editor.setMode(tab);
      tabBtns.forEach((b) => b.classList.toggle("active", b === btn));
    });
  });

  // Update undo/redo button states on history change.
  const existingOnChange = editor.history.onChange;
  editor.history.onChange = () => {
    existingOnChange?.();
    if (btnUndo) btnUndo.style.opacity = editor.history.canUndo() ? "1" : "0.4";
    if (btnRedo) btnRedo.style.opacity = editor.history.canRedo() ? "1" : "0.4";
  };
  // Set initial state.
  if (btnUndo) btnUndo.style.opacity = "0.4";
  if (btnRedo) btnRedo.style.opacity = "0.4";

  // ------------------------------------------------------------------
  // Keyboard shortcuts
  // ------------------------------------------------------------------
  window.addEventListener("keydown", (e: KeyboardEvent) => {
    // Ignore when typing in an input field.
    const tag = (e.target as HTMLElement).tagName;
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;

    const ctrl = e.ctrlKey || e.metaKey;

    if (ctrl && e.shiftKey && e.key.toLowerCase() === "z") {
      e.preventDefault();
      editor.history.redo();
    } else if (ctrl && e.key.toLowerCase() === "z") {
      e.preventDefault();
      editor.history.undo();
    } else if (e.key.toLowerCase() === "g" && !ctrl && !e.shiftKey && !e.altKey) {
      editor.grid.toggleVisibility();
      btnGrid?.classList.toggle("active", editor.grid.visible);
    } else if (e.key.toLowerCase() === "b" && !ctrl && !e.shiftKey && !e.altKey) {
      editorToolbar.setActiveTool("paint");
      editor.townMapEditor.setTool("paint");
    } else if (e.key.toLowerCase() === "p" && !ctrl && !e.shiftKey && !e.altKey) {
      editorToolbar.setActiveTool("place");
      editor.townMapEditor.setTool("place");
    } else if (e.key.toLowerCase() === "e" && !ctrl && !e.shiftKey && !e.altKey) {
      editorToolbar.setActiveTool("erase");
      editor.townMapEditor.setTool("erase");
    }
  });

  // ------------------------------------------------------------------
  // Ready
  // ------------------------------------------------------------------
  const status = document.getElementById("status-text");
  if (status) status.textContent = "Editor ready";
}

boot().catch((err) => {
  console.error("Editor failed to boot:", err);
});
