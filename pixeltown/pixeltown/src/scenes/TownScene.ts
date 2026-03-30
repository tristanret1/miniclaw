import { Container, Graphics, type Renderer } from "pixi.js";
import { SCALED_TILE, MAP_COLS, MAP_ROWS } from "@/config";
import { Agent } from "@/entities/Agent";
import { Building, type BuildingType } from "@/entities/Building";
import { Pathfinding } from "@/systems/Pathfinding";
import { DayNightSystem } from "@/systems/DayNight";
import { WeatherSystem } from "@/systems/Weather";
import { SeasonSystem } from "@/systems/Season";
import { IdleBehaviorSystem } from "@/systems/IdleBehavior";
import { SocialAISystem } from "@/systems/SocialAI";
import type { AgentInfo, BuildingLayout, CronJob, ServerMessage } from "@/net/Protocol";
import { getTownMapConfig } from "@/ConfigLoader";
import type { TownMapConfig, BuildingDef, DecorationDef } from "@/editor/types";
import { LayerCache } from "@/renderer/LayerCache";
import { loadTiledMap } from "@/map/TilemapLoader";
import { renderTiledToContainers } from "@/map/TileRenderer";

/**
 * Main town scene — renders the tile map, buildings, and agents.
 * Manages all game systems (day/night, weather, season, pathfinding).
 */
export class TownScene {
  readonly container: Container;

  // layers (render order)
  private groundLayer: Container;
  private buildingLayer: Container;
  private agentLayer: Container;
  private effectLayer: Container;

  // entities
  private agents = new Map<string, Agent>();
  private buildings = new Map<string, Building>();

  // systems
  private pathfinding: Pathfinding;
  private dayNight: DayNightSystem;
  private weather: WeatherSystem;
  private season: SeasonSystem;
  private idleBehavior: IdleBehaviorSystem | null = null;
  private socialAI!: SocialAISystem;

  // collision grid (0 = walkable, 1 = blocked)
  private collisionGrid: number[][];
  private collisionTerrain!: number[][];
  private collisionBuildings!: number[][];
  private collisionWater!: number[][];
  private collisionInteract!: number[][];

  // cron jobs cache
  private cronJobs: CronJob[] = [];

  // timing
  private lastFrameTime = performance.now();

  // callbacks
  private onCottageClick: ((agentId: string) => void) | null = null;
  private onPlazaClick: (() => void) | null = null;
  private onSubtitle: ((agentName: string, text: string) => void) | null = null;

  private layerCache: LayerCache | null = null;

  constructor(renderer?: Renderer) {
    this.container = new Container();

    this.groundLayer = new Container();
    this.buildingLayer = new Container();
    this.agentLayer = new Container();
    this.effectLayer = new Container();

    this.container.addChild(this.groundLayer);
    this.container.addChild(this.buildingLayer);
    this.container.addChild(this.agentLayer);
    this.container.addChild(this.effectLayer);

    // Depth sorting for agents (y-based painter's algorithm)
    this.agentLayer.sortableChildren = true;

    // Initialize collision grids (all walkable)
    this.collisionTerrain = Array.from({ length: MAP_ROWS }, () => Array.from({ length: MAP_COLS }, () => 0));
    this.collisionBuildings = Array.from({ length: MAP_ROWS }, () => Array.from({ length: MAP_COLS }, () => 0));
    this.collisionWater = Array.from({ length: MAP_ROWS }, () => Array.from({ length: MAP_COLS }, () => 0));
    this.collisionInteract = Array.from({ length: MAP_ROWS }, () => Array.from({ length: MAP_COLS }, () => 0));
    this.collisionGrid = this.mergeCollisions();

    this.pathfinding = new Pathfinding(this.collisionGrid);
    this.dayNight = new DayNightSystem();
    this.weather = new WeatherSystem();
    this.season = new SeasonSystem();

    if (renderer) {
      this.layerCache = new LayerCache(renderer);
    }

    // Add weather and season particle containers to effect layer
    this.effectLayer.addChild(this.weather.getParticleContainer());
    this.effectLayer.addChild(this.season.getParticleContainer());

    // Apply filters: day/night + season + weather combined
    this.container.filters = [
      this.dayNight.getFilter(),
      this.season.getFilter(),
      this.weather.getFilter(),
    ];

    this.drawGround();
    this.createDefaultBuildings();

    // Initialize behavior systems (after buildings are created)
    this.idleBehavior = new IdleBehaviorSystem(
      this.agents,
      this.buildings,
      this.pathfinding,
      this.collisionGrid,
    );
    this.socialAI = new SocialAISystem(this.agents);

    // Try to apply editor config if available
    this.applyEditorConfig();
  }

