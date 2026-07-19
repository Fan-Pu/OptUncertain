# Missing parameter values used in the 100-case benchmark

Audit date: 2026-07-15

This document fills the parameter checklist using the configuration, source code, and saved artifacts of the completed 100-case benchmark. It reports the settings that were actually used; it does not infer unrecorded values. “Not sent” means the request omitted that parameter and the provider default applied. “Not recorded” means the value cannot be recovered from the saved experiment and should not be claimed in the paper.

## Scope and reproducibility anchors

The same exact 100 cases were evaluated by the four proposed graph-MLLM variants, MLLM-Direct, and VLFM-G. The authoritative test manifest is:

- Path: `mllm_debug_outputs_balanced100_GPT54Medium/batch_test/sampled_generated_cases.json`
- SHA-256: `dcfca0c050fb7f2d2b2b3376ed91475233d7fd7c381394a97fa5aafed6b61ac4`
- Sampling seed: `0`
- Sampling rule: balanced by parameter configuration (`param_config`)
- Source pool: 225 persisted generated cases

Completed method roots:

| Method | Saved output root |
|---|---|
| Proposed, GPT-Medium | `mllm_debug_outputs_balanced100_GPT54Medium` |
| Proposed, Gemma-4-31B Thinking | `mllm_debug_outputs_balanced100_Gemma431BThinking` |
| Proposed, Qwen3.6-35B-A3B Thinking | `mllm_debug_outputs_balanced100_Qwen36_35BA3BThinking` |
| Proposed, Qwen3.6-35B-A3B Instant | `mllm_debug_outputs_balanced100_Qwen36_35BA3BInstant` |
| MLLM-Direct, GPT-Medium | `mllm_debug_outputs_balanced100_MLLMDirect_GPT54Medium` |
| VLFM-G | `mllm_debug_outputs_balanced100_VLFMG` |

Primary local evidence is in `config/default_config.json`, `scenarios/batch_test.json`, `optimization_model/optimizer.py`, `semantic_persistence/hypothesis_graph.py`, `semantic_persistence/mllm_client.py`, `benchmark_methods/mllm_direct.py`, `benchmark_methods/vlfm_g.py`, `Helper.py`, `main.py`, and `evaluate_batch_metrics.py`.

## 1. Core optimization hyperparameters

| Setting | Value used | Selection and scope |
|---|---:|---|
| Configured target reward weight, $w^{\mathrm{goal}}$ | `0.45` | Fixed across all four proposed variants and all team sizes. Important: target-directed mode used a lexicographic objective, so this configured number was not the active primary-objective coefficient; see below. |
| Travel-distance weight, $w^{\mathrm{dist}}$ | `0.17` | Secondary lexicographic route-cost objective. |
| Hypothesized-edge nonexistence weight, $w^{\mathrm{arc}}$ | `0.05` | Secondary lexicographic route-cost objective. |
| Node-nonexistence weight, $w^{\mathrm{node}}$ | `0.03` | Secondary lexicographic route-cost objective; this weight was omitted from the supplied checklist but was used by the code. |
| Revisit weight, $w^{\mathrm{visit}}$ | `0.30` | Secondary lexicographic route-cost objective. |
| Objective mode | Lexicographic, two priorities | Priority 2 maximized the unnormalized target-reward term with objective weight `1.0`, absolute tolerance `0`, and relative tolerance `0`. Priority 1 maximized the negative normalized route cost with weights `0.17`, `0.05`, `0.03`, and `0.30`. |
| Target score used by optimizer | Normalized `target_probs` | `target_directed_use_raw_target_probs=false`. |
| Planning horizon | No fixed arc/depth limit | Each MILP may select an acyclic simple route over the current hypothesis graph; MTZ order variables bound it implicitly by the current node count. Only the first grounded viewpoint-to-viewpoint hop is executed, after which the graph is updated and the problem is solved again. |
| Proposed-method waiting | Not applicable | `allow_inactive_agents=false`; every agent must take exactly one grounded first hop. No proposed wait variable or wait penalty was used. |

