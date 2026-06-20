# Stage 3 Evaluation Report

This report evaluates the performance of the Stage 3 deterministic resolver on the 20 labeled cases from `sample_claims.csv` against the gold standard labels.

## Scorecard (Accuracy & Set Metrics)

| Metric | Overall | Car | Laptop | Package |
| :--- | :--- | :--- | :--- | :--- |
| Claim Status Accuracy | 75.00% | 87.50% | 100.00% | 33.33% |
| Issue Type Accuracy | 15.00% | 12.50% | 16.67% | 16.67% |
| Object Part Accuracy | 65.00% | 100.00% | 66.67% | 16.67% |
| Severity Accuracy | 35.00% | 25.00% | 50.00% | 33.33% |
| Valid Image Accuracy | 90.00% | 100.00% | 100.00% | 66.67% |
| Evidence Standard Met Accuracy | 80.00% | 75.00% | 100.00% | 66.67% |
| Risk Flags Precision | 75.83% | 75.00% | 75.00% | 77.78% |
| Risk Flags Recall | 74.17% | 72.92% | 88.89% | 61.11% |
| Risk Flags F1 | 66.33% | 71.67% | 73.33% | 52.22% |
| Supporting Image Precision | 90.00% | 87.50% | 100.00% | 83.33% |
| Supporting Image Recall | 82.50% | 75.00% | 100.00% | 75.00% |

## Confusion Matrix (claim_status)

| Gold \ Pred | Supported | Contradicted | NEI |
| :--- | :--- | :--- | :--- |
| **Supported** | 11 | 0 | 2 |
| **Contradicted** | 2 | 3 | 0 |
| **NEI** | 0 | 1 | 1 |

## Disagreement Table