  /** Apply editor-exported town map config, replacing hardcoded defaults. */
  private applyEditorConfig(): void {
    const cfg = getTownMapConfig();
    if (!cfg) return;
    console.log("[TownScene] Applying editor config");

    // Clear existing ground and buildings
    this.groundLayer.removeChildren();
    this.buildingLayer.removeChildren();
    this.buildings.clear();
    this.collisionTerrain = Array.from({ length: MAP_ROWS }, () => Array.from({ length: MAP_COLS }, () => 0));
    this.collisionBuildings = Array.from({ length: MAP_ROWS }, () => Array.from({ length: MAP_COLS }, () => 0));
    this.collisionWater = Array.from({ length: MAP_ROWS }, () => Array.from({ length: MAP_COLS }, () => 0));
    this.collisionInteract = Array.from({ length: MAP_ROWS }, () => Array.from({ length: MAP_COLS }, () => 0));
    this.collisionGrid = this.mergeCollisions();

    // Render terrain from config
    this.drawGroundFromConfig(cfg);

    // Place buildings from config
    for (const bdef of cfg.buildings) {
      const building = new Building(
        bdef.id,
        bdef.type as BuildingType,
        bdef.x,
        bdef.y,
        bdef.owner,
        bdef.variant != null ? Number(bdef.variant) : undefined,
      );
      this.buildings.set(bdef.id, building);
      this.buildingLayer.addChild(building.container);
      if (this.layerCache) building.prerender(this.layerCache);
      this.markCollision(building);

      if (bdef.type === "cottage") {
        const b = building;
        building.container.on("pointertap", () => {
          if (b.ownerId) this.onCottageClick?.(b.ownerId);
        });
      }
      if (bdef.type === "plaza") {
        building.container.eventMode = "static";
        building.container.cursor = "pointer";
        building.container.on("pointertap", () => {
          this.onPlazaClick?.();
        });
      }
    }

    this.pathfinding.setGrid(this.collisionGrid);
  }

  /** Draw terrain from editor config data. */
  private drawGroundFromConfig(cfg: TownMapConfig): void {
    const PX = SCALED_TILE / 16;
    const ground = new Graphics();

    // Seeded random for consistent patterns
    let rng = 42;
    const rand = () => {
      rng = (rng * 1664525 + 1013904223) & 0x7fffffff;
      return rng / 0x7fffffff;
    };

    const grassColors = [0x7ec850, 0x72b847, 0x85d155, 0x6aad3e, 0x7bc04d];
    const pathStoneColors = [0xbfb08e, 0xd4c5a9, 0xc4b594, 0xccbea0];

    for (let ty = 0; ty < MAP_ROWS; ty++) {
      for (let tx = 0; tx < MAP_COLS; tx++) {
        const terrain = cfg.terrain[ty]?.[tx] ?? 0;
        const px = tx * SCALED_TILE;
        const py = ty * SCALED_TILE;

        switch (terrain) {
          case 0: // grass
            ground.rect(px, py, SCALED_TILE, SCALED_TILE);
            ground.fill(grassColors[Math.floor(rand() * grassColors.length)]);
            break;
          case 1: // dirt
            ground.rect(px, py, SCALED_TILE, SCALED_TILE);
            ground.fill(0xb5651d);
            break;
          case 2: // stone
            ground.rect(px, py, SCALED_TILE, SCALED_TILE);
            ground.fill(0x888888);
            break;
          case 3: // water
            ground.rect(px, py, SCALED_TILE, SCALED_TILE);
            ground.fill(0x3b82f6);
            break;
          case 4: // sand
            ground.rect(px, py, SCALED_TILE, SCALED_TILE);
            ground.fill(0xf5deb3);
            break;
          case 5: { // path
            ground.rect(px, py, SCALED_TILE, SCALED_TILE);
            ground.fill(0xc9b99a);
            for (let i = 0; i < 3; i++) {
              for (let j = 0; j < 3; j++) {
                const sx = px + PX + i * PX * 5;
                const sy = py + PX + j * PX * 5;
                const sc = pathStoneColors[Math.floor(rand() * pathStoneColors.length)];
                ground.roundRect(sx, sy, PX * 4, PX * 4, PX);
                ground.fill(sc);
              }
            }
            break;
          }
          default:
            ground.rect(px, py, SCALED_TILE, SCALED_TILE);
            ground.fill(grassColors[0]);
        }

        // Water collision
        if (terrain === 3) {
          this.collisionWater[ty][tx] = 1;
        }
      }
    }

    // Pre-render ground to texture if cache available
    if (this.layerCache) {
      const sprite = this.layerCache.toSprite(ground);
      this.groundLayer.addChild(sprite);
      ground.destroy();
    } else {
      this.groundLayer.addChild(ground);
    }
    // collisions updated from terrain: merge
    this.applyCollisionUpdate();

    // Decorations from config
    if (cfg.decorations?.length) {
      const decor = new Graphics();
      for (const d of cfg.decorations) {
        const dx = d.x * SCALED_TILE;
        const dy = d.y * SCALED_TILE;
        this.drawDecoration(decor, d.type, dx, dy, PX, rand);
      }
      if (this.layerCache) {
        const dSprite = this.layerCache.toSprite(decor);
        this.groundLayer.addChild(dSprite);
        decor.destroy();
      } else {
        this.groundLayer.addChild(decor);
      }
    }
  }