The five configured weights sum to `1.0`, but they must not be described as the coefficients of one weighted-sum objective in the evaluated target-directed configuration. The reward was optimized first, and route cost was optimized second without degrading the primary reward.

The weights were fixed in the shared configuration before the stored evaluations and were identical across MLLM variants, single-agent cases, and multi-agent cases. No weight-search log or validation-selection artifact exists, so the manuscript should not claim that these five weights were tuned on validation cases.

## 2. Hypothesis-update parameters

| Setting | Value or rule used |
|---|---|
| Prior VV distance variance, $\sigma_{\mathrm{vv}}^2$ | `4.0` |
| Distance-cue parameter, $\kappa_{\mathrm{vv}}$ | `1.0` |
| Semantic-zone cue, $\varrho$ | `0.7`, satisfying $1/2<\varrho<1$ |
| Numerical stabilizer, $\varepsilon$ | `1e-6` |
| Minimum/maximum edge-existence clipping | None |
| Edge-retention or pruning confidence threshold | None |
| Maximum hypothesis age | Unlimited; no age counter or age-based deletion |
| Target-score pruning threshold | None |
| Maximum hypotheses per target | Unlimited by an explicit parameter |

Hypothesized VV edge rules:

| Quantity | Exact rule |
|---|---|
| Initial distance mean | The MLLM-provided `dist`, required to be a finite positive numeric value. It is interpreted in the same meter-scale units as simulator edge lengths. |
| Initial distance variance | One MLLM-provided positive scalar, `edge_distance_variances.viewpoint_viewpoint`, is used for every new hypothesized VV edge in that response. |
| Variance mapping | None. No categorical confidence-to-variance lookup is used. |
| Conditional existence prior | MLLM-provided `exist_prob` in `(0,1]`. |
| Grounded-edge statistics | Population mean and population variance of all currently grounded VV edge lengths; `epsilon` is added to the variance. |
| No grounded VV edges | Existing uncertain edges retain their previous mean, variance, and conditional existence prior. No synthetic empirical statistic is inserted. |
| One grounded VV edge | Empirical mean equals that edge length and empirical variance equals `epsilon`. |
| Invalid/missing distance | Validation failure and MLLM retry; no fallback value. |
| Invalid/missing/nonpositive variance | Validation failure and MLLM retry; no fallback value. |
| Retry exhaustion | Hard `MLLMRetryExhaustedError`; no degraded graph update is substituted. |

For an existing uncertain edge, the distance cue uses

$$
\sigma_c^2=\frac{\sigma_{\mathrm{emp}}^2}{1+\kappa_{\mathrm{vv}}I_{\mathrm{same\ zone}}},\qquad
\sigma_{\mathrm{post}}^2=\left(\sigma_{\mathrm{prior}}^{-2}+\sigma_c^{-2}\right)^{-1},
$$

with the posterior mean obtained by precision-weighted averaging of the prior and empirical means. The zone cue updates existence odds using `varrho=0.7`, with a distance-compatibility penalty when grounded statistics exist.

There is no confidence-threshold removal. Hypothesized VV edges are removed structurally when they become invalid, including when an endpoint becomes grounded/visited under the graph rules. In the final saved proposed runs, all 4,371 readable MILP-aligned graph snapshots contained `0` hypothesized VV edges; therefore the uncertain-edge penalty was configured but its realized value was zero in those stored decisions.

## 3. Target-viewpoint score settings

| Setting | Value or rule used |
|---|---|
| Raw score range | `[0,+infinity)`; finite, nonnegative numeric values |
| Raw score type | Continuous |
| Interpretation | Relative raw target-location score, not a calibrated probability |
| Normalization | Separately for each active target over eligible, noncurrent, ungrounded, unvisited viewpoints: $p_{v,k}=\xi_{v,k}/\sum_{u\in E_k}\xi_{u,k}$. |
| All-zero denominator | Invalid output; the validator requests a corrected response with at least one positive eligible score. No numerical fallback is used. |
| Omitted score | The graph response is incremental: an omitted previously materialized score is preserved. A newly required score with no prior value causes validation failure and retry. |
| Evidence-strength categories | `low`, `medium`, or `high`; the validator applies an isotonic repair so raw scores are nondecreasing with evidence strength. |
| Previously visited/current/grounded viewpoint | For every still-active target that was not detected there, raw and normalized scores are set to `0` and remain detection-fixed at zero. |
| Found-target removal | An active target is marked found online when the detector returns its ID with a valid horizontal center for any agent. It is then removed from graph requests and from every node’s score maps. This online action does not wait for the offline oracle verification used for reported metrics. |
| Illustrative-figure normalization | Not part of benchmark execution. `scripts/add_target_probabilities_panel.py` uses one global maximum shared across the selected targets, not a separate maximum per target. |

