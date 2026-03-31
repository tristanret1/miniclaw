import { useState } from 'react';

interface Props {
  config: Record<string, unknown>;
  onSave: (config: Record<string, unknown>) => Promise<void>;
}

export function ConfigEditor({ config, onSave }: Props) {
  const [text, setText] = useState(JSON.stringify(config, null, 2));
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const original = JSON.stringify(config, null, 2);
  const dirty = text !== original;

  const handleSave = async () => {
    try {
      const parsed = JSON.parse(text);
      setError('');
      setSaving(true);
      await onSave(parsed);
    } catch (e) {
      setError(e instanceof SyntaxError ? `Invalid JSON: ${e.message}` : String(e));
    } finally { setSaving(false); }
  };

  return (
    <div className="flex flex-col h-full">
      <textarea value={text} onChange={(e) => { setText(e.target.value); setError(''); }}
        className="flex-1 bg-zinc-900 border border-zinc-700 rounded p-4 text-sm text-zinc-100 font-mono resize-none focus:outline-none focus:border-zinc-500"
        spellCheck={false} />
      {error && <p className="text-red-400 text-sm mt-2">{error}</p>}
      {dirty && (
        <div className="flex gap-2 mt-3">
          <button className="bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded text-sm disabled:opacity-50"
            onClick={handleSave} disabled={saving}>{saving ? 'Saving...' : 'Save Config'}</button>
          <button className="bg-zinc-700 hover:bg-zinc-600 text-zinc-300 px-4 py-2 rounded text-sm"
            onClick={() => { setText(original); setError(''); }}>Discard</button>
        </div>
      )}
    </div>
  );
}
