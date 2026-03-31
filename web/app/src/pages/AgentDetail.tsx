import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { api, AgentDetail as AgentDetailType } from '../lib/api';
import { DocumentEditor } from '../components/DocumentEditor';
import { VersionHistory } from '../components/VersionHistory';
import { ConfigEditor } from '../components/ConfigEditor';

const DOC_TABS = [
  { key: 'soul', label: 'Soul' },
  { key: 'identity', label: 'Identity' },
  { key: 'user_doc', label: 'User Doc' },
  { key: 'config', label: 'Config' },
] as const;

type TabKey = (typeof DOC_TABS)[number]['key'];

export function AgentDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [agent, setAgent] = useState<AgentDetailType | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<TabKey>('soul');

  const fetchAgent = async () => {
    if (!id) return;
    setLoading(true);
    try { setAgent(await api.getAgent(id)); } finally { setLoading(false); }
  };

  useEffect(() => { fetchAgent(); }, [id]);

  if (loading || !agent) return <p className="p-6 text-zinc-400">Loading...</p>;

  const currentDoc = activeTab !== 'config' ? agent.documents[activeTab] : null;

  const handleSaveDoc = async (content: string, message: string) => {
    if (!id || activeTab === 'config') return;
    await api.updateDocument(id, activeTab, content, message);
    await fetchAgent();
  };

  const handleSaveConfig = async (config: Record<string, unknown>) => {
    if (!id) return;
    await api.updateAgent(id, { config });
    await fetchAgent();
  };

  return (
    <div className="max-w-6xl mx-auto p-6">
      <div className="flex items-center gap-3 mb-6">
        <button className="text-zinc-400 hover:text-zinc-200" onClick={() => navigate('/agents')}>← Back</button>
        <span className="text-2xl">{agent.emoji || '🤖'}</span>
        <div>
          <h1 className="text-xl font-bold text-zinc-100">{agent.display_name}</h1>
          <p className="text-sm text-zinc-400">{agent.name}</p>
        </div>
      </div>

      <div className="flex border-b border-zinc-700 mb-4">
        {DOC_TABS.map((tab) => (
          <button key={tab.key}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeTab === tab.key ? 'border-blue-500 text-blue-400' : 'border-transparent text-zinc-400 hover:text-zinc-200'
            }`}
            onClick={() => setActiveTab(tab.key)}>
            {tab.label}
          </button>
        ))}
      </div>

      <div className="flex gap-4" style={{ height: 'calc(100vh - 220px)' }}>
        <div className="flex-1">
          {activeTab === 'config' ? (
            <ConfigEditor config={agent.config} onSave={handleSaveConfig} />
          ) : (
            <DocumentEditor key={`${activeTab}-${currentDoc?.version}`} content={currentDoc?.content || ''} onSave={handleSaveDoc} />
          )}
        </div>
        {activeTab !== 'config' && currentDoc && (
          <div className="w-72 overflow-auto">
            <VersionHistory agentId={agent.id} docType={activeTab} currentVersion={currentDoc.version} onRollback={fetchAgent} />
          </div>
        )}
      </div>
    </div>
  );
}
