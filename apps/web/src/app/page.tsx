"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
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

function placeholderResult(gene: string, disease: string): Result {
  return {
    gene: gene.toUpperCase(),
    verdict: "Insufficient evidence",
    confidence: 40,
    recommended_direction: "unresolved",
    executive_summary: `Retrieving evidence for ${gene.toUpperCase()} × ${disease}. The dossier fills in after Retrieve → Extract → Score → Falsify → Decide.`,
    driver_case: [`Queued as a close analogue for this session (${gene.toUpperCase()} × ${disease}).`],
    passenger_case: ["Waiting on the pipeline — this is not a scored abstain yet."],
    next_experiments: [
      "Watch the workbench finish scoring before treating the chip as a verdict.",
    ],
    limitations: ["Placeholder card shown only while the run is in flight."],
    scorecard: {
      causality: { value: 12 },
      actionability: { value: 8 },
      evidence_quality: { value: 20 },
      contradiction_penalty: 0,
      independent_pillars: 0,
      evidence_count: 0,
      scoring_version: "1.1.0",
    },
    evidence: [],
  };
}

function toWorkbenchResult(row: Record<string, unknown>, disease: string): Result | null {
  const gene = String(row.gene || "").trim().toUpperCase();
  if (!gene) return null;
  const scorecard = (row.scorecard || {}) as Result["scorecard"];
  const verdict = row.verdict as Result["verdict"] | undefined;
  return {
    gene,
    verdict: verdict === "Driver" || verdict === "Passenger" ? verdict : "Insufficient evidence",
    confidence: Number(row.confidence) || 0,
    recommended_direction: String(row.recommended_direction || "unresolved"),
    executive_summary: String(row.executive_summary || `${gene} × ${disease}`),
    driver_case: Array.isArray(row.driver_case) ? row.driver_case.map(String) : [],
    passenger_case: Array.isArray(row.passenger_case) ? row.passenger_case.map(String) : [],
    next_experiments: Array.isArray(row.next_experiments) ? row.next_experiments.map(String) : [],
    limitations: Array.isArray(row.limitations) ? row.limitations.map(String) : [],
    scorecard: {
      causality: { value: Number(scorecard.causality?.value) || 0 },
      actionability: { value: Number(scorecard.actionability?.value) || 0 },
      evidence_quality: { value: Number(scorecard.evidence_quality?.value) || 0 },
      contradiction_penalty: Number(scorecard.contradiction_penalty) || 0,
      independent_pillars: Number(scorecard.independent_pillars) || 0,
      evidence_count: Number(scorecard.evidence_count) || 0,
      scoring_version: String(scorecard.scoring_version || "1.1.0"),
    },
    evidence: Array.isArray(row.evidence) ? (row.evidence as Result["evidence"]) : [],
  };
}

function resultsForScope(disease: string, geneNames: string[], apiRows?: unknown[]): Result[] {
  const requested = geneNames.map((g) => g.trim().toUpperCase()).filter(Boolean);
  const mapped = (Array.isArray(apiRows) ? apiRows : [])
    .map((row) => (row && typeof row === "object" ? toWorkbenchResult(row as Record<string, unknown>, disease) : null))
    .filter((row): row is Result => Boolean(row));
  const byGene = new Map(mapped.map((row) => [row.gene.toUpperCase(), row]));
  return requested.map((gene) => byGene.get(gene) || placeholderResult(gene, disease));
}

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

type ChatMsg = {
  role: "user" | "assistant" | "command";
  content: string;
  sources?: { title: string; url: string; citation: string }[];
  command?: {
    status: "pending" | "running" | "done";
    label: string;
    steps?: string[];
    action?: ClaraPending;
    fromDisease?: string;
    toDisease?: string;
    fromGenes?: string;
    toGenes?: string;
    fromMode?: "demo" | "live";
  };
};

type ClaraPending = {
  type: string;
  label: string;
  gene?: string;
  disease?: string;
  genes?: string[];
  query?: string;
  reason?: string;
};

const PATHWAY_NEIGHBORS: Record<string, string[]> = {
  IL4R: ["IL13", "IL13RA1", "IL4", "JAK1", "STAT6", "TSLP", "IL31RA"],
  IL13: ["IL4", "IL4R", "IL13RA1", "STAT6"],
  IL4: ["IL4R", "IL13", "STAT6"],
  STAT6: ["JAK1", "IL4R", "IL13"],
  JAK1: ["JAK2", "STAT3", "STAT6", "TYK2"],
  JAK2: ["JAK1", "STAT3", "TYK2"],
  TSLP: ["TSLPR", "IL7R", "IL33"],
  IL33: ["IL1RL1", "TSLP"],
  FLG: ["LOR", "IVL", "CDSN", "SPINK5", "TMEM79", "CLDN1"],
  S100A8: ["S100A9", "S100A7", "DEFB4A", "IL17A"],
  S100A9: ["S100A8", "DEFB4A"],
  IL17A: ["IL17F", "IL17RA", "RORC", "IL23R"],
  IL17F: ["IL17A", "IL17RA"],
  IL23R: ["IL23A", "IL12B", "TYK2", "IL17A"],
  TYK2: ["JAK1", "JAK2", "IL23R", "IFNAR1"],
  IL31RA: ["OSMR", "IL31", "IL4R"],
};

const DISEASE_PANEL: Record<string, string[]> = {
  "Atopic dermatitis": ["IL4R", "IL13", "FLG", "TSLP", "STAT6", "JAK1", "IL31RA", "IL33"],
  Psoriasis: ["IL17A", "IL23R", "IL12B", "TYK2", "STAT3", "IL36G", "TNF"],
  Acne: ["AR", "TLR2", "IGF1", "CYP17A1"],
  Rosacea: ["KLK5", "TLR2", "CAMP", "MMP9"],
  Vitiligo: ["TYR", "MC1R", "IFNG", "CD8A"],
  "Alopecia areata": ["JAK1", "JAK3", "IL15", "IFNG"],
  "Hidradenitis suppurativa": ["TNF", "IL17A", "IL1B", "IL23R"],
};

const RELATED_DISEASE: Record<string, string> = {
  "Atopic dermatitis": "Psoriasis",
  Psoriasis: "Atopic dermatitis",
  Acne: "Rosacea",
  Rosacea: "Acne",
  Vitiligo: "Alopecia areata",
  "Alopecia areata": "Vitiligo",
};