## 4. VLFM-G baseline

### Model and tuned parameter

| Setting | Value used |
|---|---|
| BLIP-2 model | `Salesforce/blip2-itm-vit-g` |
| Pinned revision | `d3788a04efa0f9e897305f5b9d9dedeaa3afb99d` |
| Model class/head | `Blip2ForImageTextRetrieval`, `use_image_text_matching_head=false`; `logits_per_image` is used as the image-text contrastive score |
| Device and precision | One CUDA GPU, `float32` |
| Verified GPU | NVIDIA GeForce RTX 3070 |
| Processor input | Each native 800×600 crop is passed to the pinned `AutoProcessor`, which resizes it to `224×224`, converts to RGB, rescales, and normalizes it. The pinned processor metadata is available from the [official checkpoint](https://huggingface.co/Salesforce/blip2-itm-vit-g/blob/d3788a04efa0f9e897305f5b9d9dedeaa3afb99d/preprocessor_config.json). |
| Target prompt | `Seems like the following target may be ahead: {description}.` |
| Semantic weight, $\alpha$ | `1.0` |
| Selected distance weight, $\beta$ | `0.0` |
| Candidate $\beta$ values | `{0.0, 0.1, 0.25, 0.5, 1.0}` |
| Wait utility | `-2.0` |
| Unreachable utility | `-1,000,000.0` |

The selected `beta=0.0` came from `mllm_debug_outputs_vlfmg_calibration/batch_test/vlfmg_beta_selection.json`. Selection was lexicographic by:

1. team PPL-total, descending;
2. progress, descending;
3. verified success rate, descending;
4. mean total distance, ascending; and
5. beta, ascending.

The calibration used 20 held-out cases selected with seed `1`, disjoint from the 100 test cases but drawn from the same five scans. The calibration manifest SHA-256 is `9b39744405dabfb974c15540346c8f6d814b770f526b6828c78004dbcb21e955`. It contains four cases per scan; team sizes `{1:7, 3:7, 5:6}` and target counts `{1:8, 4:8, 8:4}`.

### Directional views and fusion

- Eight central-elevation crops are used at headings `0°, 45°, 90°, 135°, 180°, 225°, 270°, 315°`.
- Each crop is the native 800×600 MatterSim frame at elevation `0°`, vertical FOV `60°`, and horizontal FOV `75.17817894°`.
- For a frontier bearing offset $\Delta\theta$, directional confidence is

$$
c(\Delta\theta)=
\begin{cases}
\cos^2\!\left(\frac{|\operatorname{wrap}(\Delta\theta)|}{\mathrm{HFOV}/2}\frac{\pi}{2}\right), & |\operatorname{wrap}(\Delta\theta)|\leq \mathrm{HFOV}/2,\\
0, & \text{otherwise.}
\end{cases}
$$

- Within one step, directional/agent evidence is combined as

$$
S_{\mathrm{obs}}=\frac{\sum_j c_jS_j}{\sum_jc_j},\qquad
C_{\mathrm{obs}}=\frac{\sum_jc_j^2}{\sum_jc_j}.
$$

- Historical and new evidence are fused as

$$
S_{\mathrm{new}}=\frac{C_{\mathrm{prev}}S_{\mathrm{prev}}+C_{\mathrm{obs}}S_{\mathrm{obs}}}{C_{\mathrm{prev}}+C_{\mathrm{obs}}},\qquad
C_{\mathrm{new}}=\frac{C_{\mathrm{prev}}^2+C_{\mathrm{obs}}^2}{C_{\mathrm{prev}}+C_{\mathrm{obs}}}.
$$

- A frontier’s target-search score is the maximum fused score over currently active targets.
- Frontier semantic scores are min-max normalized: $(S_v-S_{\min})/(S_{\max}-S_{\min}+10^{-8})$. If all semantic values are equal, every normalized value is `0.5`.
- Graph-geodesic distances are computed with Dijkstra over grounded discovered edges. Each finite distance is divided by the maximum finite agent-frontier distance plus `1e-8`. If the maximum distance is zero, every finite normalized distance is zero; unreachable distances receive the unreachable utility. Equal positive distances therefore normalize to `1`, not `0.5`.
- Assignment utility is $\alpha\bar S_v-\beta\bar d_{qv}$. With the selected `beta=0`, distance does not change final assignment utility.
- Hungarian assignment uses sorted agent/frontier order and subtracts `1e-8 × column_index + 1e-10 × row_index` for deterministic tie-breaking. First-hop conflicts are resolved by highest utility and then lexicographically smaller agent ID.

## 5. MILP solver configuration and observed solve statistics

| Setting | Value used |
|---|---|
| Solver | Gurobi Optimizer |
| Version | `12.0.1` |
| Time limit per decision | `30.0 s` |
| Relative MIP gap | Not explicitly set; Gurobi default `1e-4` |
| Absolute MIP gap | Not explicitly set; Gurobi default `1e-10` |
| Threads | Not explicitly set; Gurobi `Threads=0` (automatic) |
| Solver seed | Not explicitly set; Gurobi `Seed=0` |
| Presolve | Not explicitly set; Gurobi `Presolve=-1` (automatic) |
| Warm start | None |
| Solver output | Suppressed (`OutputFlag=0`) |
| LP-file export | Disabled in the final configuration; this does not change the in-memory model |
| Optimization hardware | CPU in the experiment container; exact CPU model was not recorded |

Observed final-artifact statistics across all four proposed 100-case runs:

| Variant | MILP decisions | Mean (s) | Median (s) | Maximum (s) | Stored status |
|---|---:|---:|---:|---:|---|
| GPT-Medium | 1,034 | 0.130744 | 0.049960 | 3.510952 | 1,034 optimal |
| Gemma-4-31B Thinking | 950 | 0.194875 | 0.069141 | 5.160354 | 950 optimal |
| Qwen3.6 Thinking | 1,113 | 0.032097 | 0.012683 | 0.749654 | 1,113 optimal |
| Qwen3.6 Instant | 1,275 | 0.116096 | 0.037497 | 2.549269 | 1,275 optimal |
| **All proposed variants** | **4,372** | **0.115294** | **0.032703** | **5.160354** | **4,372 optimal** |

- Time-limit terminations in final artifacts: `0`.
- Infeasible subproblems in final artifacts: `0`.
- Achieved MIP gap: not persisted for the lexicographic multiobjective solves, so a mean achieved gap cannot be reported. All stored statuses are `OPTIMAL` under the configured tolerances.
- A time-limit result is accepted only when Gurobi returns a feasible incumbent; that incumbent is executed. Time limit without an incumbent, infeasibility, or any other unaccepted status raises an error and produces no action.

Optional graph-scale statistics, computed over 4,371 readable MILP-aligned snapshots (one additional snapshot file was zero bytes and was not used for these optional counts):

| Quantity | Mean | Median | Minimum | Maximum |
|---|---:|---:|---:|---:|
| Viewpoint nodes | 21.993 | 19 | 2 | 59 |
| Grounded VV edges | 33.875 | 27 | 1 | 135 |
| Hypothesized VV edges | 0 | 0 | 0 | 0 |

Binary-variable counts, constraint counts, and the largest MILP by those measures were printed during execution but were not persisted systematically; they should be reported as not recorded rather than reconstructed heuristically.

## 6. Proposed graph-MLLM inference settings

The supplied checklist’s “Gemma-Instant” row does not match the completed experiment. The actual fourth comparison set contains **Gemma-4-31B Thinking**, not Gemma-Instant.

| Variant | Exact model ID | Provider/API | Reasoning/thinking control | Temperature | Top-p | Top-k | Max output | Seed | Image detail | Samples |
|---|---|---|---|---:|---:|---:|---:|---|---|---:|
| GPT-Medium | `gpt-5.4-2026-03-05` | OpenAI Responses API | Explicit `reasoning.effort=medium`; default/normal service tier | Not sent | Not sent | Not sent | 32,768 | Not sent | Not sent | 1 |
| Gemma-4-31B Thinking | `google/gemma-4-31B-it` | Hugging Face OpenAI-compatible router | No explicit thinking flag; the run relied on model/provider behavior | `0.7` | `0.8` | Not sent | 32,768 | Not sent | Not sent | 1 |
| Qwen3.6 Thinking | `Qwen/Qwen3.6-35B-A3B` | Hugging Face OpenAI-compatible router | No explicit thinking flag; the run relied on model/provider behavior | `0.7` | `0.8` | Not sent | 32,768 | Not sent | Not sent | 1 |
| Qwen3.6 Instant | `Qwen/Qwen3.6-35B-A3B` | DeepInfra OpenAI-compatible API | Explicit `chat_template_kwargs.enable_thinking=false` | `0.7` | `0.8` | `20` | 32,768 | Not sent | Not sent | 1 |

For Qwen3.6 Instant, the request also sent `presence_penalty=1.5`, `min_p=0.0`, and `repetition_penalty=1.0`. Gemma and Qwen Thinking had `extra_body` and presence-penalty transmission disabled. GPT Responses requests did not transmit the chat-completion sampling constants.

Shared graph-generation settings:

| Setting | Exact value or rule |
|---|---|
| Visual input | One annotated panorama per agent, all agents included jointly in one graph request; JPEG quality `85`, resized to at most `1660 px` wide (normally `1660×610`) |
| Prompt | Built by `MLLMClient._build_instruction`; complete per-step user prompts were saved as `user_message_step_XXXX.txt` |
| Top-level JSON keys | `current_viewpoints_reassignment`, `visible_region_nodes`, `viewpoint_target_scores`, `viewpoint_node_assigns`, `new_edges`, and `edge_distance_variances` |
| Structured output | JSON-object response constraint where supported, plus strict local schema/type/range validation |
| Provider without response-format support | The request is retried once without `response_format`; the same JSON-only prompt and strict local validator still apply |
| Maximum context length | Not explicitly set in the client; provider/model context limit |
| Graph-context truncation | None; the full compact current graph summary is sent |
| Malformed-output retries | `6` retries after the initial attempt, for at most `7` validation attempts |
| API timeout | `900 s` per request |
| Timeout retries | One request-level timeout retry, for at most two timeout attempts per validation attempt |
| Repeated API failure | No semantic fallback; the error propagates and the case terminates/incompletes according to the run controller |
| Maximum zones or new edges | No explicit numeric cap; outputs are limited to legal current-step IDs and schema rules |
| Duplicate zone rule | Existing regions must be referenced by ID and must not be re-emitted as new nodes. New region IDs must be unique and assigned to at least one viewpoint; there is no label-similarity threshold. |
| Duplicate edge rule | Undirected endpoint pairs are canonicalized. An already existing edge is not inserted again; illegal/duplicated optional edges are rejected or removed by the contract repair. |
| Equal target scores | Permitted when evidence is indistinguishable; there is no score-specific tie-break. Deterministic model ordering/Gurobi settings decide any downstream tie. |

## 7. MLLM-Direct baseline

| Setting | Value or rule used |
|---|---|
| Exact model | GPT-Medium, `gpt-5.4-2026-03-05` |
| Provider/API | OpenAI Responses API |
| Reasoning | Explicit medium reasoning effort |
| Service tier | `flex` for uncached direct-action requests |
| Temperature/top-p/top-k | Not sent by the actual Responses request |
| Maximum output tokens | `1,024` |
| Seed/image detail | Not sent |
| Number of responses | One per attempt |
| Observation | Current annotated panorama only, at most 1660 px wide, JPEG quality 85; no prior-image or map memory |
| Action context | Active target list, allowed neighboring short viewpoint IDs, one-step distances, and IDs already reserved by earlier agents that round |
| Prompt | Exact system/user templates in `benchmark_methods/mllm_direct.py`; per-step prompts saved as `direct_action_prompt_step_XXXX_agent_AGENT.txt` |
| First priority order | Lexicographically sorted agent IDs, beginning with `agent0` |
| Rotation | For step $t$ (one-indexed), cyclic offset `(t-1) mod number_of_agents` |
| Collision rule | Once an agent selects a short neighbor ID, that first hop is reserved and removed from later agents’ allowed sets for that round |
| Invalid output/ID | One repair attempt; after two total attempts, hard `MLLMRetryExhaustedError`. No nearest-ID or random fallback. |
| Equal-choice rule | The model chooses; no additional algorithmic tie-break among equal-looking actions |
| Waiting | The model may not choose `WAIT` while any unreserved local action exists. Waiting is inserted automatically only when no unreserved local action remains. |
| Model-matched baselines | Only the GPT-Medium direct baseline was evaluated; there was not one direct baseline per proposed graph model. |

## 8. Common target detector

| Setting | Value or rule used |
|---|---|
| Model | `gpt-5.4-2026-03-05` |
| Provider/API | OpenAI Responses API |
| Reasoning | Explicit medium effort |
| Temperature/top-p/top-k | Not sent by the actual Responses request |
| Maximum output tokens | `32,768` |
| Seed/image detail | Not sent |
| Prompt version | `direct_detection_v1` |
| Image input | One clean, unannotated, smooth multi-elevation 360° panorama per agent; all agents processed jointly; JPEG quality 85, at most 1980 px wide (normally `1980×728`) |
| Output | Binary target IDs plus normalized horizontal target-center positions in `[0,1]`; no confidence score |
| Detection threshold | Not applicable because the model returns a binary decision |
| Malformed-output retries | Six retries after the initial attempt, at most seven attempts |
| Failure | Hard error after retry exhaustion; no detector fallback |
| Targets queried | Only targets still active at the beginning of the step |
| Found targets queried again | No |
| Partial visibility | Report only when the visible object plus described support/location cues make it the strongest target-specific match. Do not report an absent, unidentifiable, heavily occluded, or contradictory candidate. |
| Online found condition | Any schema-valid detector claim for an active target from any agent marks it found; online execution does not consult the oracle annotation. |
| Offline verification | A predicted target is a TP only if that agent’s current stable viewpoint ID is in the target’s annotated `detectable_viewpoint_ids`; otherwise it is an FP. An unpredicted active target at an annotated viewpoint is an FN. |
| Cache | Exact-key shared cache enabled for read/write, with conflicting records quarantined |

Detector service tier was not uniform over the entire multi-method experiment. The shared cache currently contains 10,708 per-target records produced with `flex` and 8,962 with no requested tier (default/normal); these are cache-record counts, not API-request counts. The final VLFM-G continuation used `detection_service_tier=null` for new detector requests and reused exact cache hits without making a request.

## 9. Dataset and case generation

### Scans, sampling, and reachability

| Setting | Value or rule used |
|---|---|
| Test scans | `r47D5H71a5s`, `zsNo4HB9uLZ`, `JF19kD82Mey`, `RPmz2sHmrrY`, `17DRP5sb8fy` |
| Validation scans | The same five scans; beta calibration was episode-disjoint, not scan-disjoint |
| Validation/test cases | 20 calibration cases; 100 test cases |
| Test sampling seed | `0` |
| VLFM-G calibration selection seed | `1` |
| Initial 225-case generation seed | Not recorded. `generate_batch_scenarios` used an unseeded `random.Random()` and then persisted the generated manifest. |
| Target/start generation seeds | Not separately set or recorded for the 225-case pool |
| Exact reproducibility | Use the persisted test manifest and its SHA-256 above; do not regenerate the pool |
| Agent starts | Distinct navigable viewpoints. First start is sampled, then each additional start maximizes its minimum graph-geodesic distance to selected starts; ties are sampled. |
| Minimum start separation | No numeric threshold; farthest-point max-min selection only |
| Targets initially visible | Allowed. In the final manifest, 50/100 cases contain at least one target whose annotated viewpoint set includes an agent start (89 selected target instances in total). |
| Target distribution | 40 one-target cases, 40 four-target cases, 20 eight-target cases |
| Reachability constraint | No explicit rejection filter in generation. Audit of the persisted test manifest found every selected target reachable from every agent start through the connectivity graph. All 40 defined targets have at least one detectable viewpoint. |
| Multiple targets in one room/zone | Allowed; no room/zone exclusivity constraint |
| Visibility annotation | Each target has an explicit hand-curated list of stable Matterport viewpoint IDs in `scenarios/batch_test.json` |
| Minimum visible area | No numeric area threshold is encoded; recognition is defined by membership in the curated detectable-viewpoint list |
| Detectable viewpoints per distinct target | 40 targets; minimum 1, mean 5.725, median 5, maximum 14 |
| Repetitions | One run of each selected case per method; no independent repeated trials |

### Exact 100-case composition

| Team size | 1 target | 4 targets | 8 targets | Total |
|---:|---:|---:|---:|---:|
| 1 agent | 14 | 14 | 6 | 34 |
| 3 agents | 13 | 13 | 7 | 33 |
| 5 agents | 13 | 13 | 7 | 33 |
| **Total** | **40** | **40** | **20** | **100** |

Every scan contributes exactly 20 test cases.

## 10. Simulator and observation settings

| Setting | Value used |
|---|---|
| Simulator | Matterport3D Simulator (`MatterSim`); exact package version/commit was not pinned or recorded |
| Camera height | Not explicitly set; the simulator uses the dataset viewpoint pose |
| Raw perspective frame | `800×600` pixels |
| Vertical FOV | `60°` |
| Horizontal FOV | `75.17817894°`, derived from aspect ratio and vertical FOV |
| Panorama source views | 576 frames: 192 headings at each of three elevations |
| Heading interval | `1.875°` (`360°/192`) |
| Elevations | `+30°`, `0°`, `-30°` |
| Native smooth panorama | `3264×1200` pixels, spanning 360° horizontally and approximately `-60°` to `+60°` pitch |
| Stitching | Spherical ray reprojection to the best valid perspective source view, followed by bilinear sampling (`cv2.INTER_LINEAR`) |
| Graph panorama annotations | Red numeric short viewpoint IDs (font scale 2.0, thickness 3) plus heading/pitch guides; detector panorama has no annotations |
| Travel distance | Sum of 3D Euclidean distances between adjacent connectivity-viewpoint poses; waits contribute zero |
| Units | Matterport3D metric coordinates, reported in meters |
| Transition model | Ideal discrete graph transition to a navigable neighboring viewpoint; no low-level controller |
| Collision handling | Not applicable to physical geometry; actions are constrained to simulator connectivity. Multi-agent first-hop conflicts are prevented by the method-specific assignment/reservation logic. |
| Communication | Centralized shared graph/state with no bandwidth, latency, or packet-loss model |
| Synchronization | Synchronous: observe all agents, detect/update/plan jointly, then execute one action per agent |
| Localization | Perfect stable viewpoint identity and simulator pose |

## 11. Episode termination and evaluation conventions

| Setting | Value or rule used |
|---|---|
| Maximum decision steps | `30` |
| Early success termination | Yes; the whole episode stops immediately after all targets are marked found |
| Proposed method with no executable first hop | Hard runtime error; no wait or random-move fallback |
| MLLM-Direct with no unreserved move | Automatic wait |
| VLFM-G with no frontier | Terminates with `vlfm_no_frontier`; an assigned dummy action is a wait |
| Wait consumes a step | Yes for a nonterminal Direct/VLFM-G round |
| All agents stop together | Yes |
| Wait travel cost | `0` |
| Progress | Number of oracle-verified distinct targets found divided by the number of targets in the case |
| PPL zero-distance rule | $\mathrm{PPL}=\mathrm{progress}$ when both actual and oracle distance are zero; otherwise $\mathrm{progress}\times d_{\mathrm{oracle}}/\max(d_{\mathrm{actual}},d_{\mathrm{oracle}})$. |
| Precision/recall/F1 aggregation | Micro, pooling TP/FP/FN counts across all cases, steps, agents, and active targets |
| Zero denominator | Empty CSV field (`""`) for precision, recall, or F1 when its denominator is zero |
| Repeated queries | Each agent-active-target opportunity at every saved detection step is counted. After any online claim, that target is removed from later steps even if the claim is an offline FP. Multiple agents at the claim step are still evaluated. |
| Confidence intervals | None |
| Bootstrap samples | Not applicable |
| Statistical significance test | None |

## 12. Runtime and hardware reporting

| Component | What was used/recorded |
|---|---|
| Proposed MLLMs and detector | Remote APIs: OpenAI, Hugging Face router, and DeepInfra, as listed above; provider-side inference hardware was not exposed |
| MLLM-Direct | Remote OpenAI Responses API |
| VLFM-G local model | One NVIDIA GeForce RTX 3070 with CUDA, float32 |
| Proposed-run CPU/RAM allocation | Earlier experiment container reported 8 CPUs and 7.6 GiB RAM; exact CPU model was not recorded |
| Graph-generation latency | Not systematically persisted; exact mean unavailable |
| Graph-update latency | Not separately instrumented/persisted |
| Target-detection latency | Not systematically persisted; cache hits made no API call |
| Direct-action latency | Not systematically persisted |
| MILP latency | Mean 0.115294 s, median 0.032703 s, maximum 5.160354 s across 4,372 saved decisions |
| Total replanning-cycle latency | Not systematically persisted; exact mean and maximum unavailable |

The manuscript should not estimate the missing latency values from a few console examples. They require a new instrumented timing experiment if they are essential.

## 13. Manuscript-ready compact report

The following wording is faithful to the stored experiment:

```latex
All proposed variants shared the same hypothesis and optimization settings.
The configured weights were
$w^{\mathrm{goal}}=0.45$,
$w^{\mathrm{dist}}=0.17$,
$w^{\mathrm{arc}}=0.05$,
$w^{\mathrm{node}}=0.03$, and
$w^{\mathrm{visit}}=0.30$.
Because target-directed mode was enabled, we used a lexicographic objective:
the unweighted target reward was maximized first, followed by the normalized
route-cost objective using the latter four penalty weights.
The hypothesis-update parameters were
$\sigma_{\mathrm{vv}}^2=4.0$,
$\kappa_{\mathrm{vv}}=1.0$,
$\varrho=0.7$, and
$\varepsilon=10^{-6}$.
VLFM-G used $\alpha=1$ and $\beta=0$, where $\beta$ was selected from
$\{0,0.1,0.25,0.5,1\}$ on 20 held-out cases using lexicographic validation by
team PPL, progress, verified success, and travel distance.
The rolling-horizon MILPs were solved with Gurobi 12.0.1 using a 30-s time
limit and the default relative MIP-gap tolerance of $10^{-4}$.
Across 4,372 decisions from the four proposed 100-case runs, mean, median, and
maximum solve times were 0.1153, 0.0327, and 5.1604 s, respectively; all saved
decisions were optimal.
```

For the model-specific inference table, use the exact rows in Section 6. In particular, do not label the evaluated Gemma variant as “Gemma-Instant,” and do not claim that the Hugging Face Qwen Thinking request explicitly set a thinking flag.

## 14. Items that remain genuinely unavailable

The following values were not recorded and cannot be reported exactly without a new experiment or a pinned environment record:

- exact MatterSim version/commit;
- explicit camera height;
- exact CPU model used for the completed proposed runs;
- provider-side MLLM hardware;
- systematic graph-generation, graph-update, detector, direct-action, and full-cycle latency means/maxima;
- achieved multiobjective MIP gaps;
- per-decision MILP binary-variable and constraint counts; and
- a documented validation/tuning procedure for the five proposed objective weights.

These should be stated as not recorded or omitted, not filled with assumed defaults.
