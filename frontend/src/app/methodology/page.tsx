import type { Metadata } from "next";
import { AssessmentBadge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { Notice } from "@/components/ui/states";
import type { AssessmentCategory } from "@/lib/api/types";

export const metadata: Metadata = { title: "Methodology & Transparency" };

/*
 * Content transcribed from docs/ESG_INTEGRITY_SCORE_METHODOLOGY.md (methodology version 1.0.0).
 * Update this page when the methodology document changes. Live parameters for each run are also returned
 * by the score breakdown (`methodology_details`) and shown on the assessment and claim screens.
 */

const SECTIONS = [
  ["measures", "What the score measures"],
  ["not", "What it does not measure"],
  ["pipeline", "Scoring pipeline"],
  ["bands", "Claim scoring bands"],
  ["quality", "Evidence-quality adjustments"],
  ["materiality", "Materiality & volume damping"],
  ["pillars", "E / S / G weighting"],
  ["reliability", "Coverage, substantiation & confidence"],
  ["missing", "Missing data"],
  ["sector", "Sector materiality"],
  ["limitations", "Limitations"],
  ["versioning", "Versioning"],
] as const;

const BANDS: { a: AssessmentCategory; base: string; band: string; meaning: string }[] = [
  { a: "supported", base: "90", band: "80 – 100", meaning: "Retrieved disclosure evidence directly substantiates the claim." },
  { a: "partially_supported", base: "60", band: "50 – 70", meaning: "Evidence supports part of the claim but introduces material caveats, scope restrictions or incomplete progress." },
  { a: "unsubstantiated", base: "25", band: "15 – 35", meaning: "Relevant context exists but does not substantiate the assertion. Partial credit, because a lack of documentation is not proof of falsity." },
  { a: "inconsistent", base: "0", band: "0 (fixed)", meaning: "Disclosed facts, timelines or metrics directly contradict the claim. Fixed at 0 so confidence in a contradiction cannot award points." },
  { a: "insufficient_evidence", base: "Excluded", band: "—", meaning: "No relevant evidence was retrieved. Excluded from numerator and denominator; reduces evidence coverage instead." },
];

const QUALITY = [
  ["Evaluation confidence is high", "+3", "Strong, unambiguous match between claim and cited passages."],
  ["Evaluation confidence is low", "−3", "Weak or borderline match."],
  ["Mean relevance of cited evidence ≥ 0.40", "+3", "Cited evidence addresses the same concepts, metrics and timeframe."],
  ["Mean relevance of cited evidence < 0.20", "−3", "Weak topical overlap between claim and cited passages."],
  ["No validated evidence citation", "−3", "The assessment lacked a traceable filing citation."],
  ["Caveats or scope limits identified", "−2 each (max −6)", "Material exclusions or conditional language noted by the evaluator."],
];

const TYPE_WEIGHTS = [
  ["Achievement", "1.5", "Concrete completed outcomes — highest verification importance."],
  ["Target", "1.3", "Measurable forward-looking commitments."],
  ["Current state", "1.2", "Current operational metrics or baselines."],
  ["Policy", "0.9", "Governance standards, codes of conduct, formal policies."],
  ["General (or unknown)", "0.6", "High-level aspirational or introductory statements."],
];

const PILLAR_WEIGHTS = [
  ["Environmental", "40%", "Prevalence and measurability of emissions, energy, water, waste and climate claims."],
  ["Social", "35%", "Workforce safety, diversity and inclusion, human rights, labour, supply chain, community."],
  ["Governance", "25%", "Board oversight, ethics, compliance, anti-corruption and transparency controls."],
];

const CONFIDENCE = [
  ["High", "≥ 10 assessable E/S/G claims, evidence coverage ≥ 70%, at least 2 pillars scored, and LLM-assisted evaluations."],
  ["Medium", "≥ 5 assessable claims and coverage ≥ 50% — or meets High thresholds while using the rule-based fallback."],
  ["Low", "3–4 assessable claims, or evidence coverage below 50%."],
  ["Insufficient", "Fewer than 3 assessable claims; no score is computed."],
];

const SECTORS = [
  ["Mining", "mining, mines, gold, minerals, metal ores", "Water, pollution, waste, biodiversity, health & safety, community, human rights, galamsey, tailings, land rehabilitation, cyanide"],
  ["Oil & gas", "oil, gas, petroleum, crude, refining", "Emissions, GHG, carbon, climate, pollution, health & safety, community, oil spill, gas flaring"],
  ["Agriculture", "agriculture, cocoa, plantations, palm, farming", "Biodiversity, water, supply chain, labour, human rights, cocoa, palm oil, deforestation, smallholder"],
  ["Banking", "banking, financial, insurance, microfinance, savings", "Governance, ethics, compliance, risk management, financial inclusion, mobile money, AML, data protection"],
  ["Telecommunications", "telecom, mobile, wireless", "Energy, renewables, carbon, emissions, waste, digital inclusion, e-waste, mobile money, data privacy"],
  ["Technology", "computers, electronics, software, semiconductors", "Energy, renewables, carbon, supply chain, recycling, e-waste, conflict minerals, data privacy"],
  ["Manufacturing", "manufacturing, industrial, cement, steel, chemicals", "Emissions, energy, waste, pollution, water, health & safety, labour, effluent"],
  ["Consumer goods", "consumer, beverages, breweries, food, household", "Waste, recycling, water, supply chain, circular economy, packaging, plastics"],
];

function H({ id, n, children }: { id: string; n: number; children: React.ReactNode }) {
  return (
    <h2 id={id} className="scroll-mt-24 font-serif text-[21px] font-semibold text-text">
      <span className="tabular mr-2 font-sans text-[13px] font-medium text-text-subtle">{String(n).padStart(2, "0")}</span>
      {children}
    </h2>
  );
}

function P({ children }: { children: React.ReactNode }) {
  return <p className="mt-3 max-w-3xl text-[14px] leading-relaxed text-text-muted [&_strong]:text-text">{children}</p>;
}

function Table({ head, rows, firstMono }: { head: string[]; rows: React.ReactNode[][]; firstMono?: boolean }) {
  return (
    <div className="mt-4 overflow-x-auto rounded-lg border border-line bg-surface">
      <table className="w-full min-w-[520px] text-left text-[13px]">
        <thead className="border-b border-line bg-surface-muted text-[11px] tracking-wider text-text-subtle uppercase">
          <tr>
            {head.map((h) => (
              <th key={h} scope="col" className="px-4 py-2.5 font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {rows.map((r, i) => (
            <tr key={i} className="align-top">
              {r.map((c, j) => (
                <td
                  key={j}
                  className={
                    j === 0
                      ? `px-4 py-2.5 font-medium text-text ${firstMono ? "font-mono" : ""}`
                      : j === r.length - 1
                        ? "px-4 py-2.5 leading-relaxed text-text-muted"
                        : "tabular px-4 py-2.5 whitespace-nowrap text-text"
                  }
                >
                  {c}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Formula({ children }: { children: React.ReactNode }) {
  return (
    <div className="mt-4 max-w-3xl overflow-x-auto rounded-md bg-ink-900 px-4 py-3 font-mono text-[13px] leading-relaxed text-ink-200">
      {children}
    </div>
  );
}

export default function MethodologyPage() {
  return (
    <div>
      <PageHeader
        eyebrow={<span>Methodology version 1.0.0</span>}
        title="Methodology & Transparency"
        description="How the ESG Integrity Score is calculated, what it can and cannot tell you, and how missing information is handled. Written for both analysts and business readers."
      />

      <div className="grid gap-8 lg:grid-cols-[13rem_minmax(0,1fr)]">
        <nav aria-label="Methodology sections" className="hidden lg:block">
          <ol className="sticky top-20 space-y-1 border-l border-line text-[13px]">
            {SECTIONS.map(([id, label], i) => (
              <li key={id}>
                <a href={`#${id}`} className="-ml-px block border-l border-transparent py-1 pl-3 text-text-muted hover:border-forest-500 hover:text-text">
                  <span className="tabular mr-1.5 text-text-subtle">{i + 1}.</span>
                  {label}
                </a>
              </li>
            ))}
          </ol>
        </nav>

        <article className="min-w-0 space-y-12">
          <Notice title="No model chooses a number">
            Scores are calculated deterministically from claim evaluations. No language model invents, chooses or adjusts
            any score; identical inputs and settings always produce identical results. Each assessment response also
            returns the exact parameters it used.
          </Notice>

          <section aria-labelledby="measures">
            <H id="measures" n={1}>What the ESG Integrity Score measures</H>
            <P>
              The ESG Integrity Score (0 to 100) measures <strong>the credibility and evidence substantiation of a
              company&apos;s disclosed sustainability and ESG claims</strong>, based on the disclosure evidence retrieved by
              the platform. It evaluates whether evidence in the company&apos;s own filings or reports corroborates,
              qualifies, contradicts or fails to substantiate each extracted claim; whether high-materiality, quantified and
              sector-relevant disclosures are backed by stronger evidence than generic statements; and how much of the
              reporting has verifiable supporting context.
            </P>
            <P>
              A <strong>higher score</strong> means the company&apos;s assessable claims in the analysed document are
              consistently backed by aligned disclosure evidence rather than contradicted or left unsubstantiated.
            </P>
          </section>

          <section aria-labelledby="not">
            <H id="not" n={2}>What it does not measure</H>
            <ul className="mt-4 grid max-w-3xl gap-2 text-[14px] leading-relaxed text-text-muted sm:grid-cols-2">
              {[
                ["A complete ESG performance rating", "A low-footprint company with poorly documented claims can score below a high emitter with candid, verifiable disclosures."],
                ["Total environmental or social impact", "It evaluates disclosure integrity, not physical emissions or outcomes on the ground."],
                ["Proof of greenwashing", "Greenwashing is a legal determination. 'Unsubstantiated' means disclosures did not establish a claim — not that it is false."],
                ["An audit or assurance", "It is no substitute for independent third-party ESG audits or assurance."],
                ["A validated index", "Version 1.0.0 weights and bands are transparent analytical defaults, not calibrated coefficients."],
                ["Investment advice", "It is not financial or investment advice."],
              ].map(([t, d]) => (
                <li key={t} className="rounded-lg border border-line bg-surface p-3.5">
                  <p className="font-medium text-text">{t}</p>
                  <p className="mt-1 text-[13px]">{d}</p>
                </li>
              ))}
            </ul>
          </section>

          <section aria-labelledby="pipeline">
            <H id="pipeline" n={3}>Scoring pipeline</H>
            <ol className="mt-4 max-w-3xl space-y-3 text-[14px] leading-relaxed text-text-muted">
              <li><strong className="text-text">Deduplicate and filter.</strong> Duplicate evaluations of the same claim are ignored. Claims not mapped to Environmental, Social or Governance are reported but excluded from scores.</li>
              <li><strong className="text-text">Score each claim.</strong> The assessment outcome sets a non-overlapping score band; a bounded evidence-quality adjustment is applied inside that band.</li>
              <li><strong className="text-text">Weight each claim.</strong> Claim-type weight × quantification multiplier × sector-priority multiplier.</li>
              <li><strong className="text-text">Aggregate into pillars.</strong> Low-materiality claims are volume-damped, then a weighted average of claim scores is taken per pillar.</li>
              <li><strong className="text-text">Aggregate overall.</strong> Scored pillars are combined with base weights scaled by thin-pillar sufficiency and normalised across the pillars that have scores.</li>
            </ol>
            <Formula>
              Pillar score = round( Σ effective_weight × claim_score ÷ Σ effective_weight )
              <br />
              Pillar weight = base_weight × min(1, assessable_claims ÷ 3)
              <br />
              Overall score = round( Σ pillar_weight × pillar_score ÷ Σ pillar_weight ) — scored pillars only
            </Formula>
          </section>

          <section aria-labelledby="bands">
            <H id="bands" n={4}>Claim scoring bands</H>
            <P>
              Each claim is placed in a band determined by its assessment. Bands are separated by at least 10 points, so
              evidence-quality adjustments can never lift an unsubstantiated claim above a partially supported one, or a
              partially supported claim above a supported one.
            </P>
            <Table
              head={["Assessment", "Base", "Band", "Meaning"]}
              rows={BANDS.map((b) => [<AssessmentBadge key={b.a} value={b.a} />, b.base, b.band, b.meaning])}
            />
          </section>

          <section aria-labelledby="quality">
            <H id="quality" n={5}>Evidence-quality adjustments</H>
            <P>
              For supported, partially supported and unsubstantiated claims, an additive adjustment within ±10 points is
              applied and the result is clamped to the band. Where filings document independent assurance, relevance and
              confidence rise, allowing supported claims to reach 96–100; the <strong>absence of assurance is never treated
              as proof</strong> that a claim is false.
            </P>
            <Table head={["Signal", "Points", "Rationale"]} rows={QUALITY} />
          </section>

          <section aria-labelledby="materiality">
            <H id="materiality" n={6}>Claim materiality & volume damping</H>
            <Formula>materiality_weight = type_weight × quantified (1.2× or 1.0×) × sector_priority (1.3× or 1.0×)</Formula>
            <Table head={["Claim type", "Weight", "Rationale"]} rows={TYPE_WEIGHTS} />
            <P>
              <strong>Quantified (1.2×)</strong> applies to percentages, currency amounts, numbers with physical or
              workforce units, and explicit deadline years such as &ldquo;by 2030&rdquo;. Bare calendar years such as
              &ldquo;2024 Annual Report&rdquo; are deliberately ignored. <strong>Sector priority (1.3×)</strong> applies
              when the claim matches high-materiality themes for the company&apos;s sector.
            </P>
            <P>
              <strong>Volume damping.</strong> Claims with a weight below 1.0 are low-materiality. When a pillar has at
              least one high-materiality claim, the combined effective weight of its low-materiality claims is capped at
              25% of the pillar&apos;s total weight. Adding more boilerplate beyond the cap scales each item down, leaving
              the pillar score unchanged — a company cannot dilute contradicted material claims with trivial statements.
            </P>
          </section>

          <section aria-labelledby="pillars">
            <H id="pillars" n={7}>Environmental, Social & Governance weighting</H>
            <P>Pillars are scored separately so weak governance or social disclosures are not masked by strong environmental claims.</P>
            <Table head={["Pillar", "Base weight", "Rationale"]} rows={PILLAR_WEIGHTS} />
            <P>
              A pillar with 1 or 2 assessable claims enters the overall average at a fraction of its base weight
              (assessable claims ÷ 3). Weights are configurable on the backend; each assessment reports the weights it used.
            </P>
          </section>

          <section aria-labelledby="reliability">
            <H id="reliability" n={8}>Evidence coverage, substantiation rate & confidence</H>
            <P>Always read the score alongside its three reliability indicators.</P>
            <Table
              head={["Indicator", "Definition", "What it tells you"]}
              rows={[
                ["Evidence coverage", "(assessed − insufficient evidence) ÷ assessed", "Data availability: was relevant evidence found? High coverage does not mean claims were corroborated."],
                ["Substantiation rate", "(supported + partially supported) ÷ assessable claims", "Corroboration ratio. Not available when there are no assessable claims."],
                ["Confidence", "high · medium · low · insufficient", "Sample size and method reliability (thresholds below)."],
              ]}
            />
            <Table head={["Confidence", "Required conditions"]} rows={CONFIDENCE} />
            <P>
              <strong>Rule-based cap.</strong> When no LLM is configured and every claim is assessed by deterministic
              keyword and relationship heuristics, confidence is capped at medium.
            </P>
          </section>

          <section aria-labelledby="missing">
            <H id="missing" n={9}>Treatment of missing information</H>
            <ul className="mt-4 max-w-3xl space-y-3 text-[14px] leading-relaxed text-text-muted">
              <li><strong className="text-text">Minimum of 3 assessable claims.</strong> Below this, no overall score is produced: the score is null and the status is &ldquo;insufficient data&rdquo;.</li>
              <li><strong className="text-text">Missing pillars are null, never zero.</strong> A pillar without assessable claims is shown as Insufficient Data, its weight is excluded, and the gap is listed among the main concerns.</li>
              <li><strong className="text-text">Insufficient-evidence claims are excluded.</strong> They are not punished as contradictions; they lower evidence coverage instead.</li>
              <li><strong className="text-text">No fabricated history.</strong> History lists only assessments computed by the running backend session, stored in memory.</li>
            </ul>
          </section>

          <section aria-labelledby="sector">
            <H id="sector" n={10}>Ghana (GSE) and sector-specific considerations</H>
            <P>
              Identical bands, weights and thresholds apply to US SEC and Ghana Stock Exchange companies; <strong>market
              origin never raises or lowers a score</strong>. Sector multipliers depend only on the company&apos;s sector
              classification (sector / industry for GSE; SIC description for SEC). Criteria never cross sectors — for
              example, mining themes are not applied to banks — and unmatched sectors receive no multiplier.
            </P>
            <Table head={["Sector profile", "Trigger keywords", "High-materiality themes (1.3×)"]} rows={SECTORS} />
          </section>

          <section aria-labelledby="limitations">
            <H id="limitations" n={11}>Known limitations</H>
            <ul className="mt-4 max-w-3xl space-y-3 text-[14px] leading-relaxed text-text-muted">
              <li><strong className="text-text">Single document scope.</strong> Claims are evaluated within the analysed 10-K or GSE report. External news, satellite monitoring and third-party databases are out of scope.</li>
              <li><strong className="text-text">Rule-based fallback.</strong> Without an LLM key, evaluations use keyword heuristics; nuance in long PDF tables may be marked unsubstantiated.</li>
              <li><strong className="text-text">In-memory history.</strong> No database persistence; history clears on server restart.</li>
              <li><strong className="text-text">No external validation.</strong> Version 1.0.0 defaults are not statistically calibrated or independently audited.</li>
            </ul>
          </section>

          <section aria-labelledby="versioning">
            <H id="versioning" n={12}>Rounding, traceability & versioning</H>
            <P>
              Scores and percentages are rounded to whole numbers to avoid false precision. Every breakdown preserves claim
              and evaluation IDs, cited evidence, quality-adjustment reasons, multipliers, effective weights and source
              document references. Methodology changes follow semantic versioning (major: band or formula changes; minor:
              new sector profiles or fields; patch: fixes), and history records keep the version used.
            </P>
          </section>

          <Card className="p-5 text-[13px] leading-relaxed text-text-muted">
            Source: <span className="font-mono text-text">docs/ESG_INTEGRITY_SCORE_METHODOLOGY.md</span> in the project
            repository. Parameters shown on assessment screens come from the backend response for that run.
          </Card>
        </article>
      </div>
    </div>
  );
}
