/**
 * TypeScript mirrors of the FastAPI / Pydantic response models.
 *
 * Source of truth: app/models/*.py in the backend. Optional[...] fields are typed as
 * `T | null` because Pydantic serialises missing optionals as JSON null. Keep these in
 * sync with the backend when response models change.
 */

// ── Shared enums ────────────────────────────────────────────

/** app/models/market.py::MarketIdentifier */
export type MarketId = "us_sec" | "gh_gse";

/** app/models/market.py::DocumentSourceType */
export type DocumentSourceType =
  | "sec_10k"
  | "annual_report"
  | "sustainability_report"
  | "integrated_report"
  | "investor_presentation"
  | "unknown";

/** app/models/evaluation.py::AssessmentCategory */
export type AssessmentCategory =
  | "supported"
  | "partially_supported"
  | "inconsistent"
  | "unsubstantiated"
  | "insufficient_evidence";

/** app/models/evaluation.py::EvaluationConfidence */
export type EvaluationConfidence = "high" | "medium" | "low";

/** app/models/evaluation.py::EvaluationMode */
export type EvaluationMode = "llm" | "rule_based";

/** app/models/scoring.py::ScoreStatus */
export type ScoreStatus = "scored" | "insufficient_data";

/** app/models/scoring.py::ConfidenceLevel */
export type ConfidenceLevel = "high" | "medium" | "low" | "insufficient";

export type PillarKey = "environmental" | "social" | "governance";

// ── System ──────────────────────────────────────────────────

/** GET /health */
export interface HealthResponse {
  status: string;
  app: string;
  environment: string;
}

// ── US SEC ──────────────────────────────────────────────────

/** app/models/company.py::Company */
export interface SecCompany {
  ticker: string;
  company_name: string;
  cik: string;
  exchange: string | null;
  sic: string | null;
  sic_description: string | null;
}

/** app/models/filing.py::SECFiling */
export interface SecFiling {
  form_type: string;
  filing_date: string;
  report_date: string | null;
  accession_number: string;
  primary_document: string;
  filing_url: string;
  filing_index_url: string | null;
  fiscal_year: number | null;
  is_amendment: boolean;
}

/** app/models/filing.py::CompanyFilingsResponse */
export interface SecFilingsResponse {
  company: SecCompany;
  filings: SecFiling[];
  total_count: number;
}

/** app/models/filing.py::CompanyLatestFilingResponse */
export interface SecLatestFilingResponse {
  company: SecCompany;
  filing: SecFiling;
}

/** app/models/document.py::DocumentMetadataResponse */
export interface SecDocumentMetadataResponse {
  company: SecCompany;
  accession_number: string;
  form_type: string;
  filing_date: string;
  report_date: string | null;
  source_url: string;
  title: string | null;
  word_count: number;
  character_count: number;
  total_sections: number;
  detected_sections: string[];
}

// ── Ghana GSE ───────────────────────────────────────────────

/** app/models/market.py::GSECompany */
export interface GseCompany {
  ticker: string;
  company_name: string;
  market: MarketId;
  isin: string | null;
  sector: string | null;
  industry: string | null;
  currency: string;
  shares_outstanding: number | null;
  market_cap: number | null;
  year_listed: number | null;
  website: string | null;
}

/** app/models/market.py::MarketDocument */
export interface MarketDocument {
  document_id: string;
  company_ticker: string;
  company_name: string;
  market: MarketId;
  source_type: DocumentSourceType;
  title: string;
  reporting_period: string | null;
  publication_date: string | null;
  source_url: string | null;
  /** pending | retrieved | failed | unavailable */
  retrieval_status: string;
  text_content: string | null;
  text_length: number | null;
  word_count: number | null;
  page_count: number | null;
  format: string;
  error_message: string | null;
}

/** app/models/market.py::GSECompanyListResponse */
export interface GseCompanyListResponse {
  companies: GseCompany[];
  total_count: number;
  market: MarketId;
}

/** app/models/market.py::GSECompanyDetailResponse */
export interface GseCompanyDetailResponse {
  company: GseCompany;
  documents: MarketDocument[];
}

// ── Evaluation ──────────────────────────────────────────────

/** app/models/evaluation.py::EvidenceReference */
export interface EvidenceReference {
  evidence_id: string;
  section_id: string;
  relevance_score: number;
  relationship: string;
  quote: string;
}

/** app/models/evaluation.py::ClaimEvaluation */
export interface ClaimEvaluation {
  evaluation_id: string;
  claim_id: string;
  company_ticker: string;
  company_name: string;
  claim_text: string;
  claim_type: string;
  category: string;
  category_group: string;
  assessment: AssessmentCategory;
  confidence: EvaluationConfidence;
  reasoning: string;
  caveats: string[];
  referenced_evidence: EvidenceReference[];
  evaluation_mode: EvaluationMode;
  model_name: string | null;
  created_at: string;
}