  /** Draw a single decoration by type. */
  private drawDecoration(g: Graphics, type: string, x: number, y: number, PX: number, rand: () => number): void {
    switch (type) {
      case "tree_oak": {
        g.rect(x + PX * 5, y + PX * 6, PX * 6, PX * 10);
        g.fill(0x8b4513);
        g.circle(x + PX * 8, y + PX * 2, PX * 8);
        g.fill(0x2e8b2e);
        g.circle(x + PX * 4, y + PX * 5, PX * 6);
        g.fill(0x2e8b2e);
        g.circle(x + PX * 12, y + PX * 5, PX * 6);
        g.fill(0x2e8b2e);
        g.circle(x + PX * 8, y, PX * 6);
        g.fill(0x32cd32);
        break;
      }
      case "tree_pine": {
        g.rect(x + PX * 6, y + PX * 10, PX * 4, PX * 6);
        g.fill(0x654321);
        g.moveTo(x + PX * 8, y - PX * 2);
        g.lineTo(x + PX * 2, y + PX * 10);
        g.lineTo(x + PX * 14, y + PX * 10);
        g.closePath();
        g.fill(0x1a6b1a);
        g.moveTo(x + PX * 8, y - PX * 4);
        g.lineTo(x + PX * 3, y + PX * 6);
        g.lineTo(x + PX * 13, y + PX * 6);
        g.closePath();
        g.fill(0x228b22);
        break;
      }
      case "bush": {
        g.circle(x + PX * 8, y + PX * 8, PX * 6);
        g.fill(0x2e8b2e);
        g.circle(x + PX * 5, y + PX * 9, PX * 4);
        g.fill(0x228b22);
        g.circle(x + PX * 11, y + PX * 9, PX * 4);
        g.fill(0x228b22);
        break;
      }
      case "flower": {
        const colors = [0xff6b6b, 0xffb347, 0xff69b4, 0x9370db, 0xffd700];
        g.moveTo(x + PX * 8, y + PX * 12);
        g.lineTo(x + PX * 8, y + PX * 6);
        g.stroke({ width: 1, color: 0x228b22 });
        g.circle(x + PX * 8, y + PX * 5, PX * 3);
        g.fill(colors[Math.floor(rand() * colors.length)]);
        g.circle(x + PX * 8, y + PX * 5, PX * 1.5);
        g.fill(0xffd700);
        break;
      }
      case "rock": {
        g.ellipse(x + PX * 8, y + PX * 8, PX * 5, PX * 4);
        g.fill(0x808080);
        g.stroke({ width: 1, color: 0x606060 });
        g.ellipse(x + PX * 7, y + PX * 7, PX * 2, PX * 1.5);
        g.fill({ color: 0xaaaaaa, alpha: 0.4 });
        break;
      }
      case "fence_h": {
        g.rect(x + PX * 2, y + PX * 4, PX * 2, PX * 8);
        g.fill(0xdeb887);
        g.rect(x + PX * 12, y + PX * 4, PX * 2, PX * 8);
        g.fill(0xdeb887);
        g.rect(x + PX * 2, y + PX * 6, PX * 12, PX * 2);
        g.fill(0xdeb887);
        g.rect(x + PX * 2, y + PX * 9, PX * 12, PX * 2);
        g.fill(0xdeb887);
        break;
      }
      case "fence_v": {
        g.rect(x + PX * 6, y + PX * 2, PX * 2, PX * 12);
        g.fill(0xdeb887);
        g.rect(x + PX * 4, y + PX * 2, PX * 2, PX * 2);
        g.fill(0xdeb887);
        g.rect(x + PX * 4, y + PX * 12, PX * 2, PX * 2);
        g.fill(0xdeb887);
        break;
      }
      case "mushroom": {
        g.rect(x + PX * 7, y + PX * 8, PX * 3, PX * 4);
        g.fill(0xf5deb3);
        g.ellipse(x + PX * 8, y + PX * 7, PX * 5, PX * 4);
        g.fill(0xcc3333);
        g.circle(x + PX * 6, y + PX * 6, PX);
        g.fill(0xffffff);
        g.circle(x + PX * 10, y + PX * 7, PX);
        g.fill(0xffffff);
        break;
      }
      case "bench": {
        g.rect(x + PX * 2, y + PX * 6, PX * 12, PX * 3);
        g.fill(0x8b4513);
        g.stroke({ width: 1, color: 0x654321 });
        g.rect(x + PX * 2, y + PX * 4, PX * 12, PX * 2);
        g.fill(0x8b4513);
        g.rect(x + PX * 3, y + PX * 9, PX * 2, PX * 4);
        g.fill(0x654321);
        g.rect(x + PX * 11, y + PX * 9, PX * 2, PX * 4);
        g.fill(0x654321);
        break;
      }
    }
  }