| Case ID | Field | Predicted | Gold | Signal / Root Cause |
| :--- | :--- | :--- | :--- | :--- |
| case_001 | `issue_type` | `broken_part` | `dent` | Claimed:['rear_bumper'] (issue:dent) | Images: img_1[focal:rear_bumper, add:['taillight', 'side_mirror', 'body'], issue:broken_part, non_orig:False] |
|  | `severity` | `high` | `medium` |  |
| case_002 | `issue_type` | `dent` | `scratch` | Claimed:['front_bumper'] (issue:scratch) | Images: img_1[focal:front_bumper, add:['headlight', 'windshield'], issue:dent, non_orig:False], img_2[focal:front_bumper, add:['side_mirror', 'headlight', 'taillight', 'windshield', 'hood', 'body'], issue:none, non_orig:False] |
|  | `severity` | `medium` | `low` |  |
| case_003 | `issue_type` | `glass_shatter` | `crack` | Claimed:['windshield'] (issue:crack) | Images: img_1[focal:windshield, add:['front_bumper', 'hood'], issue:glass_shatter, non_orig:False], img_2[focal:windshield, add:['front_bumper'], issue:none, non_orig:False] |
|  | `severity` | `high` | `medium` |  |
| case_004 | `issue_type` | `glass_shatter` | `broken_part` | Claimed:['side_mirror'] (issue:broken_part) | Images: img_1[focal:side_mirror, add:[], issue:glass_shatter, non_orig:False] |
|  | `severity` | `high` | `medium` |  |
| case_005 | `issue_type` | `none` | `scratch` | Claimed:['rear_bumper'] (issue:dent) | Images: img_1[focal:front_bumper, add:['side_mirror', 'door'], issue:dent, non_orig:False], img_2[focal:rear_bumper, add:['body', 'side_mirror', 'taillight', 'fender'], issue:none, non_orig:False] |
|  | `severity` | `none` | `low` |  |
|  | `risk_flags` | `damage_not_visible;user_history_risk` | `claim_mismatch;user_history_risk;manual_review_required` |  |
|  | `supporting_image_ids` | `img_2` | `img_1` |  |
| case_006 | `risk_flags` | `wrong_object_part` | `wrong_angle;damage_not_visible` | Claimed:['headlight'] (issue:crack) | Images: img_1[focal:side_mirror, add:['body', 'front_bumper', 'rear_bumper', 'door', 'windshield', 'headlight', 'taillight', 'fender', 'quarter_panel'], issue:none, non_orig:False] |
| case_007 | `claim_status` | `not_enough_information` | `supported` | Claimed:['door'] (issue:dent) | Images: img_1[focal:body, add:[], issue:unknown, non_orig:False], img_2[focal:body, add:['rear_bumper', 'side_mirror', 'door', 'fender', 'quarter_panel', 'front_bumper', 'hood', 'windshield', 'headlight', 'taillight'], issue:dent, non_orig:False] |
|  | `issue_type` | `unknown` | `dent` |  |
|  | `severity` | `unknown` | `medium` |  |
|  | `evidence_standard_met` | `false` | `true` |  |
|  | `risk_flags` | `blurry_image;wrong_object_part` | `blurry_image` |  |
|  | `supporting_image_ids` | `none` | `img_2` |  |
| case_008 | `issue_type` | `crushed_packaging` | `broken_part` | Claimed:['hood'] (issue:scratch) | Images: img_1[focal:front_bumper, add:['hood', 'side_mirror', 'body', 'rear_bumper'], issue:crushed_packaging, non_orig:True] |
|  | `evidence_standard_met` | `false` | `true` |  |
|  | `risk_flags` | `non_original_image;user_history_risk` | `claim_mismatch;non_original_image;user_history_risk;manual_review_required` |  |
| case_009 | `issue_type` | `glass_shatter` | `crack` | Claimed:['screen'] (issue:crack) | Images: img_1[focal:screen, add:['keyboard', 'trackpad', 'body'], issue:glass_shatter, non_orig:False] |
|  | `severity` | `high` | `medium` |  |
| case_010 | `issue_type` | `crack` | `broken_part` | Claimed:['hinge', 'screen'] (issue:broken_part) | Images: img_1[focal:screen, add:['keyboard'], issue:crack, non_orig:False], img_2[focal:screen, add:['keyboard', 'base'], issue:none, non_orig:False] |
|  | `object_part` | `screen` | `hinge` |  |
| case_011 | `issue_type` | `water_damage` | `stain` | Claimed:['keyboard'] (issue:stain) | Images: img_1[focal:keyboard, add:[], issue:water_damage, non_orig:False] |
| case_012 | `issue_type` | `scratch` | `dent` | Claimed:['corner'] (issue:dent) | Images: img_1[focal:lid, add:[], issue:none, non_orig:False], img_2[focal:lid, add:[], issue:scratch, non_orig:False] |
|  | `risk_flags` | `low_light_or_glare` | `none` |  |
| case_013 | `severity` | `high` | `medium` | Claimed:['screen'] (issue:glass_shatter) | Images: img_1[focal:screen, add:['keyboard'], issue:crack, non_orig:False] |
| case_014 | `issue_type` | `scratch` | `none` | Claimed:['trackpad', 'body'] (issue:broken_part) | Images: img_1[focal:base, add:['keyboard', 'screen'], issue:scratch, non_orig:False] |
|  | `object_part` | `body` | `trackpad` |  |
|  | `severity` | `low` | `none` |  |
|  | `risk_flags` | `claim_mismatch;user_history_risk` | `damage_not_visible;user_history_risk;manual_review_required` |  |
| case_016 | `issue_type` | `crushed_packaging` | `torn_packaging` | Claimed:['seal', 'box', 'package_side'] (issue:torn_packaging) | Images: img_1[focal:box, add:[], issue:crushed_packaging, non_orig:False], img_2[focal:box, add:[], issue:none, non_orig:False] |
|  | `object_part` | `box` | `seal` |  |
|  | `risk_flags` | `text_instruction_present` | `none` |  |
| case_017 | `claim_status` | `not_enough_information` | `supported` | Claimed:['box'] (issue:water_damage) | Images: img_1[focal:box, add:[], issue:unknown, non_orig:False] |
|  | `issue_type` | `unknown` | `water_damage` |  |
|  | `object_part` | `box` | `package_side` |  |
|  | `severity` | `unknown` | `medium` |  |
|  | `valid_image` | `false` | `true` |  |
|  | `evidence_standard_met` | `false` | `true` |  |
|  | `risk_flags` | `user_history_risk` | `user_history_risk;manual_review_required` |  |
|  | `supporting_image_ids` | `none` | `img_1` |  |
| case_018 | `claim_status` | `contradicted` | `not_enough_information` | Claimed:['item', 'box'] (issue:missing_part) | Images: img_1[focal:unknown, add:[], issue:unknown, non_orig:False], img_2[focal:box, add:['label', 'seal'], issue:none, non_orig:False] |
|  | `issue_type` | `none` | `unknown` |  |
|  | `object_part` | `box` | `contents` |  |
|  | `severity` | `none` | `unknown` |  |
|  | `valid_image` | `true` | `false` |  |
|  | `evidence_standard_met` | `true` | `false` |  |
|  | `risk_flags` | `blurry_image;damage_not_visible;manual_review_required` | `cropped_or_obstructed;damage_not_visible;manual_review_required` |  |
|  | `supporting_image_ids` | `img_2` | `none` |  |
| case_019 | `claim_status` | `supported` | `contradicted` | Claimed:['box'] (issue:crushed_packaging) | Images: img_1[focal:box, add:[], issue:crushed_packaging, non_orig:False] |
|  | `issue_type` | `crushed_packaging` | `unknown` |  |
|  | `object_part` | `box` | `unknown` |  |
|  | `severity` | `medium` | `low` |  |
|  | `risk_flags` | `user_history_risk` | `wrong_object;claim_mismatch;user_history_risk;manual_review_required` |  |
| case_020 | `claim_status` | `supported` | `contradicted` | Claimed:['box', 'seal'] (issue:torn_packaging) | Images: img_1[focal:box, add:['label', 'seal'], issue:crushed_packaging, non_orig:False], img_2[focal:box, add:[], issue:none, non_orig:False] |
|  | `issue_type` | `crushed_packaging` | `none` |  |
|  | `object_part` | `box` | `seal` |  |
|  | `severity` | `medium` | `none` |  |
|  | `risk_flags` | `user_history_risk` | `damage_not_visible;text_instruction_present;user_history_risk;manual_review_required` |  |
|  | `supporting_image_ids` | `img_1` | `img_1;img_2` |  |

