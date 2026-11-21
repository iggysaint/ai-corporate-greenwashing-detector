# ESG Integrity Score Methodology

**Methodology Version:** `1.0.0`  
**Audience:** Business analysts, sustainability researchers, investors, regulators, and corporate disclosure reviewers (no programming background required)

---

## 1. What the ESG Integrity Score Measures

The **ESG Integrity Score** (0 to 100) measures **the credibility and evidence substantiation of a company's disclosed sustainability and ESG claims based on the disclosure evidence retrieved by the platform**.

Specifically, it evaluates:
- Whether concrete evidence in the company's own regulatory filings or annual/sustainability reports corroborates, qualifies, contradicts, or fails to substantiate each extracted claim.
- Whether high-materiality, quantified, and sector-relevant disclosures are backed by stronger evidence than generic aspirational statements.
- How much of the company's sustainability reporting has verifiable supporting context (`evidence_coverage`) versus unverified claims (`substantiation_rate`).

A **higher score** means that the company's assessable ESG claims in the analysed document(s) are consistently backed by aligned disclosure evidence rather than contradicted or left unsubstantiated.

---

## 2. What the ESG Integrity Score Does NOT Measure

Every API response carries an explicit scope disclaimer. The ESG Integrity Score **must never** be interpreted as:

1. **A complete ESG performance rating.** A company with a small carbon footprint that makes poorly documented claims can score lower than a high-emitting company whose disclosures are candid and backed by verifiable data.
2. **A measure of total environmental or social impact.** It evaluates *disclosure integrity*, not physical emissions, labour outcomes, or ecological footprint on the ground.
3. **Proof that a company is or is not greenwashing.** "Greenwashing" is a legal and regulatory determination involving intent and external facts. An `unsubstantiated` finding means retrieved disclosures did not establish the claim—it does **not** prove the claim is false. Conversely, a high score only reflects consistency within available disclosures.
4. **A substitute for independent third-party ESG audits or assurance.**
5. **A scientifically validated or externally audited index.** The weighting and banding parameters in Version `1.0.0` are transparent analytical defaults, not empirically calibrated statistical coefficients.
6. **Financial or investment advice.**

---

## 3. Scoring Formula Overview

The engine calculates scores deterministically in four stages, moving from individual claims up to ESG pillars and then to the overall score. **No Large Language Model (LLM) invents, chooses, or adjusts any number.** Identical evaluation inputs and methodology settings always produce the exact same scores.

### High-Level Pipeline

1. **Deduplicate & Filter:** Remove duplicate evaluations sharing the same `claim_id` (`duplicate_evaluations_ignored`) so no claim is double-counted. Claims not mapped to Environmental, Social, or Governance (`other` / `unmapped_claims`) are reported but excluded from pillar and overall scores.
2. **Score Each Claim ($C_i$):** Map each assessable claim's evaluation outcome to a **non-overlapping score band**, then apply a bounded **evidence quality adjustment** inside that band.
3. **Weight Each Claim ($W_i$):** Multiply the claim's **type weight** by optional **quantification** and **sector-priority** multipliers.
4. **Aggregate Into E, S, and G Pillars ($\text{Score}_p$):** Within each pillar, cap low-materiality boilerplate claims using **volume damping**, then take the weighted average of assessable claim scores:
   $$\text{Score}_p = \text{round}\!\left(\frac{\sum_{i \in p} w^{\text{eff}}_i \cdot C_i}{\sum_{i \in p} w^{\text{eff}}_i}\right)$$
5. **Aggregate Into Overall ESG Integrity Score ($\text{Score}$):** Combine scored pillars using configurable **pillar base weights** scaled by **thin-pillar sufficiency** and normalized across scored pillars:
   $$W^{\text{pillar}}_p = B_p \times \min\!\left(1.0,\; \frac{N_p}{N_{\min}}\right), \qquad \text{Score} = \text{round}\!\left(\frac{\sum_{p \in \text{scored}} W^{\text{pillar}}_p \cdot \text{RawScore}_p}{\sum_{p \in \text{scored}} W^{\text{pillar}}_p}\right)$$
   If fewer than $N_{\min} = 3$ assessable claims exist overall, no numerical score is computed (`score_status = "insufficient_data"`, `esg_integrity_score = null`).

---

## 4. Claim-Level Scoring (Non-Overlapping Bands)