function pickClosePair(disease: string, sessionGenes: string[], focused: string, extraBlocked: string[] = []): { gene: string; reason: string } {
  const blocked = new Set([...sessionGenes, ...extraBlocked].map((g) => g.toUpperCase()));
  const priority: string[] = [];
  if (focused) priority.push(focused.toUpperCase());
  for (const gene of sessionGenes) {
    const upper = gene.toUpperCase();
    if (!priority.includes(upper)) priority.push(upper);
  }
  for (const gene of priority) {
    for (const neighbour of PATHWAY_NEIGHBORS[gene] || []) {
      if (!blocked.has(neighbour)) return { gene: neighbour, reason: `pathway neighbour of ${gene}` };
    }
  }
  const panel = DISEASE_PANEL[disease] || [];
  for (const gene of panel) {
    if (!blocked.has(gene.toUpperCase())) return { gene, reason: `candidate on the ${disease} panel` };
  }
  return { gene: "", reason: "" };
}

type ClaraSession = {
  chat_id: string;
  title: string;
  preview: string;
  disease: string;
  updated_at: string;
  messages?: ChatMsg[];
};

const CLARA_LOCAL_KEY = "clara-sessions-v1";

function newClaraChatId() {
  return globalThis.crypto?.randomUUID?.() ?? `clara-${Date.now()}`;
}

function readLocalClaraSessions(): ClaraSession[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(CLARA_LOCAL_KEY) || "[]");
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function writeLocalClaraSessions(rows: ClaraSession[]) {
  localStorage.setItem(CLARA_LOCAL_KEY, JSON.stringify(rows.slice(0, 40)));
}

function upsertLocalClaraSession(row: ClaraSession) {
  writeLocalClaraSessions([row, ...readLocalClaraSessions().filter((item) => item.chat_id !== row.chat_id)]);
}

function deleteLocalClaraSession(chatId: string) {
  writeLocalClaraSessions(readLocalClaraSessions().filter((item) => item.chat_id !== chatId));
}

function sessionTitle(messages: ChatMsg[], disease: string) {
  const first = messages.find((item) => item.role === "user" && item.content.trim());
  if (!first) return `${disease} session`;
  const text = first.content.replace(/\s+/g, " ").trim();
  return text.length > 56 ? `${text.slice(0, 56)}…` : text;
}

function LinkGlyph() {
  return (
    <svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true">
      <path d="M6 4h6v6M12 4L6.5 9.5M4 7v5h5" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  );
}

function ClaraText({
  text,
  streaming,
  onDone,
}: {
  text: string;
  streaming?: boolean;
  onDone?: () => void;
}) {
  const cleaned = text.replace(/https?:\/\/[^\s)]+/g, "").replace(/\n{3,}/g, "\n\n").trim();
  const [shown, setShown] = useState(streaming ? 0 : cleaned.length);
  const rafRef = useRef<number>(0);
  const doneRef = useRef(false);
  const onDoneRef = useRef(onDone);
  onDoneRef.current = onDone;

  useEffect(() => {
    doneRef.current = false;
    if (!streaming) {
      setShown(cleaned.length);
      return;
    }
    setShown(0);
    let i = 0;
    const finish = () => {
      if (doneRef.current) return;
      doneRef.current = true;
      onDoneRef.current?.();
    };
    const tick = () => {
      const step = cleaned[i] === " " ? 2 : 1;
      i = Math.min(i + step, cleaned.length);
      setShown(i);
      if (i < cleaned.length) rafRef.current = requestAnimationFrame(tick);
      else finish();
    };
    const delay = setTimeout(() => { rafRef.current = requestAnimationFrame(tick); }, 60);
    return () => { clearTimeout(delay); cancelAnimationFrame(rafRef.current); };
  }, [cleaned, streaming]);

  return <>{cleaned.slice(0, shown)}{streaming && shown < cleaned.length ? <span className="clara-caret" /> : null}</>;
}

function ClaraSources({ hits }: { hits: { title: string; url: string; citation: string }[] }) {
  if (!hits.length) return null;
  return (
    <div className="clara-sources">
      {hits.map((hit) => (
        <a key={hit.url} className="clara-source" href={hit.url} target="_blank" rel="noreferrer">
          <span className="clara-source-title">{hit.title}</span>
          <span className="clara-source-cite">{hit.citation}</span>
          <span className="clara-source-icon" title={hit.url}><LinkGlyph /></span>
        </a>
      ))}
    </div>
  );
}

function extractNamedGenes(text: string, sessionGenes: string[], focused: string): string[] {
  const found: string[] = [];
  for (const gene of sessionGenes) {
    if (new RegExp(`\\b${gene}\\b`, "i").test(text) && !found.includes(gene)) found.push(gene);
  }
  const extras = text.match(/\b([A-Z][A-Z0-9-]{2,11})\b/g) || [];
  const skip = new Set(["AND", "FOR", "THE", "PMC", "MED", "PMID", "RUN", "API", "GWAS", "QTL"]);
  for (const token of extras) {
    if (skip.has(token) || found.some((g) => g.toUpperCase() === token)) continue;
    const sessionHit = sessionGenes.find((g) => g.toUpperCase() === token);
    found.push(sessionHit || token);
  }
  if (found.length) return found;
  if (/\b(the gene|this gene|current gene|focused gene)\b/i.test(text) && focused) return [focused];
  return sessionGenes;
}