## Open Diagnostics

### 1. additional_parts Spam Frequency
**Total occurrences:** 4

List of cases where a claimed part appeared ONLY in `additional_parts_seen` (not `object_part_seen`):
- **case_006**: claimed `headlight`, focal seen: `['side_mirror']`, add seen: `[['body', 'front_bumper', 'rear_bumper', 'door', 'windshield', 'headlight', 'taillight', 'fender', 'quarter_panel']]`
- **case_007**: claimed `door`, focal seen: `['body', 'body']`, add seen: `[[], ['rear_bumper', 'side_mirror', 'door', 'fender', 'quarter_panel', 'front_bumper', 'hood', 'windshield', 'headlight', 'taillight']]`
- **case_008**: claimed `hood`, focal seen: `['front_bumper']`, add seen: `[['hood', 'side_mirror', 'body', 'rear_bumper']]`
- **case_020**: claimed `seal`, focal seen: `['box', 'box']`, add seen: `[['label', 'seal'], []]`

### 2. Short-Circuit Field-Filling
**Total short-circuit rows:** 1

| Case ID | Short-Circuit Reason | Pred Part | Gold Part | Pred Issue | Gold Issue |
| :--- | :--- | :--- | :--- | :--- | :--- |
| case_008 | `non_original` | `front_bumper` | `front_bumper` | `crushed_packaging` | `broken_part` |

## Operational Analysis

