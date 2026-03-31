import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, AgentSummary } from '../lib/api';
import { AgentCard } from '../components/AgentCard';

export function AgentList() {
  const [agents, setAgents] = useState<AgentSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState('');
  const [newDisplayName, setNewDisplayName] = useState('');
  const [newEmoji, setNewEmoji] = useState('');
  const navigate = useNavigate();

  const fetchAgents = async () => {
    setLoading(true);
    try { setAgents(await api.listAgents()); } finally { setLoading(false); }
  };

  useEffect(() => { fetchAgents(); }, []);

  const handleToggle = async (id: string, enabled: boolean) => {
    await api.updateAgent(id, { enabled });
    await fetchAgents();
  };

  const handleDelete = async (id: string) => {
    await api.deleteAgent(id);
    await fetchAgents();
  };

  const handleCreate = async () => {
    if (!newName || !newDisplayName) return;
    await api.createAgent({ name: newName, display_name: newDisplayName, emoji: newEmoji });
    setShowCreate(false); setNewName(''); setNewDisplayName(''); setNewEmoji('');
    await fetchAgents();
  };

  return (
    <div className="max-w-4xl mx-auto p-6">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold text-zinc-100">Agents</h1>
        <button className="bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded" onClick={() => setShowCreate(true)}>
          + New Agent
        </button>
      </div>

      {showCreate && (
        <div className="border border-zinc-700 rounded-lg p-4 bg-zinc-900 mb-6">
          <h2 className="text-lg font-semibold text-zinc-100 mb-3">Create Agent</h2>
          <div className="grid grid-cols-3 gap-3 mb-3">
            <input placeholder="name (slug)" value={newName} onChange={(e) => setNewName(e.target.value)}
              className="bg-zinc-800 border border-zinc-600 rounded px-3 py-2 text-zinc-100" />
            <input placeholder="Display Name" value={newDisplayName} onChange={(e) => setNewDisplayName(e.target.value)}
              className="bg-zinc-800 border border-zinc-600 rounded px-3 py-2 text-zinc-100" />
            <input placeholder="Emoji" value={newEmoji} onChange={(e) => setNewEmoji(e.target.value)}
              className="bg-zinc-800 border border-zinc-600 rounded px-3 py-2 text-zinc-100" />
          </div>
          <div className="flex gap-2">
            <button className="bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded" onClick={handleCreate}>Create</button>
            <button className="bg-zinc-700 hover:bg-zinc-600 text-zinc-300 px-4 py-2 rounded" onClick={() => setShowCreate(false)}>Cancel</button>
          </div>
        </div>
      )}

      {loading ? (
        <p className="text-zinc-400">Loading...</p>
      ) : agents.length === 0 ? (
        <p className="text-zinc-400">No agents yet. Create one to get started.</p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {agents.map((agent) => (
            <AgentCard key={agent.id} agent={agent} onToggle={handleToggle} onDelete={handleDelete}
              onClick={(id) => navigate(`/agents/${id}`)} />
          ))}
        </div>
      )}
    </div>
  );
}