function inferPendingCommand(
  text: string,
  disease: string,
  geneList: string,
  focused: string,
  mode: "demo" | "live" = "demo",
): NonNullable<ChatMsg["command"]> | null {
  const lower = text.toLowerCase();
  const isSearch = /\b(search|look up|lookup|pubmed|literature|europe pmc|find papers?)\b/.test(lower);
  const isClosePair = /\b(close pair|closest pair|sibling gene|sibling target|nearby gene|neighbou?r gene|similar target|similar gene|next candidate|another candidate|another target|adjacent gene|adjacent target|same disease (?:another|different) gene|pair with the same disease|different one|another one|try another|try a different|do a different|close to it|close to this|instead of)\b/.test(
    lower,
  );
  const isNewDisease = /\b(close disease|related disease|nearby disease|similar disease|another disease|different disease|change the diea?ses?|change disease|new disease|switch disease|diea?ses? as well|disease as well)\b/.test(lower);
  const isRerun = /\b(rerun|re-run|run again|run another|another run|another analysis|refresh|reanalyze)\b/.test(lower);
  const genes = geneList.split(",").map((g) => g.trim()).filter(Boolean);
  if (isSearch) {
    const named = extractNamedGenes(text, genes, focused);
    const gene = named[0] || focused;
    const label = `Search Europe PMC for ${gene} × ${disease}`;
    return {
      status: "pending",
      label,
      action: { type: "search", label, gene, disease, query: `${gene} × ${disease}` },
      fromDisease: disease,
      toDisease: disease,
      fromGenes: geneList,
      toGenes: geneList,
    };
  }
  const removeMatch = text.match(/\b(?:remove|drop|without|except|delete)\b(.+?)(?:\b(?:instead|try)\b|$)/i);
  const insteadMatch = text.match(/\binstead of\s+([A-Za-z0-9-]+)/i);
  if (removeMatch || insteadMatch || isClosePair || isNewDisease || isRerun) {
    let toDisease = isNewDisease ? (RELATED_DISEASE[disease] || disease) : disease;
    let toGenes = genes;
    let reason = "";
    if (removeMatch || insteadMatch) {
      const removed = extractNamedGenes(removeMatch?.[1] || "", genes, focused);
      const instead = (insteadMatch?.[1] || "").toUpperCase();
      const keep = genes.filter((g) => !removed.includes(g) && g.toUpperCase() !== instead);
      const anchor = genes.find((g) => g.toUpperCase() === instead) || focused;
      const pair = pickClosePair(toDisease, genes, anchor, [...removed, instead]);
      toGenes = [...keep, ...(pair.gene ? [pair.gene] : [])];
      reason = pair.reason;
    } else if (isClosePair || isNewDisease) {
      const pair = pickClosePair(toDisease, genes, focused);
      if (pair.gene) {
        toGenes = [pair.gene];
        reason = pair.reason;
      }
    } else {
      toGenes = extractNamedGenes(text, genes, focused);
    }
    const geneS = toGenes.join(", ");
    const label = reason
      ? `Re-run BioLead for ${toDisease} · ${geneS}  (close pair · ${reason})`
      : `Re-run BioLead for ${toDisease} · ${geneS}`;
    return {
      status: "pending",
      label,
      action: {
        type: "rerun",
        label,
        gene: toGenes[0] || focused,
        disease: toDisease,
        genes: toGenes,
        reason: reason ? `close_pair:${reason}` : undefined,
      },
      fromDisease: disease,
      toDisease,
      fromGenes: geneList,
      toGenes: geneS,
      fromMode: mode,
    };
  }
  return null;
}

function hydrateCommands(
  items: ChatMsg[],
  disease: string,
  geneList: string,
  focused: string,
  mode: "demo" | "live" = "demo",
): ChatMsg[] {
  const lastUserIdx = [...items].map((item, idx) => (item.role === "user" ? idx : -1)).filter((idx) => idx >= 0).at(-1);
  if (lastUserIdx == null) return items;
  const after = items.slice(lastUserIdx + 1);
  if (after.some((item) => item.role === "command")) return items;
  if (!after.some((item) => item.role === "assistant")) return items;
  const command = inferPendingCommand(items[lastUserIdx].content, disease, geneList, focused, mode);
  if (!command) return items;
  return [...items, { role: "command", content: command.label, command }];
}

function ClaraCommandCard({
  command,
  disabled,
  onConfirm,
  onSkip,
}: {
  command: NonNullable<ChatMsg["command"]>;
  disabled: boolean;
  onConfirm: () => void;
  onSkip: () => void;
}) {
  const diseaseChanged = Boolean(command.fromDisease && command.toDisease && command.fromDisease !== command.toDisease);
  const genesChanged = Boolean(command.fromGenes && command.toGenes && command.fromGenes !== command.toGenes);
  const pipeline = command.action?.type === "rerun" || command.label.toLowerCase().includes("re-run");
  const query = command.action?.type === "search"
    ? `${command.action.gene || ""} × ${command.action.disease || command.toDisease || ""}`.trim()
    : "";
  return (
    <div className={`clara-pending-card clara-cmd-${command.status}`} data-testid="clara-pending">
      <div className="clara-pending-copy">
        <span className="clara-pending-kicker">
          {command.status === "pending" ? "Command" : command.status === "running" ? "Running" : "Done"}
        </span>
        <strong>{command.label}</strong>
      </div>
      <div className="clara-changes">
        {(command.toDisease || command.fromDisease) && (
          <div className="clara-change-row">
            <span className="clara-change-key">Disease</span>
            {diseaseChanged ? (
              <>
                <span className="clara-change-from">{command.fromDisease}</span>
                <span className="clara-change-arrow">&rarr;</span>
                <span className="clara-change-to">{command.toDisease}</span>
              </>
            ) : (
              <span className="clara-change-to">{command.toDisease || command.fromDisease}</span>
            )}
          </div>
        )}
        {(command.toGenes || command.fromGenes) && (
          <div className="clara-change-row">
            <span className="clara-change-key">Genes</span>
            {genesChanged ? (
              <>
                <span className="clara-change-from">{command.fromGenes}</span>
                <span className="clara-change-arrow">&rarr;</span>
                <span className="clara-change-to">{command.toGenes}</span>
              </>
            ) : (
              <span className="clara-change-to">{command.toGenes || command.fromGenes}</span>
            )}
          </div>
        )}
        {query && (
          <div className="clara-change-row">
            <span className="clara-change-key">Query</span>
            <span className="clara-change-to">{query}</span>
          </div>
        )}
        {pipeline && (
          <>
            <div className="clara-change-row">
              <span className="clara-change-key">Mode</span>
              {command.fromMode === "live" ? (
                <span className="clara-change-to">Live</span>
              ) : (
                <>
                  <span className="clara-change-from">Demo</span>
                  <span className="clara-change-arrow">&rarr;</span>
                  <span className="clara-change-to">Live</span>
                </>
              )}
            </div>
            <div className="clara-change-row">
              <span className="clara-change-key">Agents</span>
              <span className="clara-change-to">Retrieve → Extract → Score → Falsify → Decide</span>
            </div>
          </>
        )}
      </div>
      {!!command.steps?.length && (
        <div className="clara-activity">
          {command.steps.map((step, i) => (
            <div key={`${step}-${i}`} className="clara-activity-step">
              <span className="clara-activity-dot" />
              {step}
            </div>
          ))}
        </div>
      )}
      {command.status === "pending" && command.action && (
        <div className="clara-pending-actions">
          <button type="button" className="clara-confirm" onClick={onConfirm} disabled={disabled}>Confirm</button>
          <button type="button" className="clara-skip" onClick={onSkip} disabled={disabled}>Skip</button>
        </div>
      )}
    </div>
  );
}

