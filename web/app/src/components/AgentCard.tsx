import { AgentSummary } from '../lib/api';

interface Props {
  agent: AgentSummary;
  onToggle: (id: string, enabled: boolean) => void;
  onDelete: (id: string) => void;
  onClick: (id: string) => void;
}

export function AgentCard({ agent, onToggle, onDelete, onClick }: Props) {
  return (
    <div
      className="border border-zinc-700 rounded-lg p-4 bg-zinc-900 hover:border-zinc-500 cursor-pointer transition-colors"
      onClick={() => onClick(agent.id)}
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-2xl">{agent.emoji || '🤖'}</span>
          <div>
            <h3 className="text-lg font-semibold text-zinc-100">{agent.display_name}</h3>
            <p className="text-sm text-zinc-400">{agent.name}</p>
          </div>
        </div>
        <button
          className={`px-3 py-1 rounded text-sm font-medium ${
            agent.enabled ? 'bg-green-900 text-green-300' : 'bg-zinc-800 text-zinc-400'
          }`}
          onClick={(e) => { e.stopPropagation(); onToggle(agent.id, !agent.enabled); }}
        >
          {agent.enabled ? 'Enabled' : 'Disabled'}
        </button>
      </div>
      <div className="flex justify-between items-center text-xs text-zinc-500 mt-3">
        <span>Updated {new Date(agent.updated_at).toLocaleDateString()}</span>
        <button
          className="text-red-400 hover:text-red-300"
          onClick={(e) => {
            e.stopPropagation();
            if (confirm(`Delete agent "${agent.display_name}"?`)) onDelete(agent.id);
          }}
        >
          Delete
        </button>
      </div>
    </div>
  );
}