Before calculating averages, each claim is placed into a **non-overlapping band** determined by its Phase 6 assessment outcome (`supported`, `partially_supported`, `unsubstantiated`, `inconsistent`, or `insufficient_evidence`):

| Evaluation Category | Base Score | Permitted Band (Min – Max) | Analytical Meaning |
| :--- | :---: | :---: | :--- |
| **`supported`** | **90** | **80 – 100** | Retrieved disclosure evidence directly substantiates the claim. |
| **`partially_supported`** | **60** | **50 – 70** | Evidence supports part of the claim, but introduces material caveats, scope restrictions, or incomplete progress. |
| **`unsubstantiated`** | **25** | **15 – 35** | Relevant disclosure context exists, but does not substantiate the assertion. Receives partial credit because lack of documentation is **not** proof of falsity. |
| **`inconsistent`** | **0** | **0 – 0** (fixed) | Disclosed facts, timelines, or metrics directly contradict the claim. Fixed at `0` so high confidence in a contradiction does not award points. |
| **`insufficient_evidence`** | *Excluded* | *N/A* | No relevant evidence was retrieved. Excluded from both numerator and denominator so missing records are **never** punished as contradictions. Reduces **Evidence Coverage** instead. |

### Why Non-Overlapping Bands?
Because `[80–100]`, `[50–70]`, `[15–35]`, and `[0]` are separated by at least 10 points, secondary evidence-quality adjustments can reward thorough citations or penalise caveats **without ever letting an unsubstantiated claim score higher than a partially supported claim, or a partially supported claim score higher than a supported claim**.

---

## 5. Evidence Quality Adjustments