function firstNameFromRaw(...candidates: Array<string | null | undefined>): string {
  for (const raw of candidates) {
    let text = (raw || "").trim();
    if (!text) continue;
    text = text.split("@")[0].trim();
    if (["guest", "scientist", "user", "admin"].includes(text.toLowerCase())) continue;
    if (text.includes(",")) {
      const after = text.split(",")[1]?.trim();
      if (after) text = after;
    }
    const camel = text.match(/[A-Z][a-z]{1,13}/g);
    if (camel && camel.length >= 2) return camel[0];
    const parts = text.split(/[._\s-]+/).filter(Boolean);
    if (parts[0] && parts[0].length >= 2 && parts[0].length <= 12 && /^[A-Za-z]+$/.test(parts[0])) {
      if (parts.length === 1 && text.length > 12) continue;
      return parts[0][0].toUpperCase() + parts[0].slice(1).toLowerCase();
    }
  }
  return "";
}

function scientistFromSession(session: Session | null) {
  const email = session?.user?.email ?? null;
  const meta = session?.user?.user_metadata as {
    full_name?: string;
    name?: string;
    given_name?: string;
    first_name?: string;
  } | undefined;
  const name = firstNameFromRaw(
    meta?.given_name,
    meta?.first_name,
    meta?.full_name,
    meta?.name,
    email,
  );
  return {
    signed_in: Boolean(session?.user),
    email,
    name: session?.user ? name : "Guest",
    given_name: name,
  };
}

function buildClaraContext(
  disease: string,
  mode: "demo" | "live",
  results: Result[],
  active: Result,
  session: Session | null,
  notice: string,
) {
  const scientist = scientistFromSession(session);
  return {
    disease,
    mode,
    tissue: "skin",
    notice,
    scientist,
    session: results.map((r) => ({
      gene: r.gene,
      verdict: r.verdict,
      confidence: r.confidence,
      recommended_direction: r.recommended_direction,
      causality: r.scorecard.causality.value,
      actionability: r.scorecard.actionability.value,
      evidence_quality: r.scorecard.evidence_quality.value,
      independent_pillars: r.scorecard.independent_pillars,
      evidence_count: r.scorecard.evidence_count,
      evidence: r.evidence.map((e) => ({
        title: e.title,
        citation: e.citation,
        source_url: e.source_url,
      })),
    })),
    dossier: active,
  };
}

