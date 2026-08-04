"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import type { Session } from "@supabase/supabase-js";
import { AuthBar } from "../components/AuthBar";
import { getAccessToken } from "../lib/supabase";

type Verdict = "Driver" | "Passenger" | "Insufficient evidence";

type Evidence = {
  id: string;
  category: string;
  title: string;
  summary: string;
  source_name: string;
  source_url: string;
  quality: string;
  stance: string;
  citation?: string;
};

type Result = {
  gene: string;
  verdict: Verdict;
  confidence: number;
  recommended_direction: string;
  executive_summary: string;
  driver_case: string[];
  passenger_case: string[];
  next_experiments: string[];
  limitations: string[];
  scorecard: {
    causality: { value: number };
    actionability: { value: number };
    evidence_quality: { value: number };
    contradiction_penalty: number;
    independent_pillars: number;
    evidence_count: number;
    scoring_version: string;
  };
  evidence: Evidence[];
};

const demo: Result[] = [
  {
    gene: "IL4R",
    verdict: "Driver",
    confidence: 95,
    recommended_direction: "inhibit",
    executive_summary:
      "Colocalization + cis-pQTL Mendelian randomization, direct perturbation, and target-engaging clinical evidence converge on IL4R as a causal driver of atopic dermatitis.",
    driver_case: [
      "Cis-pQTL Mendelian randomization supports a causal IL4R effect on disease direction",
      "Skin eQTL colocalization ties the disease locus to IL4R regulation, not a neighbor",
      "Target-engaging therapy (dupilumab) improves clinical disease in randomized trials",
      "Blocking IL-4R\u03b1 suppresses type 2 inflammatory signaling from both IL-4 and IL-13",
    ],
    passenger_case: [
      "Expression is contextual evidence, not causal proof",
      "Pathway genetics does not uniquely assign every signal to IL4R",
    ],
    next_experiments: [
      "Confirm response markers in disease-relevant primary skin cells",
      "Measure pathway rescue after orthogonal IL4R perturbation",
    ],
    limitations: ["Research-use-only prioritization; not clinical validation."],
    scorecard: {
      causality: { value: 94 },
      actionability: { value: 100 },
      evidence_quality: { value: 91 },
      contradiction_penalty: 0,
      independent_pillars: 5,
      evidence_count: 6,
      scoring_version: "1.1.0",
    },
    evidence: [
      { id: "il4r-mr", category: "mendelian_randomization", title: "Cis-pQTL Mendelian randomization supports a causal IL4R effect", summary: "Instrumenting IL-4R\u03b1 with cis-pQTLs yields a disease-direction consistent effect on AD, mirroring pharmacology.", source_name: "Open Targets Genetics", source_url: "https://genetics.opentargets.org/study/GCST90014324", quality: "high", stance: "supports" },
      { id: "il4r-coloc", category: "colocalization", title: "Skin eQTL colocalizes with the AD GWAS signal at IL4R", summary: "High-posterior colocalization links the disease-associated locus to IL4R regulation in disease-relevant tissue.", source_name: "Open Targets Genetics", source_url: "https://genetics.opentargets.org/gene/ENSG00000077238", quality: "high", stance: "supports" },
      { id: "il4r-clinical", category: "clinical_pharmacology", title: "Target-engaging therapy improves clinical disease", summary: "Dupilumab blocks IL-4R\u03b1 and demonstrated efficacy in randomized atopic dermatitis trials.", source_name: "PubMed", source_url: "https://pubmed.ncbi.nlm.nih.gov/27690741/", citation: "PMID: 27690741", quality: "high", stance: "supports" },
      { id: "il4r-perturb", category: "causal_perturbation", title: "Blocking IL-4R\u03b1 suppresses type 2 inflammatory signaling", summary: "Direct target perturbation blocks signaling from both IL-4 and IL-13.", source_name: "PubMed", source_url: "https://pubmed.ncbi.nlm.nih.gov/29045222/", citation: "PMID: 29045222", quality: "high", stance: "supports" },
      { id: "il4r-genetics", category: "human_genetics", title: "Human genetic association supports the pathway", summary: "Target-level human genetics supports involvement of the IL-4/IL-13 axis.", source_name: "Open Targets", source_url: "https://platform.opentargets.org/target/ENSG00000077238/associations", quality: "high", stance: "supports" },
      { id: "il4r-mechanism", category: "mechanistic_coherence", title: "Mechanism is coherent in skin", summary: "IL-4R\u03b1 integrates signaling that affects epidermal barrier and type 2 inflammation.", source_name: "Reactome", source_url: "https://reactome.org/content/detail/R-HSA-6785807", quality: "high", stance: "supports" },
    ],
  },
  {
    gene: "FLG",
    verdict: "Insufficient evidence",
    confidence: 69,
    recommended_direction: "activate",
    executive_summary:
      "FLG has compelling causal biology, but BioLead abstains: direct, tractable intervention evidence is not yet sufficient to classify it.",
    driver_case: [
      "Loss-of-function variants strongly increase disease risk",
      "Barrier biology is directly relevant to skin disease",
    ],
    passenger_case: [
      "Reduced expression may partly reflect inflammatory state",
      "No target-engaging clinical rescue evidence in the dossier",
    ],
    next_experiments: [
      "Test feasible filaggrin-restoration strategies in organotypic skin",
      "Quantify barrier rescue independently from inflammation reduction",
    ],
    limitations: ["Actionability is distinct from causal relevance."],
    scorecard: {
      causality: { value: 47 },
      actionability: { value: 14 },
      evidence_quality: { value: 87 },
      contradiction_penalty: 6,
      independent_pillars: 2,
      evidence_count: 3,
      scoring_version: "1.1.0",
    },
    evidence: [
      { id: "flg-genetics", category: "human_genetics", title: "Loss-of-function variants strongly increase disease risk", summary: "FLG loss-of-function is a replicated human genetic risk factor.", source_name: "PubMed", source_url: "https://pubmed.ncbi.nlm.nih.gov/16550169/", citation: "PMID: 16550169", quality: "high", stance: "supports" },
      { id: "flg-mr-gap", category: "mendelian_randomization", title: "No tractable MR instrument for filaggrin restoration", summary: "Positive-direction MR for barrier-restoring intervention is not established; loss-of-function dominates the genetic signal.", source_name: "Open Targets Genetics", source_url: "https://genetics.opentargets.org/gene/ENSG00000143631", quality: "moderate", stance: "contradicts" },
      { id: "flg-mechanism", category: "mechanistic_coherence", title: "Barrier biology is directly relevant to skin disease", summary: "Filaggrin is central to epidermal differentiation and barrier integrity.", source_name: "UniProt", source_url: "https://www.uniprot.org/uniprotkb/P20930/entry", quality: "high", stance: "supports" },
    ],
  },
  {
    gene: "S100A8",
    verdict: "Passenger",
    confidence: 63,
    recommended_direction: "unresolved",
    executive_summary:
      "S100A8 is passenger-like: inflammatory-state association is strong, but direct causal and phenotype-rescue evidence is missing.",
    driver_case: ["Strong inflammatory-state up-regulation"],
    passenger_case: [
      "No disease-relevant perturbational rescue identified",
      "No direct causal human genetic assignment identified",
    ],
    next_experiments: [
      "Perturb S100A8 in primary skin cells and measure phenotype rescue",
      "Separate biomarker response from upstream disease modification",
    ],
    limitations: ["A missing public result is not proof that evidence does not exist."],
    scorecard: {
      causality: { value: 0 },
      actionability: { value: 0 },
      evidence_quality: { value: 59 },
      contradiction_penalty: 15,
      independent_pillars: 0,
      evidence_count: 2,
      scoring_version: "1.1.0",
    },
    evidence: [
      { id: "s100a8-expression", category: "differential_expression", title: "Strong inflammatory-state up-regulation", summary: "Elevation establishes association with disease state, not causal direction.", source_name: "Europe PMC", source_url: "https://europepmc.org/search?query=S100A8%20atopic%20dermatitis", quality: "high", stance: "supports" },
      { id: "s100a8-counter", category: "causal_perturbation", title: "No disease-relevant rescue evidence identified", summary: "The search did not identify direct human skin perturbation evidence.", source_name: "BioLead evidence gap", source_url: "https://europepmc.org/search?query=S100A8%20atopic%20dermatitis%20inhibition", quality: "moderate", stance: "contradicts" },
    ],
  },
];

