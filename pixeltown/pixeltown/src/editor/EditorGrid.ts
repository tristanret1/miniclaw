/**
 * Grid overlay and tile-based mouse interaction for the editor canvas.
 * Draws semi-transparent grid lines and highlights the hovered tile.
 */

import { Container, Graphics } from "pixi.js";
import { SCALED_TILE, MAP_COLS, MAP_ROWS } from "@/config";

export class EditorGrid {
  readonly container: Container;

  private gridLines: Graphics;
  private hoverHighlight: Graphics;
  private _visible = true;
  private _hoverCol = -1;
  private _hoverRow = -1;

  constructor() {
    this.container = new Container();
    this.container.label = "EditorGrid";

    this.gridLines = new Graphics();
    this.gridLines.label = "GridLines";
    this.container.addChild(this.gridLines);

    this.hoverHighlight = new Graphics();
    this.hoverHighlight.label = "HoverHighlight";
    this.container.addChild(this.hoverHighlight);

    this.drawGrid();
  }

  /** Convert a pixel position (relative to the grid container) to tile coordinates. */
  pixelToTile(px: number, py: number): { col: number; row: number } {
    const col = Math.floor(px / SCALED_TILE);
    const row = Math.floor(py / SCALED_TILE);
    return {
      col: Math.max(0, Math.min(col, MAP_COLS - 1)),
      row: Math.max(0, Math.min(row, MAP_ROWS - 1)),
    };
  }

  /** Update the hover highlight to the given tile. Pass -1 to hide. */
  setHover(col: number, row: number): void {
    if (col === this._hoverCol && row === this._hoverRow) return;
    this._hoverCol = col;
    this._hoverRow = row;
    this.drawHover();
  }

  /** Toggle grid line visibility. */
  toggleVisibility(): void {
    this._visible = !this._visible;
    this.gridLines.visible = this._visible;
  }

  get visible(): boolean {
    return this._visible;
  }

  set visible(v: boolean) {
    this._visible = v;
    this.gridLines.visible = v;
  }

  // -----------------------------------------------------------------------
  // Drawing
  // -----------------------------------------------------------------------

  private drawGrid(): void {
    const g = this.gridLines;
    g.clear();

    const totalW = MAP_COLS * SCALED_TILE;
    const totalH = MAP_ROWS * SCALED_TILE;

    g.setStrokeStyle({ width: 1, color: 0xffffff, alpha: 0.12 });

    // Vertical lines
    for (let c = 0; c <= MAP_COLS; c++) {
      const x = c * SCALED_TILE;
      g.moveTo(x, 0);
      g.lineTo(x, totalH);
    }

    // Horizontal lines
    for (let r = 0; r <= MAP_ROWS; r++) {
      const y = r * SCALED_TILE;
      g.moveTo(0, y);
      g.lineTo(totalW, y);
    }

    g.stroke();
  }

  private drawHover(): void {
    const g = this.hoverHighlight;
    g.clear();

    if (this._hoverCol < 0 || this._hoverRow < 0) return;

    const x = this._hoverCol * SCALED_TILE;
    const y = this._hoverRow * SCALED_TILE;

    g.rect(x, y, SCALED_TILE, SCALED_TILE);
    g.fill({ color: 0xffffff, alpha: 0.15 });
    g.rect(x, y, SCALED_TILE, SCALED_TILE);
    g.stroke({ width: 1, color: 0xe94560, alpha: 0.6 });
  }
}
