import { useState } from 'react';

interface Props {
  config: Record<string, unknown>;
  onSave: (config: Record<string, unknown>) => Promise<void>;
}

const ANTHROPIC_MODELS = [
  'claude-opus-4-6',
  'claude-sonnet-4-20250514',
  'claude-haiku-4-5-20251001',
];

const CODEX_MODELS = [
  'gpt-5.3-codex',
  'gpt-5.2-codex',
  'gpt-5.1-codex',
  'gpt-5.1-codex-mini',
  'gpt-5.1-codex-max',
];

type View = 'form' | 'json';

// Deep get/set helpers for nested config
function deepGet(obj: Record<string, unknown>, path: string): unknown {
  return path.split('.').reduce((o: unknown, k) => (o as Record<string, unknown>)?.[k], obj);
}

function deepSet(obj: Record<string, unknown>, path: string, value: unknown): Record<string, unknown> {
  const clone = JSON.parse(JSON.stringify(obj));
  const keys = path.split('.');
  let cur = clone;
  for (let i = 0; i < keys.length - 1; i++) {
    if (cur[keys[i]] === undefined || cur[keys[i]] === null) cur[keys[i]] = {};
    cur = cur[keys[i]] as Record<string, unknown>;
  }
  cur[keys[keys.length - 1]] = value;
  return clone;
}

function Label({ children }: { children: React.ReactNode }) {
  return <label className="text-sm text-zinc-400 mb-1">{children}</label>;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <Label>{label}</Label>
      {children}
    </div>
  );
}

const inputCls = 'bg-zinc-800 border border-zinc-600 rounded px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-zinc-500';
const selectCls = inputCls + ' appearance-none';