const CAT: Record<string, string> = {
  mendelian_randomization: "MR",
  colocalization: "Coloc",
  human_genetics: "Genetics",
  causal_perturbation: "Perturbation",
  clinical_pharmacology: "Clinical",
  mechanistic_coherence: "Mechanism",
  differential_expression: "Expression",
  literature: "Literature",
};

type ChainEdge = {
  key: string;
  label: string;
  hint: string;
  categories: string[];
};

const CAUSAL_CHAIN: ChainEdge[] = [
  {
    key: "variant-gene",
    label: "Variant → Gene",
    hint: "MR / colocalization identifies the causal gene at the locus",
    categories: ["mendelian_randomization", "colocalization", "human_genetics"],
  },
  {
    key: "gene-disease",
    label: "Gene → Disease",
    hint: "Human genetics + direct perturbation change phenotype",
    categories: ["human_genetics", "causal_perturbation"],
  },
  {
    key: "gene-rescue",
    label: "Gene → Rescue",
    hint: "Target-engaging intervention improves disease",
    categories: ["clinical_pharmacology", "causal_perturbation"],
  },
  {
    key: "mechanism",
    label: "Mechanism",
    hint: "How the target acts in disease-relevant tissue",
    categories: ["mechanistic_coherence"],
  },
];

const STAGES = [
  { id: "retrieve", label: "Retrieve", detail: "Pulling genetics, literature, and clinical sources" },
  { id: "extract", label: "Extract", detail: "Normalizing evidence into causal pillars" },
  { id: "score", label: "Score", detail: "Applying deterministic causal rubric" },
  { id: "falsify", label: "Falsify", detail: "Advocate vs falsifier ensemble vote" },
  { id: "decide", label: "Decide", detail: "Merging votes under scientific guardrails" },
] as const;

