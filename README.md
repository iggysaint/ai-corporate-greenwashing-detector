# AI Corporate Greenwashing Detector

An analytical and research platform designed to evaluate public corporate sustainability and ESG claims against official SEC regulatory filings and disclosures.

---

## 1. Project Overview & Problem Statement

Corporate sustainability reports and public Environmental, Social, and Governance (ESG) marketing often feature ambitious commitments—such as carbon neutrality milestones, renewable energy targets, and fair-labor practices. However, verifying whether these claims are substantiated by legally binding disclosures requires labor-intensive manual review of extensive regulatory filings.

The **AI Corporate Greenwashing Detector** provides an objective, evidence-driven analysis pipeline to cross-examine public sustainability claims against disclosures submitted to regulatory bodies such as the U.S. Securities and Exchange Commission (SEC).

### Core Analytical Tenet
This platform is strictly an **analytical and research application**. It does **not** make unsupported legal accusations that a company is committing fraud or greenwashing. Instead, all findings are grounded in auditable evidence and classified into objective assessment categories:

- **Supported**: Verifiable evidence in official filings supports the claim.
- **Partially Supported**: Filings provide evidence for portions of the claim, but key elements remain unverified or qualified.
- **Inconsistent**: Evidence in regulatory disclosures directly contradicts or disputes the public claim.
- **Unsubstantiated**: No evidence was found in disclosures to substantiate the claim.
- **Insufficient Evidence**: Public disclosures lack sufficient detail to evaluate the claim definitively.

The system prioritizes **traceability and primary evidence** over unconstrained AI generation.

---

## 2. Conceptual Future Pipeline

When fully developed across subsequent phases, the application will operate along this conceptual pipeline:

```
Company Stock Ticker (e.g., AAPL, MSFT, AMZN, TSLA)
  │
  ▼
Company Identification & CIK Resolution                    [PHASE 2 - IMPLEMENTED]
  │
  ▼
Public Filings Discovery (SEC EDGAR: 10-K, 10-K/A)          [PHASE 2 - IMPLEMENTED]
  │
  ▼
Filing Retrieval & Document Ingestion                      [PHASE 3 - IMPLEMENTED]
  │
  ▼
HTML Normalization & Section Extraction (Items 1, 1A, 7)   [PHASE 3 - IMPLEMENTED]
  │
  ▼
Traceable ESG Passage Retrieval (Evidence Grounding)        [PHASE 3 - IMPLEMENTED]
  │
  ▼
Sustainability Claims Identification                       [PHASE 4 - IMPLEMENTED]
  │
  ▼
Evidence & Cross-Reference Engine                           [PHASE 5 - IMPLEMENTED]
  │
  ▼
LLM Analysis & Verification Reasoning                      [PHASE 6 - FUTURE]
  │
  ▼
ESG Integrity Score & Dashboard                            [PHASE 6 - FUTURE]
```

---

## 3. Current Development Phase

> **Current Phase: PHASE 5 — EVIDENCE & CROSS-REFERENCE ENGINE**

### Implemented in Phase 5: Evidence & Cross-Reference Engine