function Clara({
  chatId,
  runId,
  disease,
  mode,
  results,
  active,
  session,
  notice,
  messages,
  setMessages,
  running,
  onClose,
  onFocusGene,
  onRerun,
  onNewChat,
  onChatId,
}: {
  chatId: string;
  runId: string;
  disease: string;
  mode: "demo" | "live";
  results: Result[];
  active: Result;
  session: Session | null;
  notice: string;
  messages: ChatMsg[];
  setMessages: (next: ChatMsg[] | ((current: ChatMsg[]) => ChatMsg[])) => void;
  running: boolean;
  onClose: () => void;
  onFocusGene: (gene: string) => void;
  onRerun: (scope?: { disease?: string; genes?: string[] }) => Promise<void>;
  onNewChat: () => void;
  onChatId: (id: string) => void;
}) {
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [sessions, setSessions] = useState<ClaraSession[]>([]);
  const deferredCommandsRef = useRef<ChatMsg[]>([]);
  const holdingCommandsRef = useRef(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const scientist = scientistFromSession(session);
  const context = buildClaraContext(disease, mode, results, active, session, notice);
  const geneList = results.map((r) => r.gene).join(", ");

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading, running]);

  useEffect(() => {
    setTimeout(() => inputRef.current?.focus(), 200);
  }, []);

  useEffect(() => {
    if (loading || holdingCommandsRef.current) return;
    const hydrated = hydrateCommands(messages, disease, geneList, active.gene, mode);
    if (hydrated.length > messages.length) setMessages(hydrated);
  }, [messages, disease, geneList, active.gene, mode, loading, setMessages]);

  async function refreshSessions() {
    if (scientist.signed_in) {
      try {
        const token = await getAccessToken();
        const headers: Record<string, string> = {};
        if (token) headers.Authorization = `Bearer ${token}`;
        const response = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/chat/sessions`,
          { headers },
        );
        if (response.ok) {
          const data = await response.json();
          if (Array.isArray(data.sessions)) {
            setSessions(data.sessions);
            return;
          }
        }
      } catch {
        // Fall through to local history.
      }
    }
    setSessions(readLocalClaraSessions().map(({ messages: _msgs, ...row }) => row));
  }

  useEffect(() => {
    if (historyOpen) void refreshSessions();
  }, [historyOpen, scientist.signed_in]);

  function persistLocal(next: ChatMsg[]) {
    if (!next.some((item) => item.role === "user")) return;
    upsertLocalClaraSession({
      chat_id: chatId,
      title: sessionTitle(next, disease),
      preview: [...next].reverse().find((item) => item.role !== "command")?.content?.slice(0, 80) || "",
      disease,
      updated_at: new Date().toISOString(),
      messages: next,
    });
  }

  async function loadSession(id: string) {
    if (scientist.signed_in) {
      try {
        const token = await getAccessToken();
        const headers: Record<string, string> = {};
        if (token) headers.Authorization = `Bearer ${token}`;
        const response = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/chat/history?chat_id=${encodeURIComponent(id)}`,
          { headers },
        );
        if (response.ok) {
          const data = await response.json();
          if (Array.isArray(data.messages)) {
            onChatId(id);
            setMessages(hydrateCommands(data.messages as ChatMsg[], disease, geneList, active.gene, mode));
            return;
          }
        }
      } catch {
        // Fall through to local history.
      }
    }
    const local = readLocalClaraSessions().find((item) => item.chat_id === id);
    if (!local) return;
    onChatId(id);
    setMessages(hydrateCommands(local.messages || [], disease, geneList, active.gene, mode));
  }

  async function removeSession(id: string, event: React.MouseEvent) {
    event.stopPropagation();
    if (scientist.signed_in) {
      try {
        const token = await getAccessToken();
        const headers: Record<string, string> = {};
        if (token) headers.Authorization = `Bearer ${token}`;
        await fetch(
          `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/chat/sessions/${encodeURIComponent(id)}`,
          { method: "DELETE", headers },
        );
      } catch {
        // Local copy is still removed below.
      }
    }
    deleteLocalClaraSession(id);
    setSessions((rows) => rows.filter((row) => row.chat_id !== id));
    if (id === chatId) onNewChat();
  }

  function chatPayload(items: ChatMsg[]) {
    return items.map((m) => ({
      role: m.role,
      content: m.content,
      sources: m.sources ?? [],
      command: m.command ?? null,
    }));
  }

  function flushDeferredCommands() {
    const cards = deferredCommandsRef.current;
    holdingCommandsRef.current = false;
    if (!cards.length) return;
    deferredCommandsRef.current = [];
    setMessages((current) => {
      const next = current.some((item) => item.role === "command" && item.command?.status === "pending")
        ? current
        : [...current, ...cards];
      persistLocal(next);
      return next;
    });
  }

  function commandFromAction(action: ClaraPending): ChatMsg {
    const toGenes = action.genes?.length ? action.genes.join(", ") : geneList;
    return {
      role: "command",
      content: action.label,
      command: {
        status: "pending",
        label: action.label,
        action,
        fromDisease: disease,
        toDisease: action.disease || disease,
        fromGenes: geneList,
        toGenes,
        fromMode: mode,
      },
    };
  }

  async function sendText(text: string, confirm?: ClaraPending[]) {
    const trimmed = text.trim();
    if ((!trimmed && !confirm?.length) || loading || running) return;
    const userMsg: ChatMsg | null = trimmed ? { role: "user", content: trimmed } : null;
    let next: ChatMsg[] = userMsg ? [...messages, userMsg] : messages;
    if (confirm?.length) {
      next = next.map((m) =>
        m.role === "command" && m.command?.status === "pending"
          ? { ...m, command: { ...m.command, status: "running", steps: ["Running confirmed command\u2026"] } }
          : m,
      );
    }
    setMessages(next);
    setInput("");
    setLoading(true);
    try {
      const token = await getAccessToken();
      const payload = JSON.stringify({
        run_id: runId,
        chat_id: chatId,
        messages: chatPayload(next.filter((m) => m.role !== "command" || Boolean(confirm?.length))),
        context,
        confirm: confirm ?? [],
      });
      const postChat = (auth: string | null) => {
        const headers: Record<string, string> = { "Content-Type": "application/json" };
        if (auth) headers.Authorization = `Bearer ${auth}`;
        return fetch(`${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/chat`, {
          method: "POST",
          headers,
          body: payload,
        });
      };
      let res = await postChat(token);
      if (!res.ok && token && (res.status === 401 || res.status === 503)) {
        res = await postChat(null);
      }
      if (!res.ok) throw new Error(`${res.status}`);
      const data = await res.json();
      const activity: string[] = Array.isArray(data.activity) ? data.activity : [];
      if (data.persisted) activity.push("Saved to your Clara memory");
      const pendingActions: ClaraPending[] = Array.isArray(data.pending) ? data.pending : [];
      const actions = Array.isArray(data.actions) ? data.actions : [];
      const searchHits = actions.find((a: { type: string; hits?: unknown[] }) => a.type === "search")?.hits ?? [];
      const sources = Array.isArray(searchHits) && searchHits.length ? searchHits : [];

      if (data.reply) {
        next = [...next, { role: "assistant", content: data.reply, sources }];
      }

      let pendingCards: ChatMsg[] = [];
      if (pendingActions.length && !confirm?.length) {
        pendingCards = pendingActions.map(commandFromAction);
      } else if (!confirm?.length && userMsg) {
        const inferred = inferPendingCommand(userMsg.content, disease, geneList, active.gene, mode);
        if (inferred && !next.some((m) => m.role === "command" && m.command?.status === "pending")) {
          pendingCards = [{ role: "command", content: inferred.label, command: inferred }];
        }
      }

      if (confirm?.length && activity.length) {
        next = next.map((m) =>
          m.role === "command" && m.command?.status === "running"
            ? { ...m, command: { ...m.command, steps: activity } }
            : m,
        );
      }

      const talkFirst = Boolean(data.reply) && pendingCards.length > 0 && !confirm?.length;
      if (talkFirst) {
        deferredCommandsRef.current = pendingCards;
        holdingCommandsRef.current = true;
        setMessages(next);
      } else {
        deferredCommandsRef.current = [];
        holdingCommandsRef.current = false;
        if (pendingCards.length) next = [...next, ...pendingCards];
        setMessages(next);
      }

      for (const action of actions) {
        if (action.type === "focus_gene" && action.gene) onFocusGene(action.gene);
        if (action.type === "rerun") {
          const genes = (Array.isArray(action.genes) ? action.genes : [])
            .map((g: string) => String(g).trim())
            .filter(Boolean);
          const fallback = action.gene ? [String(action.gene)] : [];
          await onRerun({
            disease: action.disease,
            genes: genes.length ? genes : fallback,
          });
        }
      }

      if (confirm?.length) {
        next = next.map((m) =>
          m.role === "command" && m.command?.status === "running"
            ? { ...m, command: { ...m.command, status: "done", steps: activity } }
            : m,
        );
        setMessages(next);
      }
      persistLocal(next);
      if (historyOpen) void refreshSessions();
    } catch {
      const fallback = inferPendingCommand(trimmed, disease, geneList, active.gene, mode);
      const recovered: ChatMsg[] = [...next];
      if (fallback && !confirm?.length) {
        recovered.push({
          role: "assistant",
          content: fallback.action?.type === "rerun"
            ? `Queued ${fallback.toDisease} × ${fallback.toGenes}. Confirm below.`
            : `Queued ${fallback.label}. Confirm below.`,
        });
        recovered.push({ role: "command", content: fallback.label, command: fallback });
      } else {
        recovered.push({ role: "assistant", content: "I\u2019m having trouble connecting. The evidence dossier is your source of truth for now." });
      }
      setMessages(recovered);
      persistLocal(recovered);
    } finally {
      setLoading(false);
    }
  }

  async function send(e: React.FormEvent) {
    e.preventDefault();
    await sendText(input);
  }

  function startNewChat() {
    deferredCommandsRef.current = [];
    holdingCommandsRef.current = false;
    onNewChat();
  }

  const closePair = pickClosePair(disease, geneList.split(",").map((g) => g.trim()).filter(Boolean), active.gene);
  const options = [
    {
      kind: "command" as const,
      kicker: "Command",
      label: `Search papers for ${active.gene}`,
      text: `search papers for ${active.gene}`,
    },
    closePair.gene
      ? {
          kind: "command" as const,
          kicker: "Command",
          label: `Try a close pair — ${closePair.gene} on ${disease}`,
          text: `let's try a close pair with the same disease — ${closePair.gene}`,
        }
      : {
          kind: "argue" as const,
          kicker: "Argue",
          label: `Defend ${active.gene} as ${active.verdict}`,
          text: "defend this verdict",
        },
    {
      kind: "argue" as const,
      kicker: "Argue",
      label: `Challenge ${active.gene} as ${active.verdict}`,
      text: "challenge this verdict",
    },
  ];
  const optionButtons = (
    <div className="clara-suggestions" data-testid="clara-options">
      {options.map((opt) => (
        <button
          key={opt.text}
          type="button"
          className={`clara-option clara-option-${opt.kind}`}
          disabled={loading || running}
          onClick={() => sendText(opt.text)}
        >
          <span className="clara-option-kicker">{opt.kicker}</span>
          <span>{opt.label}</span>
        </button>
      ))}
    </div>
  );

  return (
    <div className={`clara-frame${historyOpen ? " history-open" : ""}`}>
      <aside className="clara-sidebar" data-testid="clara-history">
        <div className="clara-sidebar-top">
          <button type="button" className="clara-icon-btn" onClick={() => setHistoryOpen(false)} aria-label="Close history">
            <svg viewBox="0 0 18 18" width="16" height="16" aria-hidden="true">
              <path d="M3 5h12M3 9h12M3 13h12" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
            </svg>
          </button>
          <button type="button" className="clara-icon-btn" onClick={startNewChat} aria-label="New chat">
            <svg viewBox="0 0 16 16" width="14" height="14"><path d="M8 3v10M3 8h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
          </button>
        </div>
        <button type="button" className="clara-sidebar-new" onClick={startNewChat}>
          <svg viewBox="0 0 16 16" width="14" height="14"><path d="M8 3v10M3 8h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
          New chat
        </button>
        <p className="clara-sidebar-label">Chats</p>
        {sessions.length === 0 ? (
          <p className="clara-history-empty">No saved chats yet.</p>
        ) : (
          <div className="clara-history-list">
            {sessions.map((item) => (
              <div
                key={item.chat_id}
                className={`clara-history-item${item.chat_id === chatId ? " active" : ""}`}
              >
                <button type="button" className="clara-history-open" onClick={() => loadSession(item.chat_id)}>
                  <span className="clara-history-title">{item.title}</span>
                  <span className="clara-history-meta">{item.disease || "Clara"}</span>
                </button>
                <button
                  type="button"
                  className="clara-history-delete"
                  aria-label={`Delete ${item.title}`}
                  onClick={(event) => removeSession(item.chat_id, event)}
                >
                  <svg viewBox="0 0 16 16" width="12" height="12"><path d="M5 3h6M4 5h8M6 5v7M10 5v7M5 5l.5 8h5l.5-8" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/></svg>
                </button>
              </div>
            ))}
          </div>
        )}
      </aside>

      <div className="clara-panel">
        <div className="clara-header">
          <div className="clara-identity">
            <button type="button" className="clara-icon-btn clara-hamburger" onClick={() => setHistoryOpen((open) => !open)} aria-label="Open chat history">
              <svg viewBox="0 0 18 18" width="16" height="16" aria-hidden="true">
                <path d="M3 5h12M3 9h12M3 13h12" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
              </svg>
            </button>
            <div className="clara-avatar">
              <svg viewBox="0 0 32 32" width="28" height="28"><circle cx="16" cy="16" r="14" fill="none" stroke="currentColor" strokeWidth="1.2"/><circle cx="16" cy="13" r="5" fill="currentColor" opacity="0.15"/><path d="M8 26c0-4.4 3.6-8 8-8s8 3.6 8 8" fill="none" stroke="currentColor" strokeWidth="1.2"/><circle cx="16" cy="13" r="4" fill="none" stroke="currentColor" strokeWidth="1"/></svg>
            </div>
            <div>
              <h3>Clara</h3>
              <span className="clara-subtitle">Supervisor reasoning agent</span>
              <span className="clara-memory">
                {scientist.signed_in ? "Memory on" : "Guest · sign in for memory"}
              </span>
            </div>
          </div>
          <button className="clara-close" onClick={onClose} aria-label="Close Clara">
            <svg viewBox="0 0 16 16" width="14" height="14"><path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
          </button>
        </div>

        <div className="clara-context-bar">
          <span className="clara-ctx-dot" />
          Overseeing <strong>{disease}</strong> &middot; {geneList || active.gene} &middot; {active.verdict}
        </div>

      <div className="clara-messages">
        {messages.length === 0 ? (
          <div className="clara-welcome">
            <p>
              {scientist.signed_in && scientist.name ? "Hey. " : "Hi. "}
              I&apos;m Clara, the supervisor reasoning agent on this {mode} run. I control the session — <strong>{disease}</strong> ({geneList}), the evidence, and the next step on the chain.
              Verdict, citations, or a close pair?
            </p>
            {optionButtons}
          </div>
        ) : (
          <>
            {messages.map((m, i) =>
              m.role === "command" && m.command ? (
                <div key={i} className="clara-msg command">
                  <ClaraCommandCard
                    command={m.command}
                    disabled={loading || running}
                    onConfirm={() => {
                      const cmd = m.command;
                      if (!cmd?.action) return;
                      const genes = (cmd.action.genes?.length
                        ? cmd.action.genes
                        : (cmd.toGenes || "").split(",").map((g) => g.trim()).filter(Boolean));
                      void sendText("", [{
                        ...cmd.action,
                        disease: cmd.action.disease || cmd.toDisease,
                        genes,
                      }]);
                    }}
                    onSkip={() =>
                      setMessages(
                        messages.map((row, idx) =>
                          idx === i && row.command
                            ? { ...row, command: { ...row.command, status: "done", steps: ["Skipped"] } }
                            : row,
                        ),
                      )
                    }
                  />
                </div>
              ) : (
                <div key={i} className={`clara-msg ${m.role}`}>
                  {m.role === "assistant" && <span className="clara-msg-avatar">C</span>}
                  <div className="clara-msg-bubble">
                    <ClaraText
                      text={m.content}
                      streaming={m.role === "assistant" && i === messages.length - 1 && !loading}
                      onDone={m.role === "assistant" && i === messages.length - 1 && !loading ? flushDeferredCommands : undefined}
                    />
                    {m.role === "assistant" && m.sources && <ClaraSources hits={m.sources} />}
                  </div>
                </div>
              ),
            )}
            {loading && (
              <div className="clara-msg assistant">
                <span className="clara-msg-avatar">C</span>
                <div className="clara-msg-bubble clara-typing">
                  <span /><span /><span />
                </div>
              </div>
            )}
          </>
        )}
        <div ref={bottomRef} />
      </div>

      <form className="clara-input" onSubmit={send}>
        <input
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask Clara about this run…"
          disabled={loading || running}
        />
        <button type="submit" disabled={loading || running || !input.trim()} aria-label="Send">
          <svg viewBox="0 0 20 20" width="16" height="16"><path d="M3 10l14-7-7 14v-7H3z" fill="currentColor"/></svg>
        </button>
      </form>
      </div>
    </div>
  );
}

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function nodeCenter(el: HTMLElement | null) {
  if (!el) return null;
  const r = el.getBoundingClientRect();
  const bar = el.closest(".input-bar");
  const barR = bar?.getBoundingClientRect();
  return {
    x: r.left + r.width * 0.5,
    y: barR ? barR.top + barR.height * 0.5 : r.top + r.height * 0.5,
  };
}

