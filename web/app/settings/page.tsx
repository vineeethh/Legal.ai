"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, Info, XCircle } from "lucide-react";
import { api, type ModelInfo, type SettingsView } from "@/lib/api";
import { Button, Card, cn } from "@/components/ui";

const OPENROUTER = "https://openrouter.ai/api/v1";
const OLLAMA = "http://host.docker.internal:11434/v1";
const GEMINI = "https://generativelanguage.googleapis.com/v1beta/openai/";

const PROVIDERS = [
  {
    id: "openrouter",
    base: OPENROUTER,
    title: "OpenRouter",
    blurb: "One key, every model. Free models work for testing the plumbing; accurate extraction needs a capable (paid) model.",
    needsKey: true,
  },
  {
    id: "gemini",
    base: GEMINI,
    title: "Google Gemini",
    blurb: "Use gemini-2.0-flash or gemini-3.5-flash — confirmed working (20 req/day free cap). Avoid gemini-2.5-pro (0 free quota) and preview/\"antigravity\" models (no function-calling support at all).",
    needsKey: true,
  },
  {
    id: "ollama",
    base: OLLAMA,
    title: "Ollama (local)",
    blurb: "Free, unlimited, fully private — no key needed. Quality and speed depend on your hardware; prefer instruct models with tool support.",
    needsKey: false,
  },
  {
    id: "custom",
    base: "",
    title: "Custom endpoint",
    blurb: "Any OpenAI-compatible server (vLLM, LM Studio, llama.cpp, Together, Groq, ...).",
    needsKey: true,
  },
] as const;

