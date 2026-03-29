/** A* pathfinding on a tile-based collision grid. */

interface Point {
  x: number;
  y: number;
}

interface Node {
  x: number;
  y: number;
  g: number;
  h: number;
  f: number;
  parent: Node | null;
}

/**
 * A* pathfinder operating on a 2D collision grid.
 * Grid values: 0 = walkable, 1 = blocked.
 */
export class Pathfinding {
  private grid: number[][];
  private cols: number;
  private rows: number;

  constructor(grid: number[][]) {
    this.grid = grid;
    this.rows = grid.length;
    this.cols = grid[0]?.length ?? 0;
  }

  /** Update the collision grid (e.g. after layout changes). */
  setGrid(grid: number[][]): void {
    this.grid = grid;
    this.rows = grid.length;
    this.cols = grid[0]?.length ?? 0;
  }

  /** Find path from start to end. Returns array of tile coordinates, or empty if no path. */
  findPath(start: Point, end: Point): Point[] {
    if (!this.isWalkable(end.x, end.y)) return [];
    if (start.x === end.x && start.y === end.y) return [start];

    const open: Node[] = [];
    const closed = new Set<string>();

    const startNode: Node = {
      x: start.x,
      y: start.y,
      g: 0,
      h: this.heuristic(start, end),
      f: 0,
      parent: null,
    };
    startNode.f = startNode.g + startNode.h;
    open.push(startNode);

    while (open.length > 0) {
      // Find node with lowest f
      let lowestIdx = 0;
      for (let i = 1; i < open.length; i++) {
        if (open[i].f < open[lowestIdx].f) lowestIdx = i;
      }
      const current = open.splice(lowestIdx, 1)[0];
      const key = `${current.x},${current.y}`;

      if (current.x === end.x && current.y === end.y) {
        return this.reconstructPath(current);
      }

      closed.add(key);

      for (const [dx, dy] of [[0, -1], [1, 0], [0, 1], [-1, 0]] as const) {
        const nx = current.x + dx;
        const ny = current.y + dy;
        const nkey = `${nx},${ny}`;

        if (!this.isWalkable(nx, ny) || closed.has(nkey)) continue;

        const g = current.g + 1;
        const existing = open.find((n) => n.x === nx && n.y === ny);

        if (!existing) {
          const h = this.heuristic({ x: nx, y: ny }, end);
          open.push({ x: nx, y: ny, g, h, f: g + h, parent: current });
        } else if (g < existing.g) {
          existing.g = g;
          existing.f = g + existing.h;
          existing.parent = current;
        }
      }
    }

    return []; // no path found
  }

  private isWalkable(x: number, y: number): boolean {
    return x >= 0 && y >= 0 && x < this.cols && y < this.rows && this.grid[y][x] === 0;
  }

  private heuristic(a: Point, b: Point): number {
    return Math.abs(a.x - b.x) + Math.abs(a.y - b.y); // Manhattan distance
  }

  private reconstructPath(node: Node): Point[] {
    const path: Point[] = [];
    let current: Node | null = node;
    while (current) {
      path.unshift({ x: current.x, y: current.y });
      current = current.parent;
    }
    return path;
  }
}