  setOnCottageClick(cb: (agentId: string) => void): void {
    this.onCottageClick = cb;
  }

  setOnPlazaClick(cb: () => void): void {
    this.onPlazaClick = cb;
  }

  setOnSubtitle(cb: (agentName: string, text: string) => void): void {
    this.onSubtitle = cb;
  }

  start(): void {
    this.dayNight.start();
    this.season.start();

    // Set canvas size for particle systems
    const w = MAP_COLS * SCALED_TILE;
    const h = MAP_ROWS * SCALED_TILE;
    this.weather.setCanvasSize(w, h);
    this.season.setCanvasSize(w, h);
  }

  stop(): void {
    this.dayNight.stop();
    this.season.stop();
  }

  /** Handle server messages. */
  handleMessage(msg: ServerMessage): void {
    switch (msg.type) {
      case "init":
        this.weather.setState(msg.weather.type, msg.weather.since, msg.weather.next_change);
        this.season.setCurrent(msg.season);
        // Clear demo/stale agents before loading server state
        for (const agent of this.agents.values()) {
          this.agentLayer.removeChild(agent.container);
        }
        this.agents.clear();
        // Reassign cottage ownership to real agents
        this.assignCottageOwners(msg.agents.map((a) => a.id));
        for (const info of msg.agents) {
          this.addOrUpdateAgent(info);
        }
        if (msg.town_layout.length > 0) {
          this.applyLayout(msg.town_layout);
        }
        if (msg.affinity.length > 0) {
          this.socialAI.setAffinities(msg.affinity);
        }
        break;
      case "agent_status": {
        const agent = this.agents.get(msg.agent);
        if (agent) {
          agent.setStatus(msg.status, msg.detail, msg.since);
          // Update cottage chimney smoke
          const cottage = this.findCottage(msg.agent);
          cottage?.setChimneySmoke(msg.status === "working");
        }
        break;
      }
      case "social_event":
        // Update affinities from server
        this.socialAI.setAffinities([{ agents: msg.agents, score: msg.affinity }]);
        break;
      case "cron_event": {
        // Show activity indicator on agent
        const cronAgent = this.agents.get(msg.agent);
        if (cronAgent) {
          if (msg.action === "started") {
            cronAgent.setStatus("working", `Cron: ${msg.job}`, Date.now());
            const cottage = this.findCottage(msg.agent);
            cottage?.setChimneySmoke(true);
          } else {
            cronAgent.setStatus("idle", "", Date.now());
            const cottage = this.findCottage(msg.agent);
            cottage?.setChimneySmoke(false);
          }
        }
        break;
      }
      case "message_received": {
        const replyText = (msg as any).reply || msg.preview || "";
        if (replyText && this.onSubtitle) {
          const agentName = this.agents.get(msg.agent)?.name ?? msg.agent;
          this.onSubtitle(agentName, replyText);
        }
        break;
      }
    }
  }

  /** Per-frame update. */
  update(): void {
    const now = performance.now();
    const dt = now - this.lastFrameTime;
    this.lastFrameTime = now;

    // Update agent movement
    for (const agent of this.agents.values()) {
      agent.update();
      // y-based depth sort key
      (agent.container as any).zIndex = agent.container.y | 0;
    }
    // Sort once per frame after updates
    this.agentLayer.sortChildren();

    // Idle behavior drives agent wander/visit decisions
    this.idleBehavior?.update(dt);

    // Social AI checks proximity and triggers socializing
    this.socialAI.update(dt);

    // Weather tick + particles
    this.weather.tick();
    this.weather.updateParticles();

    // Season particles
    this.season.updateParticles();
  }

  /** Merge per-layer collisions into a single grid used by pathfinding and AI. */
  private mergeCollisions(): number[][] {
    const rows = this.collisionTerrain?.length ?? MAP_ROWS;
    const cols = this.collisionTerrain?.[0]?.length ?? MAP_COLS;
    const merged = Array.from({ length: rows }, () => Array.from({ length: cols }, () => 0));
    for (let y = 0; y < rows; y++) {
      for (let x = 0; x < cols; x++) {
        merged[y][x] = (this.collisionTerrain[y]?.[x] || this.collisionBuildings[y]?.[x] || this.collisionWater[y]?.[x] || this.collisionInteract[y]?.[x]) ? 1 : 0;
      }
    }
    return merged;
  }