export function ConfigEditor({ config, onSave }: Props) {
  const [draft, setDraft] = useState<Record<string, unknown>>(JSON.parse(JSON.stringify(config)));
  const [saving, setSaving] = useState(false);
  const [view, setView] = useState<View>('form');

  const dirty = JSON.stringify(draft) !== JSON.stringify(config);

  const get = (path: string) => deepGet(draft, path);
  const set = (path: string, value: unknown) => setDraft(deepSet(draft, path, value));

  const provider = (get('llm.provider') as string) || 'anthropic';
  const models = provider === 'codex' ? CODEX_MODELS : ANTHROPIC_MODELS;
  const modelPath = provider === 'codex' ? 'llm.codex.model' : 'llm.anthropic.model';
  const currentModel = (get(modelPath) as string) || models[0];

  const handleSave = async () => {
    setSaving(true);
    try { await onSave(draft); } finally { setSaving(false); }
  };

  return (
    <div className="flex flex-col h-full">
      {/* View toggle */}
      <div className="flex items-center gap-2 mb-3">
        <button
          className={`px-3 py-1 rounded text-sm ${view === 'form' ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-400'}`}
          onClick={() => setView('form')}
        >
          Settings
        </button>
        <button
          className={`px-3 py-1 rounded text-sm ${view === 'json' ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-400'}`}
          onClick={() => setView('json')}
        >
          JSON (read-only)
        </button>
      </div>

      {view === 'json' ? (
        <pre className="flex-1 bg-zinc-900 border border-zinc-700 rounded p-4 overflow-auto text-sm text-zinc-300 font-mono whitespace-pre-wrap select-all">
          {JSON.stringify(draft, null, 2)}
        </pre>
      ) : (
        <div className="flex-1 overflow-auto space-y-6 pr-2">
          {/* ── LLM ── */}
          <Section title="LLM">
            <div className="grid grid-cols-2 gap-4">
              <Field label="Provider">
                <select value={provider} onChange={(e) => set('llm.provider', e.target.value)} className={selectCls}>
                  <option value="anthropic">Anthropic (Claude)</option>
                  <option value="codex">Codex (OpenAI)</option>
                </select>
              </Field>
              <Field label="Model">
                <select value={currentModel} onChange={(e) => set(modelPath, e.target.value)} className={selectCls}>
                  {models.map((m) => <option key={m} value={m}>{m}</option>)}
                </select>
              </Field>
              <Field label="Max History">
                <input type="number" value={(get('llm.max_history') as number) ?? 50}
                  onChange={(e) => set('llm.max_history', parseInt(e.target.value) || 50)} className={inputCls} />
              </Field>
              <Field label="Max Tokens">
                <input type="number" value={(get('llm.max_tokens') as number) ?? 4096}
                  onChange={(e) => set('llm.max_tokens', parseInt(e.target.value) || 4096)} className={inputCls} />
              </Field>
              <Field label="Tools Enabled">
                <Toggle checked={!!get('llm.tools_enabled')} onChange={(v) => set('llm.tools_enabled', v)} />
              </Field>
            </div>
          </Section>

          {/* ── Discord ── */}
          <Section title="Discord">
            <div className="grid grid-cols-2 gap-4">
              <Field label="Bot Token">
                <input type="password" value={(get('discord.bot_token') as string) || ''}
                  onChange={(e) => set('discord.bot_token', e.target.value)} className={inputCls}
                  placeholder="Discord bot token" />
              </Field>
              <Field label="Greeting Channel ID">
                <input type="text" value={(get('discord.greeting_channel_id') as string) || ''}
                  onChange={(e) => set('discord.greeting_channel_id', e.target.value)} className={inputCls} />
              </Field>
              <Field label="Allowed DM Users">
                <input type="text" value={((get('discord.allowed_dm_users') as number[]) || []).join(', ')}
                  onChange={(e) => set('discord.allowed_dm_users',
                    e.target.value.split(',').map((s) => parseInt(s.trim())).filter((n) => !isNaN(n))
                  )} className={inputCls} placeholder="Comma-separated user IDs" />
              </Field>
            </div>

            <div className="mt-4">
              <h4 className="text-xs font-semibold text-zinc-500 uppercase tracking-wide mb-2">Auto Reply</h4>
              <div className="grid grid-cols-2 gap-4">
                <Field label="Enabled">
                  <Toggle checked={!!deepGet(draft, 'discord.auto_reply.enabled')}
                    onChange={(v) => set('discord.auto_reply.enabled', v)} />
                </Field>
                <Field label="Chance">
                  <input type="number" step="0.05" min="0" max="1"
                    value={(get('discord.auto_reply.chance') as number) ?? 0.1}
                    onChange={(e) => set('discord.auto_reply.chance', parseFloat(e.target.value) || 0)}
                    className={inputCls} />
                </Field>
              </div>
            </div>
          </Section>

          {/* ── Gateway ── */}
          <Section title="Gateway">
            <div className="grid grid-cols-2 gap-4">
              <Field label="Heartbeat Enabled">
                <Toggle checked={!!get('gateway.heartbeat.enabled')}
                  onChange={(v) => set('gateway.heartbeat.enabled', v)} />
              </Field>
              <Field label="Heartbeat Interval">
                <input type="text" value={(get('gateway.heartbeat.interval') as string) || '30m'}
                  onChange={(e) => set('gateway.heartbeat.interval', e.target.value)} className={inputCls}
                  placeholder="e.g. 30m, 1h" />
              </Field>
              <Field label="Heartbeat Channel ID">
                <input type="text" value={(get('gateway.heartbeat.channel_id') as string) || ''}
                  onChange={(e) => set('gateway.heartbeat.channel_id', e.target.value)} className={inputCls} />
              </Field>
              <Field label="Voice Enabled">
                <Toggle checked={!!get('gateway.voice.enabled')}
                  onChange={(v) => set('gateway.voice.enabled', v)} />
              </Field>
            </div>
          </Section>
        </div>
      )}

      {/* Save / Discard */}
      {dirty && (
        <div className="flex gap-2 mt-3 pt-3 border-t border-zinc-700">
          <button className="bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded text-sm disabled:opacity-50"
            onClick={handleSave} disabled={saving}>{saving ? 'Saving...' : 'Save Config'}</button>
          <button className="bg-zinc-700 hover:bg-zinc-600 text-zinc-300 px-4 py-2 rounded text-sm"
            onClick={() => setDraft(JSON.parse(JSON.stringify(config)))}>Discard</button>
        </div>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-zinc-200 mb-3 pb-1 border-b border-zinc-700">{title}</h3>
      {children}
    </div>
  );
}

function Toggle({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      type="button"
      className={`relative w-11 h-6 rounded-full transition-colors ${checked ? 'bg-blue-600' : 'bg-zinc-600'}`}
      onClick={() => onChange(!checked)}
    >
      <span className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform ${checked ? 'translate-x-5' : ''}`} />
    </button>
  );
}
