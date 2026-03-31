import { useState } from 'react';

interface Props {
  content: string;
  onSave: (content: string, message: string) => Promise<void>;
}

export function DocumentEditor({ content, onSave }: Props) {
  const [text, setText] = useState(content);
  const [message, setMessage] = useState('');
  const [saving, setSaving] = useState(false);
  const [preview, setPreview] = useState(false);
  const dirty = text !== content;

  const handleSave = async () => {
    setSaving(true);
    try { await onSave(text, message); setMessage(''); } finally { setSaving(false); }
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-2 mb-2">
        <button className={`px-3 py-1 rounded text-sm ${!preview ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-400'}`}
          onClick={() => setPreview(false)}>Edit</button>
        <button className={`px-3 py-1 rounded text-sm ${preview ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-400'}`}
          onClick={() => setPreview(true)}>Preview</button>
      </div>
      {preview ? (
        <pre className="flex-1 bg-zinc-900 border border-zinc-700 rounded p-4 overflow-auto whitespace-pre-wrap text-sm text-zinc-300">{text}</pre>
      ) : (
        <textarea value={text} onChange={(e) => setText(e.target.value)}
          className="flex-1 bg-zinc-900 border border-zinc-700 rounded p-4 text-sm text-zinc-100 font-mono resize-none focus:outline-none focus:border-zinc-500"
          spellCheck={false} />
      )}
      {dirty && (
        <div className="flex items-center gap-2 mt-3">
          <input placeholder="Version note (optional)" value={message} onChange={(e) => setMessage(e.target.value)}
            className="flex-1 bg-zinc-800 border border-zinc-600 rounded px-3 py-2 text-sm text-zinc-100" />
          <button className="bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded text-sm disabled:opacity-50"
            onClick={handleSave} disabled={saving}>{saving ? 'Saving...' : 'Save'}</button>
          <button className="bg-zinc-700 hover:bg-zinc-600 text-zinc-300 px-4 py-2 rounded text-sm"
            onClick={() => setText(content)}>Discard</button>
        </div>
      )}
    </div>
  );
}