For claims in the `supported`, `partially_supported`, and `unsubstantiated` bands, a bounded additive adjustment (within $[-10, +10]$ points, then clamped to the category's `[min, max]` band) refines the base score based on evidence quality:

| Signal | Point Adjustment | Rationale |
| :--- | :---: | :--- |
| **Evaluation confidence is High** | `+3` | Strong, unambiguous match between claim and cited passage(s). |
| **Evaluation confidence is Low** | `-3` | Weak or borderline match. |
| **Mean relevance of cited evidence $\ge 0.40$** | `+3` | Cited evidence directly addresses the same concepts, metrics, and timeframe. |
| **Mean relevance of cited evidence $< 0.20$** | `-3` | Weak topical overlap between claim and cited passage(s). |
| **No validated evidence citation** | `-3` | Assessment lacked a traceable filing citation. |
| **Caveats / scope limits identified** | `-2` per caveat (max `-6`) | Reflects material operational exclusions or conditional language noted by the evaluator. |

### Role of Independent Assurance
Where regulatory filings document independent third-party assurance or audit verification as part of the cited evidence, relevance and evaluation confidence increase—allowing supported claims to reach up to `96–100`. However, because voluntary external assurance varies widely by company size and jurisdiction, **the absence of independent assurance is never treated as proof that a claim is false or unsubstantiated**.

---

## 6. Claim Materiality Weighting & Volume Damping

Not all statements carry equal weight. A quantified achievement reducing carbon emissions is far more material than a generic boilerplate pledge. Each claim's raw materiality weight is:

$$W_i = W_{\text{type}}(i) \times M_{\text{quant}}(i) \times M_{\text{sector}}(i)$$

### A. Base Weight by Claim Type ($W_{\text{type}}$)

| Claim Type | Base Weight | Rationale |
| :--- | :---: | :--- |
| **`achievement`** | `1.5` | Reports concrete completed outcomes or historical results—highest verification importance. |
| **`target`** | `1.3` | States measurable forward-looking commitments—high accountability importance. |
| **`current_state`** | `1.2` | Reports current operational metrics or baselines. |
| **`policy`** | `0.9` | Documents governance standards, codes of conduct, or formal policies. |
| **`general`** (or unknown) | `0.6` | High-level aspirational or introductory statements—lowest weight. |

### B. Quantitative Specificity Multiplier ($M_{\text{quant}} = 1.2\times$)
A `1.2x` multiplier applies when the claim includes concrete numerical specificity:
- Percentages (e.g., `15.8%`, `100%`)
- Currency figures (e.g., `$50 million`, `GH₵ 12 million`)
- Numbers paired with physical or workforce units (e.g., `tonnes`, `tCO2e`, `MWh`, `kWh`, `litres`, `hectares`, `employees`, `directors`, `beneficiaries`)
- Explicit deadline years (`by 2030`, `before 2028`, `until 2035`, `through 2030`)

*Design Safeguard:* Bare 4-digit calendar years (such as `"2024 Annual Report"`) are intentionally ignored so document headers do not falsely flag vague prose as quantified.

### C. Sector Priority Multiplier ($M_{\text{sector}} = 1.3\times$)
A `1.3x` multiplier applies when the claim's ESG category or terminology matches the high-materiality themes for the company's sector (detailed in Section 11).

### D. Volume Damping Against "Claim Stuffing"
To ensure a company cannot dilute a small number of unverified or contradicted material claims by publishing dozens of trivial boilerplate statements:
- Any assessable claim with $W_i < 1.0$ (`SCORE_LOW_MATERIALITY_THRESHOLD`) is classified as **low materiality** (for example, unquantified `general` or `policy` statements outside sector priority themes).
- Whenever at least one high-materiality claim ($W_i \ge 1.0$) exists in the same pillar, the **combined effective weight of all low-materiality claims is capped at 25% of that pillar's total weight** (`SCORE_LOW_MATERIALITY_MAX_SHARE = 0.25`):
  $$\text{cap} = W_{\text{high\_sum}} \times \frac{0.25}{1 - 0.25} = \frac{W_{\text{high\_sum}}}{3}$$
- Adding more low-materiality boilerplate statements beyond that cap scales each boilerplate item down proportionally, leaving the pillar score unchanged.

---

## 7. ESG Dimensional (E / S / G) Scoring & Pillar Aggregation

Claims mapped to `environmental`, `social`, and `governance` are scored separately to avoid masking weak governance or social gaps behind strong environmental claims (or vice versa):

| ESG Pillar | Default Base Weight | Rationale |
| :--- | :---: | :--- |
| **Environmental (E)** | **0.40** (40%) | Slightly higher default reflects the prevalence and measurability of physical emissions, energy, water, waste, and climate claims in corporate greenwashing risk. |
| **Social (S)** | **0.35** (35%) | Covers workforce safety, diversity and inclusion, human rights, labour practices, supply chain, and community investment. |
| **Governance (G)** | **0.25** (25%) | Covers board oversight, ethics, compliance, anti-corruption, and transparency controls that underpin both E and S disclosures. |

*All weights are configurable (`SCORE_WEIGHT_ENVIRONMENTAL`, `SCORE_WEIGHT_SOCIAL`, `SCORE_WEIGHT_GOVERNANCE`).*

### Missing Dimension & Thin-Pillar Sufficiency Rule
- **Unscored Dimension:** If a pillar has **zero assessable claims** (either no claims were extracted for it, or all had `insufficient_evidence`), its score is returned as **`null`** (`score_status = "insufficient_data"`), **never `0`**. Its weight is excluded and remaining scored pillars are normalized to sum to `1.0`.
- **Thin-Pillar Sufficiency Scaling:** A pillar with only 1 or 2 assessable claims should not have the full influence of a deeply evidenced pillar:
  $$W^{\text{pillar}}_p = \text{BaseWeight}_p \times \min\!\left(1.0,\; \frac{\text{AssessableClaims}_p}{3}\right)$$
  For example, if Governance has only 1 assessable claim while Environmental has 3+, Governance enters the normalized average at $1/3$ of its base weight ($0.25 \times \frac{1}{3} \approx 0.083$).

---

## 8. Worked Numerical Example

Suppose an energy/telecommunications company has 4 assessable claims in its annual report:

1. **Claim E1 (Environmental, `achievement`, quantified, sector match, `supported`, high conf, rel 0.45):**
   - Band score: `90 + 3 (conf) + 3 (rel) = 96`
   - Materiality weight: $1.5 \times 1.2 \times 1.3 = 2.34$
2. **Claim E2 (Environmental, `target`, unquantified, sector match, `partially_supported`, medium conf, rel 0.35, 1 caveat):**
   - Band score: `60 - 2 (caveat) = 58`
   - Materiality weight: $1.3 \times 1.0 \times 1.3 = 1.69$
3. **Claim E3 (Environmental, `general`, unquantified, non-sector, `supported`, high conf, rel 0.45):**
   - Band score: `96`, Materiality weight: `0.60` (low materiality $< 1.0$; under `25%` cap since $\text{cap} = (2.34 + 1.69)/3 = 1.34 > 0.60$, effective weight remains `0.60`)
4. **Claim S1 (Social, `achievement`, unquantified, non-sector, `unsubstantiated`, medium conf, no citation):**
   - Band score: `25 - 3 = 22`, Materiality weight: `1.5`

- **Environmental Pillar Raw Score:**
  $$\frac{2.34(96) + 1.69(58) + 0.60(96)}{2.34 + 1.69 + 0.60} = \frac{224.64 + 98.02 + 57.60}{4.63} = 82.13 \longrightarrow \mathbf{82}$$
- **Social Pillar Raw Score:** `22` (only 1 assessable claim $\to$ thin-pillar sufficiency $= 1/3$).
- **Governance Pillar:** No claims $\to$ `null` (`insufficient_data`).
- **Pillar Aggregation Weights:**
  - Environmental: $0.40 \times \min(1, 3/3) = 0.40$ (effective weight: $0.774$)
  - Social: $0.35 \times \min(1, 1/3) = 0.1167$ (effective weight: $0.226$)
- **Overall ESG Integrity Score:**
  $$\frac{0.40(82.13) + 0.1167(22.0)}{0.40 + 0.1167} = \frac{35.42}{0.5167} = 68.55 \longrightarrow \mathbf{69}$$

---

## 9. Treatment of Missing Information

- **Minimum Assessable Claims Threshold ($N_{\min} = 3$):** At least 3 E/S/G-mapped assessable claims (not `insufficient_evidence`) are required before generating an overall score. Otherwise, `esg_integrity_score = null` and `score_status = "insufficient_data"`.
- **Single-Dimension Gaps:** Missing information in one or two pillars does not assign `0` to those pillars; they remain `null` and are listed in `main_concerns` as data gaps.
- **No Fabricated History:** The `/score/history` endpoints only return assessments actually computed during the active server session in memory, keyed by `(source_document, methodology_version)`. If no evaluation has been run, `total_records = 0` is returned.

---

## 10. Evidence Coverage, Substantiation Rate, and Confidence

Analysts should always read the **ESG Integrity Score** alongside three companion reliability indicators:

| Metric | Formula & Definition | What It Tells You |
| :--- | :--- | :--- |
| **`evidence_coverage`** | $\frac{\text{Assessed} - \text{Insufficient Evidence}}{\text{Assessed}} \times 100\%$ | **Data availability.** Did the filing contain relevant evidence passages for the company's claims? High coverage does **not** mean claims were corroborated—only that evidence was found (even if unsubstantiated or contradictory). |
| **`substantiation_rate`** | $\frac{\text{Supported} + \text{Partially Supported}}{\text{Assessable Mapped Claims}} \times 100\%$ | **Corroboration ratio.** What share of assessable claims were directly or partially backed by disclosures? `null` if no assessable claims exist. |
| **`confidence`** | Categorical: `high`, `medium`, `low`, `insufficient` | **Sample & method reliability.** See thresholds below. |

### Confidence Thresholds

| Overall Confidence | Required Conditions |
| :--- | :--- |
| **`high`** | $\ge 10$ assessable E/S/G claims, **and** `evidence_coverage >= 70%`, **and** at least 2 pillars scored, **and** evaluations are LLM-assisted (not all rule-based). |
| **`medium`** | $\ge 5$ assessable E/S/G claims and `evidence_coverage >= 50%` (or meets `high` thresholds while using rule-based fallback). |
| **`low`** | $3$–$4$ assessable E/S/G claims, **or** `evidence_coverage < 50%`. |
| **`insufficient`** | Fewer than $3$ assessable E/S/G claims (score is `null`). |

*Rule-Based Cap:* When no LLM API key is configured (`OPENAI_API_KEY` unset) and every claim is assessed by deterministic keyword/relationship heuristics rather than full reading comprehension, confidence is **capped at `medium`** (`SCORE_CAP_CONFIDENCE_FOR_RULE_BASED = True`).

---

## 11. Ghana (GSE) and Sector-Specific Considerations

The scoring engine applies **identical base scores, quality bands, pillar weights, and thresholds to US SEC and Ghana Stock Exchange (GSE) companies**. Market origin never raises or lowers a score. Sector materiality adjustments depend solely on the company's industry/sector classification (`sector` / `industry` for GSE; `sic_description` for SEC):

| Sector Profile | Trigger Keywords (Sector / SIC) | High-Materiality Categories & Sector Themes ($1.3\times$) |
| :--- | :--- | :--- |
| **`mining`** | mining, mines, gold, minerals, metal ores | Water, pollution, waste, biodiversity, environmental management, health & safety, community, human rights, *galamsey*, illegal/artisanal mining, mineral rights, tailings, land rehabilitation, reclamation, cyanide |
| **`oil_and_gas`** | oil, gas, petroleum, crude, refining | Emissions, GHG, carbon, climate, pollution, environmental management, health & safety, community, oil spill, gas flaring, offshore drilling, petroleum |
| **`agriculture`** | agriculture, cocoa, plantations, palm, farming | Biodiversity, water, supply chain, labour, human rights, community, cocoa, palm oil, deforestation, smallholder, fair trade |
| **`banking`** | banking, financial, insurance, microfinance, savings | Governance, ethics, compliance, risk management, transparency, business conduct, inclusion, financial inclusion, mobile money, microfinance, anti-money laundering, data protection |
| **`telecommunications`** | telecom, mobile, wireless | Energy, renewable energy, carbon, emissions, GHG, waste, inclusion, digital inclusion, e-waste, tower emissions, financial inclusion, mobile money, data privacy |
| **`technology`** | computers, electronics, software, semiconductors, technology | Energy, renewable energy, carbon, emissions, GHG, supply chain, recycling, waste, human rights, e-waste, conflict minerals, data privacy |
| **`manufacturing`** | manufacturing, industrial, cement, steel, chemicals | Emissions, energy, waste, pollution, water, health & safety, labour, industrial waste, effluent, occupational safety |
| **`consumer_goods`** | consumer, beverages, breweries, food, household, distribution | Waste, recycling, water, supply chain, circular economy, packaging, plastics |

- **No Cross-Sector Contamination:** Mining-specific criteria (such as *galamsey*, tailings, or land rehabilitation) are never applied to banks or telecommunications companies unless the company itself operates in extractives.
- **Unmatched Sectors:** Companies whose sector does not match a specialized profile receive no sector multiplier ($1.0\times$ across all claims).

---

## 12. Rounding, Determinism, and Traceability

- **Whole-Number Rounding:** Overall scores, pillar scores, `evidence_coverage`, and `substantiation_rate` are rounded to whole numbers (`0–100`) to avoid false precision (e.g., presenting `49` rather than `48.73`).
- **Deterministic Repeatability:** Running the same claim evaluations through the same methodology version always produces the same numbers down to individual claim weights.
- **Full Audit Trail:** The `/score/breakdown` endpoints preserve every `claim_id`, `evaluation_id`, cited `evidence_id`, quality adjustment reason, materiality multiplier, effective weight, and `source_document_references`.

---

## 13. Known Limitations

1. **Single-Filing / Document Scope:** Currently scores claims evaluated within the analysed SEC Form 10-K/10-K/A or ingested GSE annual/sustainability report. External news, satellite monitoring, or third-party databases are out of scope in Phase 8.
2. **Rule-Based Evaluation Fallback:** When `OPENAI_API_KEY` is unavailable, upstream Phase 6 evaluations use deterministic keyword heuristics rather than semantic comprehension. Subtle nuances in long PDF sustainability tables may be marked `unsubstantiated`.
3. **In-Memory History:** No database persistence is implemented in Phase 8; score history clears on server restart.
4. **No External Validation:** Methodology `1.0.0` defaults have not been statistically calibrated or independently audited against external ESG controversy datasets.

---

## 14. Methodology Versioning

Methodology changes follow **Semantic Versioning** (`MAJOR.MINOR.PATCH`):
- **`MAJOR`** (e.g. `2.0.0`): Breaking changes to band definitions, score scale, or pillar formula.
- **`MINOR`** (e.g. `1.1.0`): Additions of new sector profiles or backward-compatible breakdown fields.
- **`PATCH`** (e.g. `1.0.1`): Bug fixes, wording refinements, or non-material edge-case fixes.

History entries store `(document_identifier, methodology_version)`, ensuring scores from different methodology versions are distinguishable.
