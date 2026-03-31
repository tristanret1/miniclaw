import { useEffect, useState } from 'react';
import { api, DocumentVersion } from '../lib/api';

interface Props {
  agentId: string;
  docType: string;
  currentVersion: number;
  onRollback: () => void;
}

export function VersionHistory({ agentId, docType, currentVersion, onRollback }: Props) {
  const [history, setHistory] = useState<DocumentVersion[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<number | null>(null);

  useEffect(() => {
    setLoading(true);
    api.getDocumentHistory(agentId, docType).then(setHistory).finally(() => setLoading(false));
  }, [agentId, docType, currentVersion]);

  const handleRollback = async (version: number) => {
    if (!confirm(`Rollback to v${version}? This creates a new version.`)) return;
    await api.rollbackDocument(agentId, docType, version);
    onRollback();
  };

  if (loading) return <p className="text-zinc-400 text-sm p-2">Loading history...</p>;

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-semibold text-zinc-300 mb-2">Version History</h3>
      {history.map((v) => (
        <div key={v.id}
          className={`border rounded p-2 text-sm cursor-pointer transition-colors ${
            v.version === currentVersion ? 'border-blue-600 bg-blue-950' : 'border-zinc-700 bg-zinc-900 hover:border-zinc-500'
          }`}
          onClick={() => setExpandedId(expandedId === v.id ? null : v.id)}>
          <div className="flex justify-between items-center">
            <span className="text-zinc-100 font-medium">v{v.version}</span>
            <span className="text-zinc-500 text-xs">{new Date(v.created_at).toLocaleString()}</span>
          </div>
          {v.message && <p className="text-zinc-400 text-xs mt-1">{v.message}</p>}
          {expandedId === v.id && (
            <div className="mt-2">
              <pre className="bg-zinc-800 rounded p-2 text-xs text-zinc-300 max-h-48 overflow-auto whitespace-pre-wrap">{v.content}</pre>
              {v.version !== currentVersion && (
                <button className="mt-2 text-xs text-blue-400 hover:text-blue-300"
                  onClick={(e) => { e.stopPropagation(); handleRollback(v.version); }}>
                  Rollback to this version
                </button>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
