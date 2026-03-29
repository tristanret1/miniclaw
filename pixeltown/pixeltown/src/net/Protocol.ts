/** WebSocket protocol message types — shared between client and server. */

// ── Agent status ──

export type AgentStatus = "idle" | "working" | "sleeping" | "socializing" | "offline";

export interface AgentInfo {
  id: string;
  name: string;
  status: AgentStatus;
  detail: string;
  since: number; // unix timestamp
  color?: number; // tint color for sprite differentiation
}

export interface CronJob {
  id: string;
  name: string;
  schedule: string;
  next_run: number;
  agent_id: string;
}

export type WeatherType = "sunny" | "rainy" | "snowy" | "thunderstorm";
export type SeasonType = "spring" | "summer" | "autumn" | "winter";

export interface WeatherState {
  type: WeatherType;
  since: number;
  next_change: number;
}

export interface BuildingLayout {
  id: string;
  x: number;
  y: number;
}

export interface AffinityPair {
  agents: [string, string];
  score: number; // 0.0 - 1.0
}

// ── Server → Client messages ──

export interface InitMessage {
  type: "init";
  agents: AgentInfo[];
  weather: WeatherState;
  season: SeasonType;
  town_layout: BuildingLayout[];
  affinity: AffinityPair[];
}

export interface AgentStatusMessage {
  type: "agent_status";
  agent: string;
  status: AgentStatus;
  detail: string;
  since: number;
}

export interface SocialEventMessage {
  type: "social_event";
  agents: [string, string];
  action: string;
  affinity: number;
}

export interface CronEventMessage {
  type: "cron_event";
  agent: string;
  job: string;
  action: "started" | "finished";
}

export interface MessageReceivedMessage {
  type: "message_received";
  agent: string;
  from: string;
  preview: string;
  reply?: string;
}

export type ServerMessage =
  | InitMessage
  | AgentStatusMessage
  | SocialEventMessage
  | CronEventMessage
  | MessageReceivedMessage;

// ── Client → Server messages ──

export interface SendMessageCommand {
  type: "send_message";
  agent: string;
  text: string;
  channel: string;
}

export interface TriggerTaskCommand {
  type: "trigger_task";
  agent: string;
  job_id: string;
}

export interface ToggleAgentCommand {
  type: "toggle_agent";
  agent: string;
  enabled: boolean;
}

export interface SaveLayoutCommand {
  type: "save_layout";
  buildings: BuildingLayout[];
}

export type ClientMessage =
  | SendMessageCommand
  | TriggerTaskCommand
  | ToggleAgentCommand
  | SaveLayoutCommand;