/** app/models/evaluation.py::SingleClaimEvaluationResponse */
export interface SingleClaimEvaluationResponse {
  evaluation: ClaimEvaluation;
  provider_mode: string;
}

// ── Scoring ─────────────────────────────────────────────────

/** app/models/scoring.py::DimensionalScore */
export interface DimensionalScore {
  dimension: string;
  score: number | null;
  status: ScoreStatus;
  weight: number;
  effective_weight: number;
  claims_count: number;
  assessable_claims_count: number;
  supported_count: number;
  partially_supported_count: number;
  inconsistent_count: number;
  unsubstantiated_count: number;
  insufficient_evidence_count: number;
  evidence_coverage: number;
  confidence: ConfidenceLevel;
  key_factors: string[];
}

/** app/models/scoring.py::ClaimScoreDetail */
export interface ClaimScoreDetail {
  claim_id: string;
  evaluation_id: string;
  claim_text: string;
  claim_type: string;
  category: string;
  category_group: string;
  assessment: AssessmentCategory;
  base_score: number;
  evidence_quality_adjustment: number;
  quality_adjustment_reasons: string[];
  claim_score: number;
  materiality_weight: number;
  effective_weight: number;
  included_in_score: boolean;
  is_quantified: boolean;
  sector_priority_match: boolean;
  referenced_evidence_ids: string[];
  referenced_evidence: EvidenceReference[];
  caveats_count: number;
  reasoning: string;
}

/** app/models/scoring.py::ESGIntegrityScoreResponse */
export interface EsgIntegrityScore {
  company_name: string;
  ticker: string;
  market: MarketId;
  reporting_period: string | null;
  esg_integrity_score: number | null;
  score_status: ScoreStatus;
  confidence: ConfidenceLevel;
  evidence_coverage: number;
  substantiation_rate: number | null;
  environmental_score: number | null;
  social_score: number | null;
  governance_score: number | null;
  total_claims_extracted: number;
  total_claims_assessed: number;
  supported_claims: number;
  partially_supported_claims: number;
  inconsistent_claims: number;
  unsubstantiated_claims: number;
  insufficient_evidence_claims: number;
  unmapped_claims: number;
  duplicate_evaluations_ignored: number;
  rule_based_evaluations: number;
  llm_evaluations: number;
  main_positive_factors: string[];
  main_concerns: string[];
  methodology_version: string;
  assessment_timestamp: string;
  source_document_references: string[];
  disclaimer: string;
}

/**
 * Shape of `materiality_summary` as built in scoring_service.calculate_score_from_evaluations.
 * The Pydantic type is Dict[str, Any], so every key is treated as optional.
 */
export interface MaterialitySummary {
  sector?: string | null;
  industry?: string | null;
  matched_sector_profile?: string | null;
  sector_priority_matches?: number;
  quantified_claims?: number;
  [key: string]: unknown;
}

export interface AssessmentBand {
  base: number;
  min: number;
  max: number;
}

/**
 * Shape of `methodology_details` as built in scoring_service.calculate_score_from_evaluations.
 * Dict[str, Any] on the backend, so keys are optional here.
 */
export interface MethodologyDetails {
  version?: string;
  assessment_bands?: Partial<Record<AssessmentCategory, AssessmentBand>>;
  insufficient_evidence_treatment?: string;
  claim_type_materiality?: Record<string, number>;
  quantified_multiplier?: number;
  sector_priority_multiplier?: number;
  low_materiality_threshold?: number;
  low_materiality_max_share?: number;
  pillar_base_weights?: Partial<Record<PillarKey, number>>;
  min_assessable_claims?: number;
  confidence_capped_for_rule_based?: boolean;
  rounding?: string;
  [key: string]: unknown;
}

/** app/models/scoring.py::ESGScoreBreakdownResponse */
export interface EsgScoreBreakdown extends EsgIntegrityScore {
  dimensions: Partial<Record<PillarKey, DimensionalScore>> & Record<string, DimensionalScore>;
  claim_scores: ClaimScoreDetail[];
  materiality_summary: MaterialitySummary;
  methodology_details: MethodologyDetails;
}

/** app/models/scoring.py::ESGScoreHistoryResponse */
export interface EsgScoreHistory {
  company_name: string;
  ticker: string;
  market: MarketId;
  total_records: number;
  history: EsgIntegrityScore[];
  note: string;
}

// ── Error payloads ──────────────────────────────────────────

/** Custom exception handlers in app/main.py return { detail, error }. */
export interface BackendErrorBody {
  detail?: string | ValidationIssue[];
  error?: string;
}

/** FastAPI request-validation 422 items. */
export interface ValidationIssue {
  loc?: (string | number)[];
  msg?: string;
  type?: string;
}