  private applyCollisionUpdate(): void {
    this.collisionGrid = this.mergeCollisions();
    this.pathfinding.setGrid(this.collisionGrid);
    this.idleBehavior?.setCollisionGrid(this.collisionGrid);
  }

  /** Try to load a Tiled map (if present) and replace ground/decorations + collisions. */
  async loadTilemapIfAvailable(): Promise<boolean> {
    const map = await loadTiledMap();
    if (!map) return false;
    if (map.width !== MAP_COLS || map.height !== MAP_ROWS) {
      console.warn("[Tilemap] Map size differs from config, using overlap area.");
    }
    const { ground, decorations, waterGrid, blockGrid } = await renderTiledToContainers(map);

    // Clear existing ground and default buildings so tilemap视觉生效
    this.groundLayer.removeChildren();
    this.buildingLayer.removeChildren();
    for (const b of this.buildings.values()) {
      // detach any listeners if needed (pixi removes on destroy)
    }
    this.buildings.clear();

    // Pre-render via cache if available
    if (this.layerCache) {
      const gSprite = this.layerCache.toSprite(ground);
      this.groundLayer.addChild(gSprite);
      const dSprite = this.layerCache.toSprite(decorations);
      this.groundLayer.addChild(dSprite);
    } else {
      this.groundLayer.addChild(ground);
      this.groundLayer.addChild(decorations);
    }

    // Apply collisions
    this.collisionTerrain = Array.from({ length: MAP_ROWS }, () => Array.from({ length: MAP_COLS }, () => 0));
    this.collisionWater = waterGrid;
    this.collisionBuildings = Array.from({ length: MAP_ROWS }, () => Array.from({ length: MAP_COLS }, () => 0));
    this.collisionInteract = Array.from({ length: MAP_ROWS }, () => Array.from({ length: MAP_COLS }, () => 0));
    // Merge building blocks (blockGrid) into buildings layer for now
    for (let y = 0; y < Math.min(blockGrid.length, MAP_ROWS); y++) {
      for (let x = 0; x < Math.min(blockGrid[0].length, MAP_COLS); x++) {
        if (blockGrid[y][x]) this.collisionBuildings[y][x] = 1;
      }
    }
    this.applyCollisionUpdate();
    return true;
  }

  /** Add or update an agent from server data. */
  addOrUpdateAgent(info: AgentInfo): void {
    let agent = this.agents.get(info.id);
    if (!agent) {
      // Place near their cottage or at a default position
      const cottage = this.findCottage(info.id);
      const startX = cottage ? cottage.getDoorTile().x : 10 + this.agents.size * 2;
      const startY = cottage ? cottage.getDoorTile().y : 10;
      agent = new Agent(info.id, info.name, startX, startY, info.color);
      this.agents.set(info.id, agent);
      this.agentLayer.addChild(agent.container);
    }
    agent.setStatus(info.status, info.detail, info.since);
  }

  getAgents(): Map<string, Agent> {
    return this.agents;
  }

  getBuildings(): Map<string, Building> {
    return this.buildings;
  }

  getCronJobs(): CronJob[] {
    return this.cronJobs;
  }

  setCronJobs(jobs: CronJob[]): void {
    this.cronJobs = jobs;
  }

  private findCottage(agentId: string): Building | undefined {
    for (const b of this.buildings.values()) {
      if (b.type === "cottage" && b.ownerId === agentId) return b;
    }
    return undefined;
  }

  /** Reassign cottage ownership from demo IDs to real agent IDs. */
  private assignCottageOwners(agentIds: string[]): void {
    const cottages = [...this.buildings.values()].filter((b) => b.type === "cottage");
    for (let i = 0; i < Math.min(agentIds.length, cottages.length); i++) {
      cottages[i].ownerId = agentIds[i];
    }
  }

  private applyLayout(layout: BuildingLayout[]): void {
    for (const bl of layout) {
      const building = this.buildings.get(bl.id);
      if (building) {
        building.moveTo(bl.x, bl.y);
        this.markCollision(building);
      }
    }
    this.pathfinding.setGrid(this.collisionGrid);
  }