function AgentCursor({
  x,
  y,
  label,
  clicking,
}: {
  x: number;
  y: number;
  label: string;
  clicking: boolean;
}) {
  return (
    <div className={`agent-cursor${clicking ? " clicking" : ""}`} style={{ left: x, top: y }} data-testid="agent-cursor" aria-hidden="true">
      <svg viewBox="0 0 48 48" width="48" height="48">
        <path d="M8 4 L8 36 L16 28 L22 42 L28 39 L22 26 L34 26 Z" fill="currentColor" />
      </svg>
      {label ? <span className="agent-cursor-label">{label}</span> : null}
    </div>
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
  const [authOpen, setAuthOpen] = useState(false);
  const [claraOpen, setClaraOpen] = useState(false);
  const [claraNotif, setClaraNotif] = useState(false);
  const [claraWanted, setClaraWanted] = useState(false);
  const [claraMessages, setClaraMessages] = useState<ChatMsg[]>([]);
  const [claraChatId, setClaraChatId] = useState(newClaraChatId);
  const [runId, setRunId] = useState("seeded-demo");
  const [agentCursor, setAgentCursor] = useState<{ x: number; y: number; label: string; clicking: boolean } | null>(null);
  const [agentHit, setAgentHit] = useState<"disease" | "genes" | "demo" | "live" | "run" | null>(null);
  const diseaseRef = useRef<HTMLInputElement>(null);
  const genesRef = useRef<HTMLInputElement>(null);
  const demoRef = useRef<HTMLButtonElement>(null);
  const liveRef = useRef<HTMLButtonElement>(null);
  const runRef = useRef<HTMLButtonElement>(null);

  const signedIn = Boolean(session?.user?.id);

  useEffect(() => {
    if (!signedIn) return;
    const t = setTimeout(() => setClaraNotif(true), 2500);
    return () => clearTimeout(t);
  }, [signedIn]);

  useEffect(() => {
    if (!signedIn) {
      setClaraOpen(false);
      return;
    }
    if (claraWanted) {
      setClaraOpen(true);
      setClaraNotif(false);
      setClaraWanted(false);
      setAuthOpen(false);
    }
  }, [signedIn, claraWanted]);

  function tryOpenClara() {
    if (session?.user?.id) {
      setClaraOpen(true);
      setClaraNotif(false);
      setClaraWanted(false);
      return;
    }
    setClaraWanted(true);
    setAuthOpen(true);
    setClaraNotif(true);
  }

  function startClaraChat() {
    setClaraMessages([]);
    setClaraChatId(newClaraChatId());
  }

  const onSessionChange = useCallback((next: Session | null) => {
    setSession(next);
    if (!next) setStats(null);
  }, []);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    document.documentElement.style.colorScheme = theme;
  }, [theme]);

  useEffect(() => {
    if (!session) return;
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

  const active = results.find((r) => r.gene === activeGene) ?? results[0];

  useEffect(() => {
    if (!running) return;
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

  async function moveCursorTo(el: HTMLElement | null, label: string) {
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "nearest" });
    await sleep(280);
    const point = nodeCenter(el);
    if (!point) return;
    setAgentCursor({ x: point.x, y: point.y, label, clicking: false });
    await sleep(2400);
  }

  async function typeInto(setter: (val: string) => void, value: string) {
    setter("");
    await sleep(200);
    for (let i = 0; i <= value.length; i++) {
      setter(value.slice(0, i));
      await sleep(80);
    }
    await sleep(500);
  }

  async function playAgentTrace(scope: { disease?: string; genes?: string[] }) {
    const nextDisease = scope.disease?.trim() || disease;
    const geneNames = (scope.genes || []).map((g) => g.trim()).filter(Boolean);
    const nextGenes = geneNames.length ? geneNames.join(", ") : genes;
    const appliedGenes = nextGenes.split(",").map((g) => g.trim()).filter(Boolean);
    setAgentCursor({
      x: Math.max(80, window.innerWidth - 240),
      y: Math.min(window.innerHeight * 0.42, window.innerHeight - 80),
      label: "Clara",
      clicking: false,
    });
    await sleep(900);

    setAgentHit("disease");
    await moveCursorTo(diseaseRef.current, "Typing disease");
    setAgentCursor((c) => (c ? { ...c, clicking: true } : c));
    await sleep(450);
    setAgentCursor((c) => (c ? { ...c, clicking: false } : c));
    await typeInto(setDisease, nextDisease);

    setAgentHit("genes");
    await moveCursorTo(genesRef.current, "Typing genes");
    setAgentCursor((c) => (c ? { ...c, clicking: true } : c));
    await sleep(450);
    setAgentCursor((c) => (c ? { ...c, clicking: false } : c));
    await typeInto(setGenes, nextGenes);

    if (mode !== "live" && liveRef.current) {
      setAgentHit("live");
      await moveCursorTo(liveRef.current, "Switching to Live");
      setMode("live");
      setAgentCursor((c) => (c ? { ...c, clicking: true } : c));
      await sleep(700);
      setAgentCursor((c) => (c ? { ...c, clicking: false } : c));
      await sleep(500);
    }

    setAgentHit("run");
    await moveCursorTo(runRef.current, "Running analysis");
    setAgentCursor((c) => (c ? { ...c, clicking: true } : c));
    await sleep(800);

    setAgentCursor(null);
    setAgentHit(null);
    await runAnalysis({
      resetClara: false,
      disease: nextDisease,
      genes: appliedGenes,
      mode: "live",
    });
  }

  async function run(e: FormEvent) {
    e.preventDefault();
    await runAnalysis({ resetClara: true });
  }

  async function runAnalysis(opts?: { resetClara?: boolean; disease?: string; genes?: string[]; mode?: "demo" | "live" }) {
    const nextDisease = opts?.disease?.trim() || disease;
    const geneNames = (opts?.genes?.length ? opts.genes : genes.split(",")).map((g) => g.trim()).filter(Boolean);
    const nextGenes = geneNames.join(", ");
    const runMode = opts?.mode || mode;
    setDisease(nextDisease);
    setGenes(nextGenes);
    if (runMode !== mode) setMode(runMode);
    setResults(resultsForScope(nextDisease, geneNames));
    setActiveGene(geneNames[0] || "");
    const started = performance.now();
    setStage(0);
    setElapsedMs(0);
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
            disease: nextDisease,
            genes: geneNames,
            tissue: "skin",
            intervention_direction: "unknown",
            mode: runMode,
          }),
        },
      );
      if (!res.ok) {
        const detail = await res.text();
        throw new Error(`API ${res.status}: ${detail.slice(0, 160)}`);
      }
      const data = await res.json();
      const applied = resultsForScope(nextDisease, geneNames, data.results);
      if (!applied.length) throw new Error("API returned no candidate results");
      setResults(applied);
      setActiveGene(applied[0]?.gene ?? geneNames[0] ?? "");
      setRunId(data.run_id);
      if (opts?.resetClara !== false) {
        setClaraMessages([]);
        setClaraChatId(newClaraChatId());
      }
      const ms = Math.round(performance.now() - started);
      setLastLatencyMs(ms);
      const who = session?.user?.email ? ` · ${session.user.email}` : "";
      setNotice(`${runMode === "live" ? "Live" : "Seeded"} run \u00b7 ${String(data.run_id || "").slice(0, 8)} · ${(ms / 1000).toFixed(1)}s${who}`);
      if (!claraOpen) setTimeout(() => setClaraNotif(true), 1200);
    } catch (error) {
      const ms = Math.round(performance.now() - started);
      setLastLatencyMs(ms);
      setResults(resultsForScope(nextDisease, geneNames));
      setActiveGene(geneNames[0] || "");
      const message = error instanceof Error ? error.message : "Unknown request error";
      setNotice(`${runMode === "live" ? "Live" : "Demo"} analysis used the new scope · ${message} · ${(ms / 1000).toFixed(1)}s`);
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
  const scoring = Boolean(running && active && (sc?.evidence_count ?? 0) === 0);

  return (
    <div className={`shell tone-${t}${claraOpen ? " clara-open" : ""}`}>
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
          <AuthBar open={authOpen} onOpenChange={setAuthOpen} onSessionChange={onSessionChange} />
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

        <form className={`input-bar${agentHit ? " agent-watching" : ""}`} onSubmit={run}>
          <div className={`field${agentHit === "disease" ? " agent-hit" : ""}`}>
            <label>Disease</label>
            <input ref={diseaseRef} value={disease} onChange={(e) => setDisease(e.target.value)} />
          </div>
          <div className="divider" />
          <div className={`field grow${agentHit === "genes" ? " agent-hit" : ""}`}>
            <label>Candidate genes</label>
            <input ref={genesRef} value={genes} onChange={(e) => setGenes(e.target.value.toUpperCase())} />
          </div>
          <div className="toggle">
            <button ref={demoRef} type="button" className={`${mode === "demo" ? "on" : ""}${agentHit === "demo" ? " agent-hit" : ""}`} onClick={() => setMode("demo")}>Demo</button>
            <button ref={liveRef} type="button" className={`${mode === "live" ? "on" : ""}${agentHit === "live" ? " agent-hit" : ""}`} onClick={() => setMode("live")}>Live</button>
          </div>
          <button ref={runRef} type="submit" className={`btn-run${agentHit === "run" ? " agent-hit" : ""}`} disabled={running} data-testid="run-analysis">
            {running ? "Analyzing…" : "Run analysis"}
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
            const pending = running && r.scorecard.evidence_count === 0;
            const ct = pending ? "warn" : tone(r.verdict);
            const sel = r.gene === active?.gene;
            return (
              <button key={r.gene} className={`cand tone-${ct} ${sel ? "sel" : ""}`} data-testid={`gene-select-${r.gene}`} onClick={() => setActiveGene(r.gene)}>
                <div className="cand-border" />
                <div className="cand-inner">
                  <div className="cand-head">
                    <h3>{r.gene}</h3>
                    <span className={`verdict-chip tone-${ct}`}>{pending ? "Scoring…" : r.verdict}</span>
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
          {!running && results.length === 0 && (
            <div className="empty-results" role="status">
              No live result is available. Check the message above and retry.
            </div>
          )}
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
                  <span className={`verdict-chip lg tone-${scoring ? "warn" : t}`} data-testid="active-verdict">{scoring ? "Scoring…" : active.verdict}</span>
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
                      <span className="ev-cite">{ev.citation ?? ev.source_name} ↗</span>
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

      {agentCursor && (
        <AgentCursor x={agentCursor.x} y={agentCursor.y} label={agentCursor.label} clicking={agentCursor.clicking} />
      )}
      {claraOpen && signedIn && (active || running) && (
        <div className="clara-split-overlay">
          <Clara
            chatId={claraChatId}
            runId={runId}
            disease={disease}
            mode={mode}
            results={results.length ? results : demo}
            active={active ?? demo[0]}
            session={session}
            notice={notice}
            messages={claraMessages}
            setMessages={setClaraMessages}
            running={running}
            onClose={() => { setClaraOpen(false); setClaraNotif(true); startClaraChat(); }}
            onFocusGene={(gene) => setActiveGene(gene)}
            onRerun={(scope) => playAgentTrace({ disease: scope?.disease, genes: scope?.genes })}
            onNewChat={startClaraChat}
            onChatId={setClaraChatId}
          />
        </div>
      )}

      {/* ---- Clara Notification Bubble ---- */}
      {active && !claraOpen && claraNotif && (
        <div className="clara-bubble" onClick={tryOpenClara} data-testid="clara-entry">
          <div className="clara-bubble-avatar">C</div>
          <div className="clara-bubble-text">
            {signedIn ? (
              <>
                <strong>Clara is supervising this run</strong>
                <span>Controls the causal chain &rarr;</span>
              </>
            ) : (
              <>
                <strong>Please sign in</strong>
                <span>Clara unlocks once you have an account</span>
              </>
            )}
          </div>
          <button className="clara-bubble-close" onClick={(e) => { e.stopPropagation(); setClaraNotif(false); }} aria-label="Dismiss">
            <svg viewBox="0 0 12 12" width="10" height="10"><path d="M2 2l8 8M10 2l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
          </button>
        </div>
      )}
      {active && !claraOpen && !claraNotif && (
        <button type="button" className="clara-fab" onClick={tryOpenClara} aria-label="Open Clara">
          C
        </button>
      )}

      <footer>
        <span>BioLead &middot; source-linked &middot; contradiction-aware &middot; abstention-first</span>
        <span>v{sc?.scoring_version ?? "1.0.0"}</span>
      </footer>
    </div>
  );
}
