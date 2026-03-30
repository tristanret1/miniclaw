/**
 * Idle behavior tree — drives autonomous agent actions when idle.
 *
 * Actions are selected by weighted random roll from IDLE_WEIGHTS:
 *   wander (40%), visitCottage (20%), sitBench (15%), lookFlowers (10%), goPlaza (15%)
 *
 * Each agent gets its own cooldown timer; when it fires the agent picks an action,
 * pathfinds to a target tile, and walks there. After arriving the timer resets.
 */

import { IDLE_WEIGHTS, IDLE_CONFIG, MAP_COLS, MAP_ROWS } from "@/config";
import type { Agent } from "@/entities/Agent";
import type { Building } from "@/entities/Building";
import type { Pathfinding } from "@/systems/Pathfinding";

export type IdleAction = keyof typeof IDLE_WEIGHTS;

interface AgentIdleState {
  /** ms until next action decision */
  cooldown: number;
  /** current action being executed (null = waiting) */
  currentAction: IdleAction | null;
}

/**
 * Manages idle behavior for all agents in the town.
 * Call `update(dt)` every frame with delta time in ms.
 */
export class IdleBehaviorSystem {
  private states = new Map<string, AgentIdleState>();

  private agents: Map<string, Agent>;
  private buildings: Map<string, Building>;
  private pathfinding: Pathfinding;
  private collisionGrid: number[][];

  constructor(
    agents: Map<string, Agent>,
    buildings: Map<string, Building>,
    pathfinding: Pathfinding,
    collisionGrid: number[][],
  ) {
    this.agents = agents;
    this.buildings = buildings;
    this.pathfinding = pathfinding;
    this.collisionGrid = collisionGrid;
  }

  /** Update the collision grid reference after map/layout changes. */
  setCollisionGrid(grid: number[][]): void {
    this.collisionGrid = grid;
  }

  /**
   * Per-frame update.
   * @param dt - delta time in ms since last frame
   */
  update(dt: number): void {
    for (const [id, agent] of this.agents) {
      // Only drive idle agents
      if (agent.status !== "idle") {
        this.states.delete(id);
        continue;
      }

      // Skip agents that are indoors
      if (agent.indoors) continue;

      // Skip if agent is still moving to a previous target
      if (agent.isMoving()) continue;

      let state = this.states.get(id);
      if (!state) {
        state = {
          cooldown: this.randomInterval(),
          currentAction: null,
        };
        this.states.set(id, state);
      }

      // Agent just arrived at home door → enter building
      if (state.currentAction === "goHome") {
        const stayDuration = 60_000 + Math.random() * 120_000; // 1-3 minutes inside
        console.log(`[Idle] ${agent.name} enters home (${Math.round(stayDuration / 1000)}s)`);
        agent.enterBuilding(stayDuration);
        state.currentAction = null;
        state.cooldown = stayDuration + 1000;
        continue;
      }

      // Tick cooldown
      state.cooldown -= dt;
      if (state.cooldown > 0) continue;

      // Pick and execute an action
      const action = this.pickAction();
      state.currentAction = action;
      console.log(`[Idle] ${agent.name} → ${action}`);

      const moved = this.executeAction(agent, action);
      // If pathfinding failed, retry quickly instead of waiting full interval
      state.cooldown = moved ? this.randomInterval() : 500;
    }
  }

  /** Pick an action using weighted random selection. */
  private pickAction(): IdleAction {
    const roll = Math.random();
    let cumulative = 0;
    for (const [action, weight] of Object.entries(IDLE_WEIGHTS) as [IdleAction, number][]) {
      cumulative += weight;
      if (roll < cumulative) return action;
    }
    return "wander";
  }

  /** Execute the chosen idle action for an agent. Returns true if agent started moving. */
  private executeAction(agent: Agent, action: IdleAction): boolean {
    let target: { x: number; y: number } | null = null;

    switch (action) {
      case "wander":
        target = this.findRandomWalkable(agent);
        break;
      case "goHome":
        target = this.findOwnCottageDoor(agent);
        break;
      case "visitCottage":
        target = this.findCottageDoor(agent);
        break;
      case "sitBench":
        target = this.findNearBuilding("shop", agent);
        break;
      case "lookFlowers":
        target = this.findFlowerSpot(agent);
        break;
      case "goPlaza":
        target = this.findNearBuilding("plaza", agent);
        break;
    }

    if (!target) {
      target = this.findRandomWalkable(agent);
    }

    if (target) {
      const path = this.pathfinding.findPath(
        { x: agent.tileX, y: agent.tileY },
        target,
      );
      if (path.length > 1) {
        agent.setPath(path);
        return true;
      }
    }
    return false;
  }