  private createDefaultBuildings(): void {
    const defaults: { id: string; type: BuildingType; x: number; y: number; owner?: string; variant?: number }[] = [
      { id: "cottage-1", type: "cottage", x: 3, y: 3, owner: "agent-1", variant: 0 },
      { id: "cottage-2", type: "cottage", x: 11, y: 3, owner: "agent-2", variant: 1 },
      { id: "cottage-3", type: "cottage", x: 19, y: 3, owner: "agent-3", variant: 2 },
      { id: "library", type: "library", x: 28, y: 3 },
      { id: "plaza", type: "plaza", x: 13, y: 23 },
      { id: "shop", type: "shop", x: 30, y: 14 },
    ];

    for (const def of defaults) {
      const building = new Building(def.id, def.type, def.x, def.y, def.owner, def.variant);
      this.buildings.set(def.id, building);
      this.buildingLayer.addChild(building.container);
      if (this.layerCache) building.prerender(this.layerCache);
      this.markCollision(building);

      // Wire cottage clicks — read ownerId at click time (may be reassigned by assignCottageOwners)
      if (def.type === "cottage") {
        const b = building;
        building.container.on("pointertap", () => {
          if (b.ownerId) this.onCottageClick?.(b.ownerId);
        });
      }

      // Wire plaza click (bulletin board)
      if (def.type === "plaza") {
        building.container.eventMode = "static";
        building.container.cursor = "pointer";
        building.container.on("pointertap", () => {
          this.onPlazaClick?.();
        });
      }
    }
    this.pathfinding.setGrid(this.collisionGrid);
  }

  private markCollision(building: Building): void {
    for (let dy = 0; dy < building.heightTiles; dy++) {
      for (let dx = 0; dx < building.widthTiles; dx++) {
        const tx = building.tileX + dx;
        const ty = building.tileY + dy;
        if (ty >= 0 && ty < MAP_ROWS && tx >= 0 && tx < MAP_COLS) {
          this.collisionBuildings[ty][tx] = 1;
        }
      }
    }
    this.applyCollisionUpdate();
  }