function formatLatency(ms: number) {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function tone(v: Verdict) {
  if (v === "Driver") return "pos";
  if (v === "Passenger") return "neg";
  return "warn";
}

function Arc({ value, r, strokeWidth }: { value: number; r: number; strokeWidth: number }) {
  const c = 2 * Math.PI * r;
  return (
    <circle
      r={r}
      cx="50%"
      cy="50%"
      fill="none"
      className="arc-fill"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeDasharray={c}
      strokeDashoffset={c - (c * Math.min(100, Math.max(0, value))) / 100}
      transform={`rotate(-90 ${r + strokeWidth / 2} ${r + strokeWidth / 2})`}
    />
  );
}

function Gauge({ value, size, label }: { value: number; size: number; label?: string }) {
  const sw = size > 100 ? 9 : 4;
  const r = (size - sw) / 2;
  const d = size;
  return (
    <div className="gauge">
      <svg width={d} height={d} viewBox={`0 0 ${d} ${d}`}>
        <circle cx="50%" cy="50%" r={r} fill="none" stroke="var(--ring-track)" strokeWidth={sw} />
        <Arc value={value} r={r} strokeWidth={sw} />
      </svg>
      <div className="gauge-inner">
        <strong>{value}</strong>
        {label && <span>{label}</span>}
      </div>
    </div>
  );
}

function Bar({ label, value }: { label: string; value: number }) {
  return (
    <div className="bar-meter">
      <div className="bar-label"><span>{label}</span><strong>{value}</strong></div>
      <div className="bar-track"><div className="bar-fill" style={{ width: `${value}%` }} /></div>
    </div>
  );
}

function CausalChain({ evidence }: { evidence: Evidence[] }) {
  const supportByCategory = new Map<string, number>();
  const contradictByCategory = new Map<string, number>();
  for (const item of evidence) {
    const map = item.stance === "contradicts" ? contradictByCategory : supportByCategory;
    map.set(item.category, (map.get(item.category) ?? 0) + 1);
  }
  return (
    <div className="chain" data-testid="causal-chain">
      <div className="chain-title">
        <span>Causal chain</span>
        <em>Variant → Gene → Disease → Rescue</em>
      </div>
      <div className="chain-row">
        {CAUSAL_CHAIN.map((edge, idx) => {
          const support = edge.categories.reduce((a, c) => a + (supportByCategory.get(c) ?? 0), 0);
          const contra = edge.categories.reduce((a, c) => a + (contradictByCategory.get(c) ?? 0), 0);
          const state = support > 0 ? "on" : contra > 0 ? "warn" : "off";
          return (
            <div key={edge.key} className="chain-cell">
              <div className={`chain-node state-${state}`} title={edge.hint}>
                <span className="chain-label">{edge.label}</span>
                <span className="chain-meta">
                  {support > 0 ? `${support} support` : contra > 0 ? `${contra} counter` : "no evidence"}
                </span>
              </div>
              {idx < CAUSAL_CHAIN.length - 1 && <span className="chain-link" aria-hidden="true" />}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function TriMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 28 28" width="28" height="28" className={className}>
      <path d="M6 24 L14 4 L22 24Z" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
      <circle cx="14" cy="16" r="2.2" fill="currentColor" />
    </svg>
  );
}

export default function Home() {
  const [results, setResults] = useState<Result[]>(demo);
  const [activeGene, setActiveGene] = useState("IL4R");
  const [genes, setGenes] = useState("IL4R, FLG, S100A8");
  const [disease, setDisease] = useState("Atopic dermatitis");
  const [mode, setMode] = useState<"demo" | "live">("demo");
  const [running, setRunning] = useState(false);
  const [stage, setStage] = useState(0);
  const [elapsedMs, setElapsedMs] = useState(0);
  const [lastLatencyMs, setLastLatencyMs] = useState<number | null>(null);
  const [notice, setNotice] = useState("Seeded, reproducible evidence snapshot");
  const [tab, setTab] = useState<"evidence" | "args">("evidence");
  const [theme, setTheme] = useState<"dark" | "light">("light");
  const [session, setSession] = useState<Session | null>(null);
  const [stats, setStats] = useState<string | null>(null);

  const onSessionChange = useCallback((next: Session | null) => {
    setSession(next);
  }, []);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    document.documentElement.style.colorScheme = theme;
  }, [theme]);

  useEffect(() => {
    if (!session) {
      setStats(null);
      return;
    }
    let cancelled = false;
    (async () => {
      const token = session.access_token;
      try {
        const res = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/analytics?mine=true`,
          { headers: { Authorization: `Bearer ${token}` } },
        );
        if (!res.ok || cancelled) return;
        const data = await res.json();
        if (cancelled || !data.enabled) return;
        const drivers = data.verdict_counts?.Driver ?? 0;
        setStats(`${data.total_runs} of your runs · ${drivers} Driver calls`);
      } catch {
        if (!cancelled) setStats(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [session, notice]);

  const active = useMemo(
    () => results.find((r) => r.gene === activeGene) ?? results[0],
    [results, activeGene],
  );

  useEffect(() => {
    if (!running) return;
    setStage(0);
    setElapsedMs(0);
    const started = performance.now();
    const tick = setInterval(() => {
      setElapsedMs(Math.max(0, Math.round(performance.now() - started)));
    }, 50);
    // Stage advance is visual pacing; real request duration drives the timer.
    const advance = setInterval(() => {
      setStage((c) => (c >= STAGES.length - 1 ? c : c + 1));
    }, 900);
    return () => {
      clearInterval(tick);
      clearInterval(advance);
    };
  }, [running]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.target as HTMLElement)?.tagName === "INPUT") return;
      const d = Number.parseInt(e.key, 10);
      if (d >= 1 && d <= results.length) setActiveGene(results[d - 1].gene);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [results]);

  async function run(e: FormEvent) {
    e.preventDefault();
    const started = performance.now();
    setRunning(true);
    setLastLatencyMs(null);
    setNotice("Collecting and scoring evidence\u2026");
    try {
      const token = await getAccessToken();
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (token) headers.Authorization = `Bearer ${token}`;
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/analyze`,
        {
          method: "POST",
          headers,
          body: JSON.stringify({
            disease,
            genes: genes.split(",").map((g) => g.trim()).filter(Boolean),
            tissue: "skin",
            intervention_direction: "unknown",
            mode,
          }),
        },
      );
      if (!res.ok) throw new Error();
      const data = await res.json();
      setResults(data.results);
      setActiveGene(data.results[0]?.gene ?? "");
      const ms = Math.round(performance.now() - started);
      setLastLatencyMs(ms);
      const who = session?.user?.email ? ` · ${session.user.email}` : "";
      setNotice(`${mode === "live" ? "Live" : "Seeded"} run \u00b7 ${data.run_id.slice(0, 8)} · ${(ms / 1000).toFixed(1)}s${who}`);
    } catch {
      const ms = Math.round(performance.now() - started);
      setLastLatencyMs(ms);
      setResults(demo);
      setActiveGene("IL4R");
      setNotice(`Backend unavailable \u2014 offline demo · ${(ms / 1000).toFixed(1)}s`);
    } finally {
      setRunning(false);
      setStage(STAGES.length);
    }
  }

  function exportJSON() {
    const blob = new Blob([JSON.stringify({ disease, results }, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `biolead-${disease.toLowerCase().replaceAll(" ", "-")}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const t = active ? tone(active.verdict) : "warn";
  const sc = active?.scorecard;

  return (
    <div className={`shell tone-${t}`}>
      {/* ---- Atmosphere ---- */}
      <div className="atmos" aria-hidden="true">
        <span className="blob blob-1" />
        <span className="blob blob-2" />
        <span className="blob blob-3" />
        <span className="grid-overlay" />
      </div>

      {/* ---- Top nav ---- */}
      <nav>
        <div className="nav-left">
          <div className="logomark">
            <svg viewBox="0 0 28 28" width="24" height="24"><path d="M6 24 L14 4 L22 24Z" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" /><circle cx="14" cy="16" r="2.8" fill="currentColor" /></svg>
          </div>
          <span className="wordmark">BioLead <em>Evidence Workbench</em></span>
        </div>
        <div className="nav-right">
          <span className="badge">Research use only</span>
          {stats && <span className="badge auth-stats" data-testid="auth-stats">{stats}</span>}
          <AuthBar onSessionChange={onSessionChange} />
          <button type="button" className="btn-ghost" onClick={exportJSON}>Export</button>
          <button
            type="button"
            className="btn-theme"
            aria-label="Toggle theme"
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          >
            {theme === "dark" ? (
              <svg viewBox="0 0 20 20" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="10" cy="10" r="4" /><path d="M10 2v2m0 12v2m-6.93-3.07 1.41-1.41m9.9-9.9 1.41-1.41M2 10h2m12 0h2M4.93 4.93l1.41 1.41m9.9 9.9 1.41 1.41" /></svg>
            ) : (
              <svg viewBox="0 0 20 20" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M17.293 13.293A8 8 0 016.707 2.707a8.003 8.003 0 1010.586 10.586z" /></svg>
            )}
          </button>
        </div>
      </nav>

      {/* ---- Hero ---- */}
      <header>
        <div className="hero-badge"><span className="pulse-dot" />Causal gene prioritization</div>
        <h1>
          Driver, passenger,&nbsp;or<br />
          <span className="shimmer">insufficient evidence?</span>
        </h1>

        <form className="input-bar" onSubmit={run}>
          <div className="field">
            <label>Disease</label>
            <input value={disease} onChange={(e) => setDisease(e.target.value)} />
          </div>
          <div className="divider" />
          <div className="field grow">
            <label>Candidate genes</label>
            <input value={genes} onChange={(e) => setGenes(e.target.value.toUpperCase())} />
          </div>
          <div className="toggle">
            <button type="button" className={mode === "demo" ? "on" : ""} onClick={() => setMode("demo")}>Demo</button>
            <button type="button" className={mode === "live" ? "on" : ""} onClick={() => setMode("live")}>Live</button>
          </div>
          <button type="submit" className="btn-run" disabled={running} data-testid="run-analysis">
            {running ? "Analyzing\u2026" : "Run analysis"}
          </button>
        </form>

        <div className={`progress-shell ${running ? "live" : ""}`} data-testid="run-progress">
          <div className="progress-head">
            <div className="progress-copy">
              <span className="progress-kicker">{running ? "Agent pipeline" : "Last run"}</span>
              <strong>
                {running
                  ? STAGES[Math.min(stage, STAGES.length - 1)].detail
                  : notice}
              </strong>
            </div>
            <div className="progress-latency" aria-live="polite">
              <span className="latency-label">{running ? "Elapsed" : "Latency"}</span>
              <span className="latency-value" data-testid="run-latency">
                {formatLatency(running ? elapsedMs : (lastLatencyMs ?? 0))}
              </span>
            </div>
          </div>

          <div className="progress-track" aria-hidden="true">
            <div
              className="progress-fill"
              style={{
                width: `${running
                  ? Math.min(96, ((stage + 0.35) / STAGES.length) * 100)
                  : stage >= STAGES.length
                    ? 100
                    : 0}%`,
              }}
            />
            <div className="progress-glow" />
          </div>

          <div className="progress-stages">
            {STAGES.map((s, i) => {
              const done = stage > i || (!running && stage >= STAGES.length);
              const now = running && stage === i;
              return (
                <div key={s.id} className={`progress-stage ${done ? "done" : ""} ${now ? "now" : ""}`}>
                  <span className="stage-dot"><i /></span>
                  <span className="stage-label">{s.label}</span>
                </div>
              );
            })}
          </div>
          <p className="run-status" data-testid="run-notice">{notice}</p>
        </div>
      </header>

      {/* ---- Candidates ---- */}
      <section className="section">
        <div className="section-title">
          <h2>Candidates</h2>
        </div>
        <div className="cand-row">
          {results.map((r, i) => {
            const ct = tone(r.verdict);
            const sel = r.gene === active?.gene;
            return (
              <button key={r.gene} className={`cand tone-${ct} ${sel ? "sel" : ""}`} data-testid={`gene-select-${r.gene}`} onClick={() => setActiveGene(r.gene)}>
                <div className="cand-border" />
                <div className="cand-inner">
                  <div className="cand-head">
                    <h3>{r.gene}</h3>
                    <span className={`verdict-chip tone-${ct}`}>{r.verdict}</span>
                  </div>
                  <div className="cand-stats">
                    <div><dt>Causality</dt><dd>{r.scorecard.causality.value}</dd></div>
                    <div><dt>Action.</dt><dd>{r.scorecard.actionability.value}</dd></div>
                    <div><dt>Quality</dt><dd>{r.scorecard.evidence_quality.value}</dd></div>
                  </div>
                  <div className="cand-foot">
                    <span>{sel ? "Viewing" : "View dossier"}</span>
                    <kbd>{i + 1}</kbd>
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </section>

      {/* ---- Dossier ---- */}
      {active && (
        <section className="dossier">
          <div className="dossier-border" />
          <div className="dossier-inner">
            {/* Header */}
            <div className="dos-head">
              <div className="dos-info">
                <p className="dos-eyebrow">{disease} &middot; Skin</p>
                <div className="dos-title">
                  <h2 data-testid="active-gene">{active.gene}</h2>
                  <span className={`verdict-chip lg tone-${t}`} data-testid="active-verdict">{active.verdict}</span>
                </div>
                <p className="dos-summary">{active.executive_summary}</p>
                <div className="dos-chips">
                  <span className="chip">Direction &middot; <b>{active.recommended_direction}</b></span>
                  <span className="chip">{sc?.independent_pillars} causal pillars</span>
                  <span className="chip">{sc?.evidence_count} evidence items</span>
                  {(sc?.contradiction_penalty ?? 0) > 0 && <span className="chip alert">&minus;{sc?.contradiction_penalty} contradiction</span>}
                </div>
              </div>
              <div className="dos-gauge">
                <Gauge value={active.confidence} size={164} label="confidence" />
              </div>
            </div>

            {/* Scores */}
            <div className="dos-scores">
              <Bar label="Causality" value={sc?.causality.value ?? 0} />
              <Bar label="Actionability" value={sc?.actionability.value ?? 0} />
              <Bar label="Evidence quality" value={sc?.evidence_quality.value ?? 0} />
            </div>

            <CausalChain evidence={active.evidence} />

            {/* Tabs */}
            <div className="tabs" role="tablist">
              {([["evidence", `Evidence (${active.evidence.length})`], ["args", "For & against"]] as const).map(([id, label]) => (
                <button key={id} role="tab" className={tab === id ? "on" : ""} onClick={() => setTab(id)}>{label}</button>
              ))}
            </div>

            <div className="tab-content">
              {tab === "evidence" && (
                <div className="ev-grid">
                  {active.evidence.map((ev) => (
                    <a key={ev.id} href={ev.source_url} target="_blank" rel="noreferrer" className="ev-card">
                      <div className="ev-top">
                        <span className={`ev-icon ${ev.stance}`}>{ev.stance === "supports" ? "+" : "\u2212"}</span>
                        <span className="ev-type">{CAT[ev.category] ?? ev.category}</span>
                        <span className="ev-qual">{ev.quality}</span>
                      </div>
                      <strong>{ev.title}</strong>
                      <p>{ev.summary}</p>
                      <span className="ev-cite">{ev.citation ?? ev.source_name} \u2197</span>
                    </a>
                  ))}
                </div>
              )}

              {tab === "args" && (
                <div className="args-grid">
                  <div className="arg-col for">
                    <h4><span className="arg-dot for" />Case for driver</h4>
                    <ul>{active.driver_case.map((c) => <li key={c}>{c}</li>)}</ul>
                  </div>
                  <div className="arg-col against">
                    <h4><span className="arg-dot against" />Falsification</h4>
                    <ul>{active.passenger_case.map((c) => <li key={c}>{c}</li>)}</ul>
                  </div>
                </div>
              )}
            </div>
          </div>
        </section>
      )}

      <footer>
        <span>BioLead &middot; source-linked &middot; contradiction-aware &middot; abstention-first</span>
        <span>v{sc?.scoring_version ?? "1.0.0"}</span>
      </footer>
    </div>
  );
}