- **Structured Evidence Models** ([`app/models/evidence.py`](file:///c:/Users/CALDWELL%20N.%20ARTHUR/ai-corporate-%20greenwashing-detector/app/models/evidence.py)): Pydantic models for `Evidence`, `ClaimEvidenceResult`, `EvidenceSummaryResponse`, and `CompanyEvidenceResponse` preserving complete source traceability back to the SEC EDGAR filing, section, and character position.
- **Deterministic Cross-Reference Engine** ([`app/services/evidence_service.py`](file:///c:/Users/CALDWELL%20N.%20ARTHUR/ai-corporate-%20greenwashing-detector/app/services/evidence_service.py)): Pairs each extracted sustainability claim with filing evidence passages without using an LLM.
- **Controlled Relationship Vocabulary**:
  - `supporting`: Filing disclosure substantiates or corroborates the commitment, milestone, or policy.
  - `contradictory`: Filing disclosure reports contradictory actual performance data for the same metric within the same reporting period.
  - `qualifying`: Filing disclosure introduces conditions, feasibility constraints, or limited operational scope (`subject to`, `where feasible`, `selected facilities`).
  - `contextual`: General subject-matter context, background, or Item 1A Risk Factor disclosures.
  - `insufficient_evidence`: Explicit classification when no meaningful evidence exists in the filing. Evidence is never fabricated.
- **Transparent Relevance Scoring Formula (0.0–1.0)**:
  $$\text{Score} = (\text{Overlap Ratio} \times 0.40) + (\text{Metric Bonus} \times 0.20) + (\text{Year Bonus} \times 0.15) + (\text{Value Bonus} \times 0.15) + (\text{Section Bonus} \times 0.10)$$
- **Core Guardrails & Conservative Principles**:
  - Item 1A (Risk Factors) passages and pure risk statements are classified as `contextual` (or `qualifying`), never `supporting` or `contradictory`.
  - Differing numbers across different fiscal years are guarded against false contradiction flags.
  - Deduping ensures passages discovered across multiple concepts merge matched terms and concepts into a unified record.
- **Evidence API Endpoints**: Three REST endpoints for full company evidence, single-claim evidence, and statistical summaries.
- **In-Memory Evidence Caching**: Evidence retrieval results are cached per accession number.

> [!IMPORTANT]
> **Phase 5 classifies evidence passages based on deterministic retrieval rules only. It does NOT determine whether a company is committing greenwashing, fraud, or legal violations.** No LLM, subjective bias, or ESG score is produced in Phase 5. Evidence records are structured inputs prepared for downstream reasoning.

---

### Phase 4 Claim Data Model

Each extracted [`Claim`](file:///c:/Users/CALDWELL%20N.%20ARTHUR/ai-corporate-%20greenwashing-detector/app/models/claim.py) record includes:

| Field | Description |
|---|---|
| `claim_id` | Stable SHA-256-derived unique identifier |
| `company_ticker` | Exchange ticker symbol |
| `company_name` | Full company name |
| `claim_text` | Verbatim extracted sentence from the filing |
| `claim_type` | Controlled vocabulary (see below) |
| `category` | Fine-grained ESG category (see below) |
| `category_group` | High-level group: `environmental`, `social`, or `governance` |
| `source_type` | Source document type (e.g., `sec_10k`) |
| `source_title` | Document title |
| `source_url` | Canonical SEC Archives URL |
| `filing_accession_number` | SEC accession number for the source filing |
| `filing_date` | Date the filing was submitted |
| `report_date` | Fiscal period end date |
| `section_id` | 10-K section identifier (e.g., `item_1`, `item_1a`) |
| `section_title` | 10-K section title (e.g., `Item 1. Business`) |
| `source_excerpt` | Verbatim sentence (same as `claim_text`) |
| `additional_sources` | List of `SourceReference` objects if same claim appears in multiple sections |
| `target_value` | Quantitative target if present (e.g., `"100%"`) |
| `target_year` | Target year if present (e.g., `2030`) |
| `baseline_year` | Baseline year if present |
| `metric` | Metric keyword if detectable (e.g., `"emissions"`, `"renewable"`) |
| `unit` | Unit label if present (e.g., `"%"`, `"MW"`) |
| `extraction_method` | Always `"deterministic"` in Phase 4 |
| `confidence` | `"high"` / `"medium"` / `"low"` |
| `status` | `"validated"` or `"candidate"` |

---

### Claim Type Vocabulary

| `claim_type` | Meaning |
|---|---|
| `target` | A forward-looking commitment, goal, or pledge |
| `achievement` | A past accomplishment or result |
| `current_state` | A present-tense operational fact or metric |
| `policy` | A policy, standard, framework, or code of conduct |
| `general` | A general sustainability-related statement |

---

### ESG Category Vocabulary

**Environmental** categories: `carbon_emissions`, `renewable_energy`, `energy_efficiency`, `water_management`, `waste_reduction`, `biodiversity`, `circular_economy`, `climate_risk`, `net_zero`, `sustainability`

**Social** categories: `inclusion`, `labor_practices`, `health_safety`, `community`, `supply_chain`, `human_rights`, `data_privacy`, `employee_development`

**Governance** categories: `board_governance`, `executive_compensation`, `ethics_compliance`, `transparency_reporting`, `risk_management`

---

### Previously Implemented (Phase 3)

- **SEC Filing Retrieval**: Direct download of primary 10-K / 10-K/A HTML documents from official SEC Archives.
- **Document Service**: HTML cleaning, normalization, section detection, and passage extraction.
- **Section Detection Engine**: Distinguishes TOC entries from body sections via dot-leader filtering and last-occurrence selection.
- **Traceable ESG Passage Extraction**: Deterministic keyword scanner preserving section, offset, and URL provenance.
- **In-Memory Caching**: Parsed documents cached by accession number.

### Deferred to Later Phases
- LLM-assisted claim interpretation and evidence cross-examination
- External sustainability report / CSR website scraping
- AI-generated objective assessments (Supported / Partially Supported / Inconsistent / Unsubstantiated)
- Deterministic ESG Integrity scoring algorithms
- Database persistence and web frontend UI

---

## 4. SEC Data Source & User-Agent Guidelines

The primary source for corporate filings is the official SEC EDGAR public data infrastructure:
- Company Tickers: `https://www.sec.gov/files/company_tickers.json`
- Company Submissions: `https://data.sec.gov/submissions/CIK{cik_10_digits}.json`
- SEC Archives: `https://www.sec.gov/Archives/edgar/data/{cik_numeric}/{accession_no}/{document}`

### Required SEC User-Agent Configuration
Per [SEC EDGAR Access Guidelines](https://www.sec.gov/os/accessing-edgar-data), automated requests must provide a custom `User-Agent` header containing contact information:
```
User-Agent: Sample Company Name AdminContact@<sample company domain>.com
```

Configured in `app/utils/config.py` and `.env`:
```env
SEC_USER_AGENT=AI Corporate Greenwashing Detector (mr.ignatiusarthur@gmail.com)
SEC_REQUEST_TIMEOUT=30.0
```

---

## 5. Technology Stack

- **Language & Runtime**: Python 3.10+
- **Web Framework**: FastAPI, Uvicorn
- **Configuration & Validation**: Pydantic, pydantic-settings, python-dotenv
- **HTTP & Data Retrieval**: HTTPX, Requests
- **Document Parsing**: BeautifulSoup4, lxml
- **Testing**: pytest, pytest-asyncio

---

## 6. Project Structure

```
ai-corporate-greenwashing-detector/
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI entrypoint, exception handlers & routing
│   │
│   ├── api/
│   │   ├── __init__.py          # API route exports
│   │   ├── company_routes.py    # Company, filing, document & claim endpoints
│   │   └── evidence_routes.py   # Evidence & cross-reference endpoints (Phase 5)
│   │
│   ├── services/
│   │   ├── __init__.py          # Service exports
│   │   ├── sec_service.py       # SEC EDGAR company & filing discovery
│   │   ├── document_service.py  # 10-K document ingestion, parsing & passages
│   │   ├── claims_service.py    # Claim extraction (Phase 4)
│   │   ├── evidence_service.py  # Evidence & cross-reference engine (Phase 5)
│   │   ├── llm_service.py       # LLM evaluation interface (Phase 6+)
│   │   └── scoring_service.py   # ESG Integrity scoring (Phase 6+)
│   │
│   ├── models/
│   │   ├── __init__.py          # Domain model exports
│   │   ├── company.py           # Company model
│   │   ├── filing.py            # SECFiling models
│   │   ├── document.py          # Document, DocumentSection, RelevantPassage models
│   │   ├── claim.py             # Claim, ClaimType, ClaimCategoryGroup, SourceReference models
│   │   └── evidence.py          # Evidence, ClaimEvidenceResult, EvidenceSummary models (Phase 5)
│   │
│   └── utils/
│       ├── __init__.py          # Utility exports
│       ├── config.py            # Pydantic Settings application configuration
│       └── exceptions.py        # Domain exceptions (includes ClaimNotFoundError, EvidenceNotFoundError)
│
├── frontend/
│   └── README.md                # Frontend specifications & roadmap
│
├── scripts/
│   └── verify_live_sec.py       # Standalone live SEC verification CLI (Phases 1-5)
│
├── tests/
│   ├── __init__.py
│   ├── test_health.py           # Health check test
│   ├── test_sec_service.py      # SECService unit tests (mocked SEC responses)
│   ├── test_api_company.py      # Company & filing endpoint tests
│   ├── test_document_service.py # DocumentService parsing & extraction tests
│   ├── test_api_document.py     # Document inspection API tests
│   ├── test_sec_integration.py  # Live SEC integration tests (Apple Inc.)
│   ├── test_claims_service.py   # ClaimsService unit tests (mocked documents)
│   ├── test_api_claims.py       # Claims API endpoint tests
│   ├── test_evidence_service.py # EvidenceService unit tests (Phase 5)
│   └── test_api_evidence.py     # Evidence API endpoint tests (Phase 5)
│
├── data/
│   ├── raw/                     # Directory for unprocessed filings (git-ignored)
│   └── processed/               # Directory for structured parsed outputs (git-ignored)
│
├── .env.example                 # Environment variable templates
├── .gitignore                   # Git exclusion rules
├── pytest.ini                   # Pytest configuration and markers
├── README.md                    # Project documentation
└── requirements.txt             # Project dependencies
```

---

## 7. API Reference

All endpoints return JSON responses.

### 1. Health Check
- **Route**: `GET /health`
- **Response**: `200 OK`

### 2. Identify Company by Ticker
- **Route**: `GET /api/v1/companies/{ticker}`
- **Response**: `200 OK` (returns company name, CIK, exchange, SIC code)

### 3. Discover Company Annual Filings
- **Route**: `GET /api/v1/companies/{ticker}/filings`
- **Response**: `200 OK` (returns list of all `10-K` and `10-K/A` filings)

### 4. Get Latest Prevailing Annual Filing
- **Route**: `GET /api/v1/companies/{ticker}/filings/latest`
- **Response**: `200 OK` (returns latest annual filing metadata)

### 5. Retrieve Processed Document Metadata Summary
- **Route**: `GET /api/v1/companies/{ticker}/filings/latest/document`
- **Description**: Returns summary metadata without streaming enormous raw HTML payloads.
- **Example Request**:
  ```bash
  curl -X GET http://127.0.0.1:8000/api/v1/companies/AAPL/filings/latest/document
  ```
- **Response**: `200 OK`
```json
{
  "company": {
    "ticker": "AAPL",
    "company_name": "Apple Inc.",
    "cik": "0000320193",
    "exchange": "Nasdaq",
    "sic": "3571",
    "sic_description": "Electronic Computers"
  },
  "accession_number": "0000320193-25-000079",
  "form_type": "10-K",
  "filing_date": "2025-10-31",
  "report_date": "2025-09-27",
  "source_url": "https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm",
  "title": "aapl-20250927",
  "word_count": 36174,
  "character_count": 229142,
  "total_sections": 23,
  "detected_sections": [
    "Item 1. Business",
    "Item 1A. Risk Factors",
    "Item 1B. Unresolved Staff Comments",
    "Item 1C. Cybersecurity",
    "Item 7. Management's Discussion and Analysis",
    "Item 8. Financial Statements and Supplementary Data"
  ]
}
```

### 6. Get Document Sections
- **Route**: `GET /api/v1/companies/{ticker}/filings/latest/document/sections`
- **Query Parameter**: `section_type` (optional filter: `business`, `risk_factors`, `mda`, `financials`, `governance`)
- **Example Request**:
  ```bash
  curl -X GET "http://127.0.0.1:8000/api/v1/companies/AAPL/filings/latest/document/sections?section_type=business"
  ```
- **Response**: `200 OK`
```json
{
  "company": { "ticker": "AAPL", "company_name": "Apple Inc.", "cik": "0000320193" },
  "accession_number": "0000320193-25-000079",
  "source_url": "https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm",
  "total_sections": 1,
  "sections": [
    {
      "section_id": "item_1",
      "section_title": "Item 1. Business",
      "section_type": "business",
      "text": "Item 1. Business Company Background...",
      "start_position": 22567,
      "end_position": 38618,
      "word_count": 2380
    }
  ]
}
```

### 7. Extract Traceable ESG Passages
- **Route**: `GET /api/v1/companies/{ticker}/filings/latest/document/relevant-passages`
- **Query Parameters**:
  - `keywords`: Optional comma-separated list of keywords (e.g. `climate,carbon,renewable energy`). Defaults to standard ESG keywords.
  - `max_passages`: Maximum number of passages to return (1-200, default 50).
- **Example Request**:
  ```bash
  curl -X GET "http://127.0.0.1:8000/api/v1/companies/AAPL/filings/latest/document/relevant-passages?keywords=climate,emissions&max_passages=10"
  ```
- **Response**: `200 OK`
```json
{
  "company": { "ticker": "AAPL", "company_name": "Apple Inc.", "cik": "0000320193" },
  "accession_number": "0000320193-25-000079",
  "source_url": "https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm",
  "query_keywords": ["climate", "emissions"],
  "total_passages": 2,
  "passages": [
    {
      "passage_id": "0000320193-25-000079_item_1a_p2",
      "company_ticker": "AAPL",
      "accession_number": "0000320193-25-000079",
      "source_url": "https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm",
      "section_id": "item_1a",
      "section_title": "Item 1A. Risk Factors",
      "text": "Item 1A. Risk Factors The following summarizes factors that could have a material adverse effect on the Company's business...",
      "matched_keywords": ["climate"],
      "approximate_position": 124
    }
  ]
}
```

### 8. Extract Sustainability Claims
- **Route**: `GET /api/v1/companies/{ticker}/claims`
- **Query Parameters**:
  - `category`: Optional ESG category filter (e.g., `carbon_emissions`, `renewable_energy`, `inclusion`).
  - `claim_type`: Optional claim type filter (`target`, `achievement`, `current_state`, `policy`, `general`).
  - `limit`: Maximum number of claims to return (1–500, default 200).
- **Example Request**:
  ```bash
  curl -X GET "http://127.0.0.1:8000/api/v1/companies/AAPL/claims?claim_type=target&limit=10"
  ```
- **Response**: `200 OK`
```json
{
  "company": { "ticker": "AAPL", "company_name": "Apple Inc.", "cik": "0000320193" },
  "accession_number": "0000320193-25-000079",
  "filing_date": "2025-10-31",
  "report_date": "2025-09-27",
  "source_url": "https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm",
  "total_claims": 12,
  "extraction_method": "deterministic",
  "claims": [
    {
      "claim_id": "claim_aapl_0000320193_25_000079_e52cadff8979",
      "company_ticker": "AAPL",
      "company_name": "Apple Inc.",
      "claim_text": "The Company is an equal opportunity employer committed to inclusion...",
      "claim_type": "target",
      "category": "inclusion",
      "category_group": "social",
      "source_type": "sec_10k",
      "source_url": "https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm",
      "filing_accession_number": "0000320193-25-000079",
      "filing_date": "2025-10-31",
      "section_id": "item_1",
      "section_title": "Item 1. Business",
      "extraction_method": "deterministic",
      "confidence": "high",
      "status": "validated"
    }
  ]
}
```

> [!IMPORTANT]
> **The claims returned by this endpoint represent extracted text from SEC regulatory filings. They are not assessments of truthfulness, and this endpoint does NOT constitute greenwashing detection.** Phase 5 will introduce evidence cross-examination and objective classification.

### 9. Get Claims Summary Statistics
- **Route**: `GET /api/v1/companies/{ticker}/claims/summary`
- **Example Request**:
  ```bash
  curl -X GET "http://127.0.0.1:8000/api/v1/companies/AAPL/claims/summary"
  ```
- **Response**: `200 OK`
```json
{
  "company_ticker": "AAPL",
  "company_name": "Apple Inc.",
  "accession_number": "0000320193-25-000079",
  "total_claims": 12,
  "by_type": {
    "target": 6,
    "achievement": 5,
    "policy": 1
  },
  "by_category_group": {
    "environmental": 10,
    "social": 2,
    "governance": 0
  },
  "by_category": {
    "sustainability": 4,
    "inclusion": 2,
    "supply_chain": 1
  },
  "by_confidence": {
    "high": 9,
    "medium": 2,
    "low": 1
  },
  "extraction_method": "deterministic"
}
```

### 10. Get Individual Claim by ID
- **Route**: `GET /api/v1/companies/{ticker}/claims/{claim_id}`
- **Example Request**:
  ```bash
  curl -X GET "http://127.0.0.1:8000/api/v1/companies/AAPL/claims/claim_aapl_0000320193_25_000079_e52cadff8979"
  ```
- **Response**: `200 OK` (returns a single `Claim` object)
- **Error**: `404 Not Found` if the claim ID does not exist for that ticker.

### 11. Get Evidence Retrieval Summary (Phase 5)
- **Route**: `GET /api/v1/companies/{ticker}/evidence/summary`
- **Example Request**:
  ```bash
  curl -X GET "http://127.0.0.1:8000/api/v1/companies/AAPL/evidence/summary"
  ```
- **Response**: `200 OK` (returns `EvidenceSummaryResponse` with counts by relationship and strength)

### 12. Retrieve Evidence for a Specific Claim (Phase 5)
- **Route**: `GET /api/v1/companies/{ticker}/claims/{claim_id}/evidence`
- **Example Request**:
  ```bash
  curl -X GET "http://127.0.0.1:8000/api/v1/companies/AAPL/claims/claim_aapl_0000320193_25_000079_e52cadff8979/evidence"
  ```
- **Response**: `200 OK` (returns `ClaimEvidenceResult` pairing the claim with all retrieved evidence passages)

### 13. Retrieve Evidence for All Sustainability Claims (Phase 5)
- **Route**: `GET /api/v1/companies/{ticker}/evidence`
- **Query Parameters**:
  - `category` (optional): Filter by ESG category or pillar (`greenhouse_gas`, `environmental`, etc.)
  - `claim_type` (optional): Filter by claim type (`target`, `achievement`, `policy`, etc.)
  - `relationship` (optional): Filter by relationship (`supporting`, `contradictory`, `qualifying`, `contextual`, `insufficient_evidence`)
  - `minimum_relevance` (optional, float 0.0–1.0): Minimum relevance threshold
  - `limit` (optional, default 50): Maximum results to return
- **Example Request**:
  ```bash
  curl -X GET "http://127.0.0.1:8000/api/v1/companies/AAPL/evidence?category=environmental&relationship=supporting"
  ```
- **Response**: `200 OK` (returns `CompanyEvidenceResponse` with full per-claim results)

---

## 8. Installation & Setup

### 1. Create Virtual Environment
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables
Copy `.env.example` to `.env`:
```powershell
Copy-Item .env.example .env
```

### 4. Run Development Server
```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```
- API Docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- Alternative Redoc: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

---

## 9. Testing & Verification

### Unit Testing (Mocked, Offline & Deterministic)
All core service and API tests use mocked SEC responses to guarantee determinism without making external requests:

```bash
pytest -v
```

Expected: **88 tests passing** (Phases 1–5)

### Live SEC Integration Testing
To verify end-to-end connectivity with the real SEC EDGAR infrastructure using Apple Inc. (`AAPL`):

```bash
pytest -m integration -v
```

### Standalone Manual Verification Script
Run the included verification CLI against Apple or any public ticker to exercise the full Phases 1–5 pipeline end-to-end:

```bash
python scripts/verify_live_sec.py AAPL
python scripts/verify_live_sec.py MSFT
```

---

## 10. Known Limitations

- **Filing Size**: SEC 10-K filings can be 2 to 20+ megabytes of raw HTML. To prevent network and browser strain, API endpoints return metadata summaries, targeted sections, and bounded passage lists rather than enormous raw HTML strings.
- **HTML Diversity**: Companies submit 10-K filings formatted using different HTML generators, CSS architectures, and inline XBRL (iXBRL). The section detection engine uses tolerant regex heuristics with Table-of-Contents disambiguation, but atypical non-standard headings will default to the full document section.
- **In-Memory Storage**: Document, claim, and evidence caching is stored in memory. Downloaded filings are not persisted to a database or committed to Git.
- **Deterministic Extraction Precision**: Phases 4 and 5 use deterministic regex and keyword algorithms without an LLM. Some nuanced passages may receive contextual or qualifying classifications rather than deeper semantic assessment.
- **10-K Scope**: The system currently cross-references claims only against SEC 10-K / 10-K/A filings. Standalone sustainability reports, CSR websites, and proxy statements are not yet ingested.
- **No Greenwashing Verdicts**: Phase 5 produces neutral, retrieval-based evidence relationships (`supporting`, `contradictory`, `qualifying`, `contextual`, `insufficient_evidence`). Full LLM reasoning, ESG scoring, and dashboard visualisations belong to Phase 6 and beyond.