  private drawGround(): void {
    const PX = SCALED_TILE / 16;
    const totalW = MAP_COLS * SCALED_TILE;
    const totalH = MAP_ROWS * SCALED_TILE;

    // Seeded random for consistent layout
    const seed = 42;
    let rng = seed;
    const rand = () => {
      rng = (rng * 1664525 + 1013904223) & 0x7fffffff;
      return rng / 0x7fffffff;
    };

    const ground = new Graphics();

    // ── Base grass with tile variation ──
    const grassColors = [0x7ec850, 0x72b847, 0x85d155, 0x6aad3e, 0x7bc04d];
    for (let ty = 0; ty < MAP_ROWS; ty++) {
      for (let tx = 0; tx < MAP_COLS; tx++) {
        const color = grassColors[Math.floor(rand() * grassColors.length)];
        ground.rect(tx * SCALED_TILE, ty * SCALED_TILE, SCALED_TILE, SCALED_TILE);
        ground.fill(color);
      }
    }

    // ── Paths with cobblestone texture ──
    const pathBaseColor = 0xc9b99a;
    const pathStoneColors = [0xbfb08e, 0xd4c5a9, 0xc4b594, 0xccbea0];
    // Horizontal path at row 9
    for (let tx = 0; tx < MAP_COLS; tx++) {
      ground.rect(tx * SCALED_TILE, 9 * SCALED_TILE, SCALED_TILE, SCALED_TILE);
      ground.fill(pathBaseColor);
      // Cobblestone pattern
      for (let i = 0; i < 3; i++) {
        for (let j = 0; j < 3; j++) {
          const stoneX = tx * SCALED_TILE + PX * 1 + i * PX * 5;
          const stoneY = 9 * SCALED_TILE + PX * 1 + j * PX * 5;
          const sc = pathStoneColors[Math.floor(rand() * pathStoneColors.length)];
          ground.roundRect(stoneX, stoneY, PX * 4, PX * 4, PX);
          ground.fill(sc);
          ground.roundRect(stoneX, stoneY, PX * 4, PX * 4, PX);
          ground.stroke({ width: 0.5, color: 0xa89070, alpha: 0.4 });
        }
      }
    }
    // Vertical path at col 15
    for (let ty = 0; ty < MAP_ROWS; ty++) {
      ground.rect(15 * SCALED_TILE, ty * SCALED_TILE, SCALED_TILE, SCALED_TILE);
      ground.fill(pathBaseColor);
      for (let i = 0; i < 3; i++) {
        for (let j = 0; j < 3; j++) {
          const stoneX = 15 * SCALED_TILE + PX * 1 + i * PX * 5;
          const stoneY = ty * SCALED_TILE + PX * 1 + j * PX * 5;
          const sc = pathStoneColors[Math.floor(rand() * pathStoneColors.length)];
          ground.roundRect(stoneX, stoneY, PX * 4, PX * 4, PX);
          ground.fill(sc);
          ground.roundRect(stoneX, stoneY, PX * 4, PX * 4, PX);
          ground.stroke({ width: 0.5, color: 0xa89070, alpha: 0.4 });
        }
      }
    }
    // Path edge trim
    ground.moveTo(0, 9 * SCALED_TILE);
    ground.lineTo(totalW, 9 * SCALED_TILE);
    ground.moveTo(0, 10 * SCALED_TILE);
    ground.lineTo(totalW, 10 * SCALED_TILE);
    ground.stroke({ width: 1, color: 0x8b7355, alpha: 0.5 });
    ground.moveTo(15 * SCALED_TILE, 0);
    ground.lineTo(15 * SCALED_TILE, totalH);
    ground.moveTo(16 * SCALED_TILE, 0);
    ground.lineTo(16 * SCALED_TILE, totalH);
    ground.stroke({ width: 1, color: 0x8b7355, alpha: 0.5 });

    if (this.layerCache) {
      const sprite = this.layerCache.toSprite(ground);
      this.groundLayer.addChild(sprite);
      ground.destroy();
    } else {
      this.groundLayer.addChild(ground);
    }

    // ── Decorations layer (on top of ground, behind buildings) ──
    const decor = new Graphics();

    // ── Grass tufts ──
    for (let i = 0; i < 60; i++) {
      const gx = rand() * totalW;
      const gy = rand() * totalH;
      // Skip if on path
      const tx = Math.floor(gx / SCALED_TILE);
      const ty = Math.floor(gy / SCALED_TILE);
      if (tx === 15 || ty === 9) continue;
      const tintG = 0x228b22 + Math.floor(rand() * 0x20) * 0x100;
      for (let b = 0; b < 3; b++) {
        decor.moveTo(gx + b * PX * 2 - PX * 2, gy);
        decor.lineTo(gx + b * PX * 2 - PX * 2 + (rand() - 0.5) * PX * 2, gy - PX * (3 + rand() * 3));
        decor.stroke({ width: 1.5, color: tintG, alpha: 0.7 });
      }
    }

    // ── Wildflowers ──
    const flowerColors = [0xff6b6b, 0xffb347, 0xff69b4, 0x9370db, 0xffd700, 0xff4500];
    for (let i = 0; i < 25; i++) {
      const fx = rand() * totalW;
      const fy = rand() * totalH;
      const tx = Math.floor(fx / SCALED_TILE);
      const ty = Math.floor(fy / SCALED_TILE);
      if (tx === 15 || ty === 9) continue;
      // Stem
      decor.moveTo(fx, fy);
      decor.lineTo(fx, fy - PX * 4);
      decor.stroke({ width: 1, color: 0x228b22 });
      // Petals
      const fc = flowerColors[Math.floor(rand() * flowerColors.length)];
      decor.circle(fx, fy - PX * 4, PX * 2);
      decor.fill(fc);
      decor.circle(fx, fy - PX * 4, PX * 1);
      decor.fill(0xffd700);
    }

    // ── Trees ──
    const treePositions = [
      [0, 1], [1, 16], [27, 1], [28, 16], [0, 8], [29, 7],
      [18, 16], [2, 18], [26, 18], [7, 16], [0, 14],
    ];
    for (const [ttx, tty] of treePositions) {
      const tx = ttx * SCALED_TILE;
      const ty = tty * SCALED_TILE;
      // Trunk
      decor.rect(tx + PX * 5, ty + PX * 6, PX * 6, PX * 10);
      decor.fill(0x8b4513);
      decor.rect(tx + PX * 5, ty + PX * 6, PX * 6, PX * 10);
      decor.stroke({ width: 1, color: 0x654321 });
      // Canopy - layered circles for fullness
      const canopyColor = 0x2e8b2e;
      const canopyLight = 0x32cd32;
      decor.circle(tx + PX * 8, ty + PX * 2, PX * 8);
      decor.fill(canopyColor);
      decor.circle(tx + PX * 4, ty + PX * 5, PX * 6);
      decor.fill(canopyColor);
      decor.circle(tx + PX * 12, ty + PX * 5, PX * 6);
      decor.fill(canopyColor);
      decor.circle(tx + PX * 8, ty, PX * 6);
      decor.fill(canopyLight);
      // Highlight
      decor.circle(tx + PX * 6, ty - PX * 1, PX * 2);
      decor.fill({ color: 0x90ee90, alpha: 0.4 });
    }

    // ── Fences near cottages ──
    const fenceY = 2 * SCALED_TILE + PX * 14; // just above cottage row
    for (const startX of [3, 8, 13]) {
      for (let fi = 0; fi < 3; fi++) {
        const fx = startX * SCALED_TILE + fi * SCALED_TILE;
        // Post
        decor.rect(fx + PX * 2, fenceY, PX * 2, PX * 8);
        decor.fill(0xdeb887);
        decor.rect(fx + PX * 12, fenceY, PX * 2, PX * 8);
        decor.fill(0xdeb887);
        // Rails
        decor.rect(fx + PX * 2, fenceY + PX * 2, PX * 12, PX * 2);
        decor.fill(0xdeb887);
        decor.rect(fx + PX * 2, fenceY + PX * 5, PX * 12, PX * 2);
        decor.fill(0xdeb887);
      }
    }

    // ── Mailboxes at each cottage ──
    for (const [mx, my] of [[5, 6], [10, 6], [15, 6]]) {
      const mbx = mx * SCALED_TILE + PX * 2;
      const mby = my * SCALED_TILE;
      // Post
      decor.rect(mbx + PX * 2, mby + PX * 2, PX * 2, PX * 10);
      decor.fill(0x8b4513);
      // Box
      decor.rect(mbx, mby, PX * 6, PX * 5);
      decor.fill(0x4169e1);
      decor.rect(mbx, mby, PX * 6, PX * 5);
      decor.stroke({ width: 1, color: 0x2c4ba0 });
      // Flag
      decor.rect(mbx + PX * 5, mby + PX, PX * 3, PX * 2);
      decor.fill(0xff4444);
    }

    // ── Rocks scattered ──
    const rockPositions = [[6, 17], [19, 8], [23, 15], [3, 12], [17, 18]];
    for (const [rx, ry] of rockPositions) {
      const rockX = rx * SCALED_TILE + PX * 4;
      const rockY = ry * SCALED_TILE + PX * 4;
      decor.ellipse(rockX, rockY, PX * 4, PX * 3);
      decor.fill(0x808080);
      decor.ellipse(rockX, rockY, PX * 4, PX * 3);
      decor.stroke({ width: 1, color: 0x606060 });
      // Highlight
      decor.ellipse(rockX - PX, rockY - PX, PX * 1.5, PX * 1);
      decor.fill({ color: 0xaaaaaa, alpha: 0.4 });
    }

    // ── Mushrooms ──
    const mushroomPositions = [[1, 10], [28, 3], [22, 17]];
    for (const [mx2, my2] of mushroomPositions) {
      const mushX = mx2 * SCALED_TILE + PX * 6;
      const mushY = my2 * SCALED_TILE + PX * 8;
      // Stem
      decor.rect(mushX - PX, mushY, PX * 3, PX * 4);
      decor.fill(0xf5deb3);
      // Cap
      decor.ellipse(mushX + PX * 0.5, mushY, PX * 4, PX * 3);
      decor.fill(0xcc3333);
      // Spots
      decor.circle(mushX - PX, mushY - PX, PX * 0.8);
      decor.fill(0xffffff);
      decor.circle(mushX + PX * 2, mushY - PX * 1.5, PX * 0.6);
      decor.fill(0xffffff);
    }

    // ── Bushes ──
    const bushPositions = [[2, 7], [6, 2], [11, 2], [16, 2], [26, 7], [19, 14], [4, 17]];
    for (const [bx, by] of bushPositions) {
      const bushX = bx * SCALED_TILE + PX * 4;
      const bushY = by * SCALED_TILE + PX * 6;
      decor.circle(bushX, bushY, PX * 5);
      decor.fill(0x2e8b2e);
      decor.circle(bushX + PX * 4, bushY + PX, PX * 4);
      decor.fill(0x228b22);
      decor.circle(bushX - PX * 2, bushY + PX * 2, PX * 3);
      decor.fill(0x32cd32);
      // Berry dots on some bushes
      if (rand() > 0.5) {
        decor.circle(bushX + PX, bushY - PX * 2, PX);
        decor.fill(0xff4444);
        decor.circle(bushX + PX * 3, bushY, PX);
        decor.fill(0xff4444);
      }
    }

    // ── Water pond (bottom right area) ──
    const pondX = 25 * SCALED_TILE;
    const pondY = 16 * SCALED_TILE;
    decor.ellipse(pondX + PX * 16, pondY + PX * 12, PX * 20, PX * 12);
    decor.fill(0x4682b4);
    decor.ellipse(pondX + PX * 16, pondY + PX * 12, PX * 20, PX * 12);
    decor.stroke({ width: 2, color: 0x3a6d8c });
    // Water shine
    decor.ellipse(pondX + PX * 12, pondY + PX * 9, PX * 6, PX * 3);
    decor.fill({ color: 0x87ceeb, alpha: 0.4 });
    // Reeds
    for (let ri = 0; ri < 4; ri++) {
      const rx = pondX + PX * 2 + ri * PX * 4;
      decor.moveTo(rx, pondY + PX * 6);
      decor.lineTo(rx + PX, pondY - PX * 4);
      decor.stroke({ width: 1.5, color: 0x6b8e23 });
      decor.ellipse(rx + PX, pondY - PX * 5, PX * 1.5, PX * 3);
      decor.fill(0x8b6914);
    }

    if (this.layerCache) {
      const dSprite = this.layerCache.toSprite(decor);
      this.groundLayer.addChild(dSprite);
      decor.destroy();
    } else {
      this.groundLayer.addChild(decor);
    }
    // Merge after any terrain/water updates in default map
    this.applyCollisionUpdate();
  }
}