  /** Find a random walkable tile within reasonable distance. */
  private findRandomWalkable(agent: Agent): { x: number; y: number } | null {
    for (let i = 0; i < 15; i++) {
      const tx = Math.floor(Math.random() * MAP_COLS);
      const ty = Math.floor(Math.random() * MAP_ROWS);
      if (this.collisionGrid[ty]?.[tx] === 0) {
        // Keep path length reasonable (< 25 tiles)
        const dist = Math.abs(tx - agent.tileX) + Math.abs(ty - agent.tileY);
        if (dist > 2 && dist < 25) return { x: tx, y: ty };
      }
    }
    return null;
  }

  /** Find the door of the agent's own cottage. */
  private findOwnCottageDoor(agent: Agent): { x: number; y: number } | null {
    for (const b of this.buildings.values()) {
      if (b.type === "cottage" && b.ownerId === agent.id) {
        return b.getDoorTile();
      }
    }
    return null;
  }

  /** Find the door of a random cottage (not the agent's own). */
  private findCottageDoor(agent: Agent): { x: number; y: number } | null {
    const cottages = [...this.buildings.values()].filter(
      (b) => b.type === "cottage" && b.ownerId !== agent.id,
    );
    if (cottages.length === 0) return null;
    const cottage = cottages[Math.floor(Math.random() * cottages.length)];
    return cottage.getDoorTile();
  }

  /** Find a walkable tile adjacent to a building of the given type. */
  private findNearBuilding(
    type: string,
    agent: Agent,
  ): { x: number; y: number } | null {
    const candidates = [...this.buildings.values()].filter((b) => b.type === type);
    if (candidates.length === 0) return null;
    const building = candidates[Math.floor(Math.random() * candidates.length)];
    return this.walkableTileNear(building);
  }

  /** Find a "flower spot" — a walkable tile near the edges of the map (garden area). */
  private findFlowerSpot(agent: Agent): { x: number; y: number } | null {
    for (let i = 0; i < 10; i++) {
      // Edges tend to be garden-like areas
      const edge = Math.floor(Math.random() * 4);
      let tx: number, ty: number;
      switch (edge) {
        case 0: tx = Math.floor(Math.random() * 5); ty = Math.floor(Math.random() * MAP_ROWS); break;
        case 1: tx = MAP_COLS - 1 - Math.floor(Math.random() * 5); ty = Math.floor(Math.random() * MAP_ROWS); break;
        case 2: tx = Math.floor(Math.random() * MAP_COLS); ty = Math.floor(Math.random() * 5); break;
        default: tx = Math.floor(Math.random() * MAP_COLS); ty = MAP_ROWS - 1 - Math.floor(Math.random() * 5); break;
      }
      if (this.collisionGrid[ty]?.[tx] === 0) return { x: tx, y: ty };
    }
    return null;
  }

  /** Find a walkable tile adjacent to a building. */
  private walkableTileNear(building: Building): { x: number; y: number } | null {
    // Try tiles around the building perimeter
    const offsets = [
      { x: Math.floor(building.widthTiles / 2), y: building.heightTiles },     // below door
      { x: -1, y: Math.floor(building.heightTiles / 2) },                      // left
      { x: building.widthTiles, y: Math.floor(building.heightTiles / 2) },      // right
      { x: Math.floor(building.widthTiles / 2), y: -1 },                       // above
    ];

    for (const off of offsets) {
      const tx = building.tileX + off.x;
      const ty = building.tileY + off.y;
      if (tx >= 0 && tx < MAP_COLS && ty >= 0 && ty < MAP_ROWS && this.collisionGrid[ty]?.[tx] === 0) {
        return { x: tx, y: ty };
      }
    }
    return null;
  }

  /** Random interval between actions (wanderIntervalMin..wanderIntervalMax). */
  private randomInterval(): number {
    const { wanderIntervalMin, wanderIntervalMax } = IDLE_CONFIG;
    return wanderIntervalMin + Math.random() * (wanderIntervalMax - wanderIntervalMin);
  }
}