### 1. Call Volumes and Image Processing
* **Total unique images processed:** 111 images (29 sample + 82 test).
* **Total VLM (Stage 1) calls:** ~111 blind global passes, plus conditional directed detail passes (triggered on blind confidence `< high`, estimating ~120-130 total vision calls).
* **Total LLM extraction (Stage 2) calls:** 64 calls (20 sample claims + 44 test claims).
* **Total API calls for full run:** ~180-195 calls.

### 2. Token Consumption Estimates
* **Stage 1 (Vision):**
  * Input tokens per call: ~1,500 (VLM prompt + image resolution scaling).
  * Output tokens per call: ~200 (JSON structured findings).
  * Total Vision volume: ~180,000 input tokens, ~24,000 output tokens.
* **Stage 2 (Claim Extraction):**
  * Input tokens per call: ~800 (Transcript transcript conversation + system instructions).
  * Output tokens per call: ~100 (JSON claim record).
  * Total Extraction volume: ~51,200 input tokens, ~6,400 output tokens.
* **Total Token Volume:** ~231,200 input tokens and ~30,400 output tokens.

### 3. Cost Projection (Stated Claude Pricing)
Stated pricing for **Claude 3.5 Sonnet** ($3.00/M input, $15.00/M output) vs. **Claude 3 Opus** ($15.00/M input, $75.00/M output):
* **Claude 3.5 Sonnet Cost:**
  * Vision Input: $3.00 * 0.180M = $0.54
  * Vision Output: $15.00 * 0.024M = $0.36
  * Extraction Input: $3.00 * 0.051M = $0.153
  * Extraction Output: $15.00 * 0.006M = $0.09
  * **Total Estimated Test Set Cost (Sonnet):** **$1.14**
* **Claude 3 Opus Cost:**
  * Vision Input: $15.00 * 0.180M = $2.70
  * Vision Output: $75.00 * 0.024M = $1.80
  * Extraction Input: $15.00 * 0.051M = $0.765
  * Extraction Output: $75.00 * 0.006M = $0.45
  * **Total Estimated Test Set Cost (Opus):** **$5.72**

### 4. Latency and Runtime
* **Cold Runtime (no cache):** ~2-3 minutes depending on OpenRouter/VLM network latency and rate limits.
* **Warm Runtime (full cache hits):** **~1.2 seconds** for all 44 rows.
* **Average latency per uncached API request:** ~2.5 seconds.

### 5. TPM/RPM, Throttling, Caching, and Retries
* **Caching Strategy:** We implement local JSON caching under `code/stage1/.cache/` and `code/stage2/.cache/` keyed on SHA-256 hashes of the exact inputs (image bytes, model, prompts, and schema). This guarantees 100% determinism, bypasses network latency, and makes subsequent runs free.
* **Retries & Robustness:** Standard 180s timeout is configured on all `urllib` HTTP connections. Robust exception wrappers wrap the VLM see-image and LLM claim-extraction passes. If a rate limit (HTTP 429) or connection error occurs (e.g., daily free limits on OpenRouter), the system fails closed gracefully to `not_enough_information` with `valid_image = false` and `evidence_standard_met = false`, preventing process crashes and maintaining deterministic row counts.
* **TPM/RPM considerations:** For high-volume production, a backoff retry decorator with exponential delays (1s, 2s, 4s, 8s) should be wired directly into the transport wrappers to handle temporary rate limits.

### 6. Model Configuration Comparison
* **Strategy A (Nvidia Nemotron-3-nano free-tier):** Serves as an affordable dev/testing proxy. However, reasoning models are prone to rambles that hit token limits (finish_reason='length') and require disabling reasoning (`reasoning: {enabled: false}`) and setting `max_tokens: 4096` to reliably emit structured JSON.
* **Strategy B (Frontier Claude 3.5 Sonnet / Opus):** Highly recommended for production. Superior multi-modal capabilities ensure correct extraction of spatial details, resulting in higher accuracy on object part classification, with native JSON schema formatting mitigating formatting syntax errors.