/**
 * Social AI system — drives affinity-based interactions between agents.
 *
 * When two idle agents are within proximity, there's a chance they start socializing.
 * Higher affinity → higher chance, longer interaction duration.
 * Speech bubble color reflects affinity (white → pink → red).
 */

import { SCALED_TILE, IDLE_CONFIG } from "@/config";
import type { Agent } from "@/entities/Agent";
import type { AffinityPair } from "@/net/Protocol";

interface SocialInteraction {
  agentA: string;
  agentB: string;
  /** remaining duration in ms */
  remaining: number;
}

/** Proximity threshold in tiles for social interaction trigger. */
const SOCIAL_PROXIMITY = 3;

/** Base interaction duration in ms. */
const BASE_DURATION = 5_000;

/** Extra duration per 0.1 affinity. */
const AFFINITY_DURATION_BONUS = 2_000;

/**
 * Manages social interactions between agents in the town.
 * Call `update(dt)` every frame.
 */
export class SocialAISystem {
  private agents: Map<string, Agent>;
  private affinities = new Map<string, number>(); // "a:b" → score
  private activeInteractions: SocialInteraction[] = [];

  /** Callback fired when two agents start socializing. */
  onSocialStart?: (agentA: string, agentB: string, affinity: number) => void;
  /** Callback fired when a social interaction ends. */
  onSocialEnd?: (agentA: string, agentB: string) => void;

  constructor(agents: Map<string, Agent>) {
    this.agents = agents;
  }

  /** Load affinity data from server init message. */
  setAffinities(pairs: AffinityPair[]): void {
    this.affinities.clear();
    for (const p of pairs) {
      const key = this.pairKey(p.agents[0], p.agents[1]);
      this.affinities.set(key, p.score);
    }
  }

  /** Get affinity between two agents (0.0 if unknown). */
  getAffinity(a: string, b: string): number {
    return this.affinities.get(this.pairKey(a, b)) ?? 0;
  }

  /**
   * Per-frame update.
   * @param dt - delta time in ms
   */
  update(dt: number): void {
    // Tick active interactions
    this.tickInteractions(dt);

    // Check for new social opportunities between idle agents
    this.checkProximity();
  }

  /** Get speech bubble color for a given affinity level. */
  static bubbleColor(affinity: number): number {
    // white (0.0) → pink (0.5) → red (1.0)
    if (affinity < 0.3) return 0xffffff;   // white
    if (affinity < 0.6) return 0xf8bbd0;   // light pink
    if (affinity < 0.8) return 0xf06292;   // pink
    return 0xe53935;                        // red
  }

  private tickInteractions(dt: number): void {
    for (let i = this.activeInteractions.length - 1; i >= 0; i--) {
      const interaction = this.activeInteractions[i];
      interaction.remaining -= dt;

      if (interaction.remaining <= 0) {
        // End interaction
        const agentA = this.agents.get(interaction.agentA);
        const agentB = this.agents.get(interaction.agentB);

        if (agentA?.status === "socializing") {
          agentA.setStatus("idle", "", Date.now());
        }
        if (agentB?.status === "socializing") {
          agentB.setStatus("idle", "", Date.now());
        }

        this.onSocialEnd?.(interaction.agentA, interaction.agentB);
        this.activeInteractions.splice(i, 1);
      }
    }
  }

  private checkProximity(): void {
    const idleAgents = [...this.agents.entries()].filter(
      ([, a]) => a.status === "idle" && !a.isMoving(),
    );

    // Check all pairs
    for (let i = 0; i < idleAgents.length; i++) {
      for (let j = i + 1; j < idleAgents.length; j++) {
        const [idA, agentA] = idleAgents[i];
        const [idB, agentB] = idleAgents[j];

        // Skip if either is already in an active interaction
        if (this.isInInteraction(idA) || this.isInInteraction(idB)) continue;

        const dist = Math.abs(agentA.tileX - agentB.tileX) + Math.abs(agentA.tileY - agentB.tileY);
        if (dist > SOCIAL_PROXIMITY) continue;

        // Roll for social interaction
        const affinity = this.getAffinity(idA, idB);
        const chance = IDLE_CONFIG.socialChance + affinity * 0.3; // higher affinity = higher chance
        if (Math.random() > chance) continue;

        // Start socializing
        const duration = BASE_DURATION + affinity * AFFINITY_DURATION_BONUS * 10;
        this.activeInteractions.push({
          agentA: idA,
          agentB: idB,
          remaining: duration,
        });

        agentA.setStatus("socializing", `Chatting with ${agentB.name}`, Date.now());
        agentB.setStatus("socializing", `Chatting with ${agentA.name}`, Date.now());

        this.onSocialStart?.(idA, idB, affinity);
      }
    }
  }

  private isInInteraction(agentId: string): boolean {
    return this.activeInteractions.some(
      (i) => i.agentA === agentId || i.agentB === agentId,
    );
  }

  /** Canonical pair key (sorted so a:b == b:a). */
  private pairKey(a: string, b: string): string {
    return a < b ? `${a}:${b}` : `${b}:${a}`;
  }
}