export default function SettingsPage() {
  const [settings, setSettings] = useState<SettingsView | null>(null);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [form, setForm] = useState({ llm_model: "", validator_llm_model: "", llm_base_url: "", api_key: "" });
  const [saving, setSaving] = useState(false);
  const [test, setTest] = useState<{ ok: boolean; detail: string } | null>(null);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getSettings()
      .then((s) => {
        setSettings(s);
        setForm({
          llm_model: s.llm_model,
          validator_llm_model: s.validator_llm_model,
          llm_base_url: s.llm_base_url,
          api_key: "",
        });
      })
      .catch(() => setError("API unreachable — is docker compose up running?"));
    api.listModels().then(setModels).catch(() => {});
  }, []);

  const providerId = PROVIDERS.find((p) => p.base && p.base === form.llm_base_url)?.id ?? "custom";
  const needsKey = PROVIDERS.find((p) => p.id === providerId)?.needsKey ?? true;

  async function save() {
    setSaving(true);
    setError(null);
    setSaved(false);
    setTest(null);
    try {
      const patch: Record<string, unknown> = {
        llm_model: form.llm_model,
        validator_llm_model: form.validator_llm_model || form.llm_model,
        llm_base_url: form.llm_base_url,
      };
      if (form.api_key.trim()) patch.llm_api_key = form.api_key.trim();
      const next = await api.updateSettings(patch);
      setSettings(next);
      setForm((f) => ({ ...f, api_key: "" }));
      setSaved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save.");
    } finally {
      setSaving(false);
    }
  }

  async function runTest() {
    setTest(null);
    try {
      setTest(await api.testConnection());
    } catch (e) {
      setTest({ ok: false, detail: e instanceof Error ? e.message : "Test failed." });
    }
  }

  const freeToolModels = models.filter((m) => m.free && m.tools).slice(0, 8);

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="font-serif text-[34px] leading-[1.08] sm:text-[44px]">Settings</h1>
        <div className="rule-double mt-5" />
        <p className="mt-4 text-[13px] leading-relaxed text-muted">
          Bring your own key. Everything runs on your machine — keys are written only to your local{" "}
          <code className="font-mono text-xs">.env</code>, never displayed back, never sent anywhere else.
        </p>
      </div>

      {error ? (
        <div className="rounded-xl border border-danger/30 bg-danger-soft px-5 py-3 text-sm text-danger">{error}</div>
      ) : null}

      <Card className="px-6 py-5">
        <h3 className="font-serif text-lg">LLM provider</h3>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {PROVIDERS.map((p) => (
            <button
              key={p.id}
              onClick={() =>
                setForm((f) => ({ ...f, llm_base_url: p.id === "custom" ? f.llm_base_url : p.base }))
              }
              className={cn(
                "rounded-xl border p-4 text-left transition-all",
                providerId === p.id
                  ? "border-accent bg-accent-soft"
                  : "border-border bg-surface hover:border-border-strong",
              )}
            >
              <div className="text-sm font-semibold">{p.title}</div>
              <div className="mt-1 text-xs leading-relaxed text-muted">{p.blurb}</div>
            </button>
          ))}
        </div>

        <div className="mt-5 space-y-4">
          <label className="block">
            <span className="text-xs font-medium uppercase tracking-wide text-faint">Endpoint (OpenAI-compatible)</span>
            <input
              value={form.llm_base_url}
              onChange={(e) => setForm((f) => ({ ...f, llm_base_url: e.target.value }))}
              className="mt-1 w-full rounded-lg border border-border bg-surface px-3 py-2 font-mono text-sm focus:outline-2 focus:outline-accent"
            />
          </label>

          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block">
              <span className="text-xs font-medium uppercase tracking-wide text-faint">Extraction model</span>
              <input
                value={form.llm_model}
                onChange={(e) => setForm((f) => ({ ...f, llm_model: e.target.value }))}
                list="model-list"
                className="mt-1 w-full rounded-lg border border-border bg-surface px-3 py-2 font-mono text-sm focus:outline-2 focus:outline-accent"
              />
            </label>
            <label className="block">
              <span className="text-xs font-medium uppercase tracking-wide text-faint">
                Validator model <span className="normal-case">(blank = same)</span>
              </span>
              <input
                value={form.validator_llm_model}
                onChange={(e) => setForm((f) => ({ ...f, validator_llm_model: e.target.value }))}
                list="model-list"
                placeholder={form.llm_model}
                className="mt-1 w-full rounded-lg border border-border bg-surface px-3 py-2 font-mono text-sm focus:outline-2 focus:outline-accent"
              />
            </label>
            <datalist id="model-list">
              {models.map((m) => (
                <option key={m.id} value={m.id ?? ""} />
              ))}
            </datalist>
          </div>

          {needsKey ? (
            <label className="block">
              <span className="text-xs font-medium uppercase tracking-wide text-faint">
                API key {settings?.has_api_key ? `(saved ${settings.api_key_hint})` : "(required)"}
              </span>
              <input
                type="password"
                value={form.api_key}
                onChange={(e) => setForm((f) => ({ ...f, api_key: e.target.value }))}
                placeholder={settings?.has_api_key ? "leave blank to keep the saved key" : "paste your provider's API key"}
                autoComplete="off"
                className="mt-1 w-full rounded-lg border border-border bg-surface px-3 py-2 font-mono text-sm focus:outline-2 focus:outline-accent"
              />
            </label>
          ) : null}
        </div>

        <div className="mt-5 flex flex-wrap items-center gap-3">
          <Button onClick={save} disabled={saving || !form.llm_model || !form.llm_base_url}>
            {saving ? "Saving…" : "Save settings"}
          </Button>
          <Button variant="secondary" onClick={runTest}>
            Test connection
          </Button>
          {saved ? (
            <span className="flex items-center gap-1.5 text-sm text-success">
              <CheckCircle2 size={15} /> Saved — applies to the next run
            </span>
          ) : null}
          {test ? (
            <span className={cn("flex items-center gap-1.5 text-sm", test.ok ? "text-success" : "text-danger")}>
              {test.ok ? <CheckCircle2 size={15} /> : <XCircle size={15} />}
              {test.detail}
            </span>
          ) : null}
        </div>
      </Card>

      <Card className="px-6 py-5">
        <div className="flex items-start gap-3">
          <Info size={16} className="mt-0.5 shrink-0 text-accent" />
          <div className="text-sm leading-relaxed text-muted">
            <p className="font-medium text-foreground">Honest guidance on model choice</p>
            <p className="mt-1">
              This system refuses to ship anything it can&apos;t verify against a verbatim quote — so
              weak models don&apos;t produce wrong records, they produce <em>empty</em> ones. If every
              field comes back empty, it&apos;s one of three things: (1) the model doesn&apos;t
              support function/tool calling at all (structured output is mandatory here — check the{" "}
              <strong>Audit trail</strong> tab or a human-review banner on the document for the exact
              error), (2) you&apos;ve hit the provider&apos;s rate limit or quota, or (3) the model is
              real but too weak for our deeply-nested schemas. Always click{" "}
              <strong>Test connection</strong> below after changing models — it makes one real tool
              call and tells you immediately if (1) is the problem, instead of you finding out after a
              multi-minute run comes back empty.
            </p>
            <p className="mt-2">
              Known from direct testing: OpenRouter free models are capped at 50 requests/day and
              often can&apos;t reliably emit structured output. On Gemini,{" "}
              <code className="font-mono text-xs">gemini-2.0-flash</code> and{" "}
              <code className="font-mono text-xs">gemini-3.5-flash</code> work (20 requests/day free);{" "}
              <code className="font-mono text-xs">gemini-2.5-pro</code> has <em>zero</em> free quota;
              preview/experimental model names (e.g. anything with &quot;antigravity&quot; in it) often
              don&apos;t support function calling at all. For reliable extraction: a paid OpenRouter
              model (e.g. <code className="font-mono text-xs">openai/gpt-4o</code>, pennies
              per judgment), or a larger local instruct model (14B+) if your hardware can run it at a
              reasonable speed.
            </p>
            {freeToolModels.length > 0 ? (
              <p className="mt-2">
                Free, tool-capable models visible at your endpoint right now:{" "}
                {freeToolModels.map((m, i) => (
                  <code key={m.id} className="font-mono text-xs">
                    {m.id}
                    {i < freeToolModels.length - 1 ? ", " : ""}
                  </code>
                ))}
              </p>
            ) : null}
          </div>
        </div>
      </Card>

      {settings ? (
        <Card className="px-6 py-5 text-sm">
          <h3 className="font-serif text-lg">Pipeline thresholds</h3>
          <div className="tnum mt-3 grid grid-cols-2 gap-x-8 gap-y-2 text-muted sm:grid-cols-4">
            <div>
              <div className="text-xs uppercase tracking-wide text-faint">Auto-save ≥</div>
              {settings.confidence_autosave_threshold}
            </div>
            <div>
              <div className="text-xs uppercase tracking-wide text-faint">Review ≥</div>
              {settings.confidence_review_threshold}
            </div>
            <div>
              <div className="text-xs uppercase tracking-wide text-faint">Max retries</div>
              {settings.max_retries}
            </div>
            <div>
              <div className="text-xs uppercase tracking-wide text-faint">Concurrency</div>
              {settings.pipeline_max_concurrency === 0 ? "unlimited" : settings.pipeline_max_concurrency}
            </div>
          </div>
          <p className="mt-3 text-xs text-faint">
            Tunable via <code className="font-mono">.env</code> — see .env.example for the full surface.
          </p>
        </Card>
      ) : null}
    </div>
  );
}
