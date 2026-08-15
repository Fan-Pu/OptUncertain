# Why the Relaxed Qwen-Thinking Run Still Saved `new_edges: []`

## Purpose and scope

This report explains why the relaxed-edge Qwen-Thinking experiment did not materialize any uncertain viewpoint--viewpoint edges, even though newly observed viewpoints were made immediately eligible as edge endpoints. The analysis concerns the frozen three-agent case `RPmz2sHmrrY_case_0030` and the corrected V2 smoke run. It distinguishes model generation, payload repair, strict validation, graph materialization, and experimental interpretation so that the issue can be reported accurately in the paper.

### Compact outline

- The relaxation removed the temporal requirement that an endpoint must already exist in a previous graph snapshot.
- It did not remove the exact output-schema, visibility, non-current, ungrounded, unvisited, and viewpoint-type requirements.
- Qwen proposed at least 22 optional edge objects across six planning steps, but all were removed by the strict repair stage before graph materialization.
- Retained rejected responses demonstrate schema violations, including incorrect endpoint fields and missing `edge_type` and `dist`.
- The corrected V2 logger retained only aggregate rejection counts, not the unrepaired accepted payload or a per-edge rejection reason; therefore, the precise cause of every V2 rejection cannot be reconstructed.
- All accepted semantic files consequently contain `new_edges: []`, and all graph snapshots contain zero ungrounded edges.
- The result is a one-case failure mode, not evidence that the relaxed rule can never generate useful edges.

## Executive conclusion

The temporal restriction was successfully removed, but this condition was only one part of the edge-admissibility contract. The corrected implementation allows a newly observed, non-current viewpoint that has no previous graph record to enter the edge validator with the synthesized prior state

```text
prior_grounded = false
prior_visit_times = 0.
```

The absence of saved edges therefore does **not** mean that the original temporal restriction remained active. Instead, Qwen generated optional edge candidates that violated at least one of the remaining structural requirements. The repair stage removed 22 candidates in total, after which the accepted payloads contained empty `new_edges` arrays. Because the current persistence mechanism saves the repaired payload rather than the unrepaired candidate list, the exact rejection category of each V2 candidate is unavailable. Retained responses from the first smoke attempt nevertheless provide direct evidence of output-schema noncompliance.

The scientifically defensible paper statement is therefore:

> Relaxing endpoint eligibility increased the model's opportunity to propose edges, but it did not yield any admissible uncertain edge in the examined episode. The model produced candidate edges, yet all candidates were removed by the unchanged structural validation rules before graph materialization.

## 1. What was relaxed

### 1.1 Original temporal restriction

Under the original contract, an edge endpoint needed a prior visit-state record in the compact graph summary. A viewpoint first observed in the current step did not yet have such a record. It could therefore be considered only after entering the graph and remaining visible, ungrounded, and unvisited in a later step. This created a narrow temporal window for edge generation.

### 1.2 Revised endpoint treatment

The separate prompt variant `prompts/graph_relaxed_newly_observed_edges.json` changes only this eligibility timing. When the variant is active, `_augment_edge_endpoint_statuses_from_current_observations()` inserts a state record for each newly visible viewpoint that is absent from the prior graph:

```python
{
    "prior_grounded": False,
    "prior_visit_times": 0,
    "prior_raw_target_probs": {},
}
```

This behavior is implemented in `semantic_persistence/mllm_client.py`, lines 3639--3655. Existing graph records are preserved because the helper does not overwrite a viewpoint that already has a status record.

The regression test `test_first_step_new_edge_is_rejected_by_original_and_accepted_by_variant` demonstrates the intended difference. The same well-formed first-step edge is rejected by the original client and accepted by the relaxed client. The relevant test is in `test_relaxed_edge_prompt.py`, beginning at line 138.

### 1.3 What was deliberately not relaxed

The following requirements remained unchanged:

1. Every edge must be represented by a dictionary with exactly five fields:

   ```json
   {
     "i": 3,
     "j": 16,
     "edge_type": "VV",
     "exist_prob": 0.6,
     "dist": 1.5
   }
   ```

2. Both endpoints must be viewpoint nodes present in the current observation context.
3. Neither endpoint may be a current agent viewpoint.
4. The edge may not be a self-edge.
5. `edge_type` must be `VV`.
6. Both endpoints must be ungrounded and unvisited.
7. `exist_prob` must be a valid probability and `dist` must be positive.
8. The panorama and spatial context must support a plausible direct traversable connection; co-visibility or shared semantic-region membership alone is insufficient.

The exact structural checks appear in `semantic_persistence/mllm_client.py`, lines 5624--5677. The temporal relaxation changes item 6 only for newly observed endpoints by providing their initial status; it does not bypass any other requirement.

## 2. Where candidates disappear in the pipeline

The graph-generation pipeline has four distinct stages:

```text
Qwen response
    -> JSON parsing
    -> deterministic payload repair
    -> strict payload validation
    -> graph update and saved hypothesis snapshot
```

The distinction between a **proposed**, **retained**, and **materialized** edge is essential.

### 2.1 Qwen generation

Qwen may return zero or more objects under `new_edges`. At this stage, an object is only a model proposal. It is not yet part of the hypothesis graph.

### 2.2 Deterministic repair

Before strict validation, `_repair_graph_mllm_payload()` examines every optional edge. It keeps an edge only if:

- the object has exactly `{i, j, edge_type, exist_prob, dist}`;
- the endpoints are current-step viewpoint IDs;
- the endpoints are non-current;
- status records exist;
- both endpoints are ungrounded and unvisited.

Otherwise, the edge is removed. The repair implementation is in `semantic_persistence/mllm_client.py`, lines 4519--4560.

Importantly, the repair does not translate alternative field names, infer a missing distance, or invent an edge type. Such transformations would introduce heuristic post-processing and would change the model prediction being evaluated.

### 2.3 Strict validation

Only retained edges reach `_validate_payload_impl()`. The validator again enforces the exact schema, numeric ranges, endpoint types, current-viewpoint exclusion, and prior state. The graph is updated only after the entire repaired payload passes validation.

### 2.4 Persistence

The accepted `semantic_step_XXXX.json` file contains the repaired payload. Therefore, an empty saved `new_edges` array means:

> No candidate survived repair and validation.

It does **not** necessarily mean:

> Qwen never proposed an edge.

This persistence choice is the main reason the saved files alone obscure the failure mechanism.

## 3. Evidence from the corrected V2 run

### 3.1 Candidate-removal counts

The V2 log records the following aggregate removals:

| Planning step | Candidate edges removed | Saved edges |
|---:|---:|---:|
| 1 | 6 | 0 |
| 2 | 5 | 0 |
| 3 | 5 | 0 |
| 4 | 0 | 0 |
| 5 | 4 | 0 |
| 6 | 0 | 0 |
| 7 | 1 | 0 |
| 8 | 1 | 0 |
| **Total** | **22** | **0** |

The aggregate messages are recorded in `batch_logs/QwenThinking_relaxed_edges_case0030_v2.log` at lines 43--44, 82--83, 116--117, 198--199, 289--290, and 327--328.

Thus, Qwen did attempt to add uncertain connectivity in six of the eight graph-generation steps. The central issue was candidate admissibility, not a complete absence of edge-generation attempts.

### 3.2 Accepted semantic outputs

All eight accepted semantic outputs contain an empty list:

```text
semantic_step_0001.json: 0 edges
semantic_step_0002.json: 0 edges
semantic_step_0003.json: 0 edges
semantic_step_0004.json: 0 edges
semantic_step_0005.json: 0 edges
semantic_step_0006.json: 0 edges
semantic_step_0007.json: 0 edges
semantic_step_0008.json: 0 edges
```

These files are stored under:

```text
mllm_raw_outputs_smoke_QwenThinkingRelaxedNewEdgesV2/
  RPmz2sHmrrY_case_0030/
```

### 3.3 Materialized graph outputs

The nine hypothesis snapshots contain increasing numbers of grounded navigation edges but zero ungrounded edges:

| Snapshot | All graph edges | Ungrounded edges |
|---:|---:|---:|
| 1 | 9 | 0 |
| 2 | 19 | 0 |
| 3 | 33 | 0 |
| 4 | 44 | 0 |
| 5 | 57 | 0 |
| 6 | 70 | 0 |
| 7 | 79 | 0 |
| 8 | 87 | 0 |
| 9 | 93 | 0 |

The additional graph edges are measured navigation edges revealed as agents move. They are grounded and therefore are not MLLM-generated uncertain edges.

## 4. Concrete evidence of malformed Qwen edge objects

The corrected V2 run saved only the repaired accepted payload, so it did not retain the 22 unrepaired edge objects. However, rejected responses from the first smoke attempt preserve concrete examples of Qwen's edge serialization.

One response used:

```json
{"viewpoint_node_indices": [3, 16], "exist_prob": 0.6}
```

Another used:

```json
{
  "source_viewpoint_id": 3,
  "target_viewpoint_id": 16,
  "exist_prob": 0.8
}
```

Both forms violate the required schema:

- `i` is missing;
- `j` is missing;
- `edge_type` is missing;
- `dist` is missing;
- one response introduces `viewpoint_node_indices`;
- the other introduces `source_viewpoint_id` and `target_viewpoint_id`.

These examples are preserved in:

- `mllm_raw_outputs_smoke_QwenThinkingRelaxedNewEdges/RPmz2sHmrrY_case_0030/semantic_step_0001_attempt_01_error.txt`;
- `mllm_raw_outputs_smoke_QwenThinkingRelaxedNewEdges/RPmz2sHmrrY_case_0030/semantic_step_0001_attempt_05_error.txt`.

They establish schema noncompliance as a real failure mode. They do not, however, prove that all 22 V2 candidates failed for exactly the same reason, because the V2 pre-repair edge objects were not persisted.

## 5. Root-cause assessment

### 5.1 Confirmed cause: candidates violated remaining admissibility checks

The V2 logger confirms that 22 model-proposed optional edges were classified as illegal by the unchanged repair filter. This is the direct reason all accepted payloads saved empty edge lists.

### 5.2 Confirmed contributing failure mode: schema noncompliance

Retained Qwen responses demonstrate that the model sometimes used alternative endpoint fields and omitted mandatory attributes. Because `dist` is part of the edge hypothesis being evaluated, filling it automatically would fabricate a prediction and invalidate Edge-JNLL.

### 5.3 Not a remaining temporal-eligibility failure

The corrected implementation synthesizes an eligible prior status for a newly observed endpoint, and the regression test proves that a well-formed first-step edge passes under the relaxed variant. The earlier `KeyError: 'prior_grounded'` was fixed before the V2 run and did not recur.

### 5.4 Not an optimizer failure

Gurobi solved every completed planning step. The optimizer received graphs containing grounded navigation edges but no uncertain MLLM-generated edges. It could not use edges that had already been removed upstream.

### 5.5 Not evidence that no plausible edge existed

The experiment does not establish whether the rejected candidate endpoint pairs corresponded to true traversable connections. The pre-repair V2 candidates and their rejection reasons were not retained, preventing oracle comparison. The correct conclusion is “no admissible saved prediction,” not “no plausible topological shortcut existed.”

## 6. Why Edge-JNLL remains unavailable

Edge-JNLL requires, for each saved ungrounded prediction:

- endpoint IDs;
- predicted existence probability;
- predicted distance mean;
- predicted distance variance;
- oracle edge-existence label;
- oracle distance when the edge exists.

After repair, the V2 run contained zero ungrounded predictions. Consequently, the Edge-JNLL candidate set is empty. Reporting a score of zero would incorrectly imply perfect edge prediction. The correct report value is `N/A`.

The same condition holds for the original Qwen-Thinking case, so the experiment cannot compare Edge-JNLL numerically.

## 7. Experimental implications

### 7.1 Effectiveness and efficiency

The relaxed run internally found all targets, but it did not benefit from uncertain-edge shortcuts because none entered the graph. Relative to the original run, it had:

- slightly higher PWGS: `0.626 -> 0.652`;
- lower oracle-verified progress: `0.625 -> 0.500`;
- lower Team-PPL-total: `0.364 -> 0.209`;
- lower Team-PPL-makespan: `0.481 -> 0.313`;
- greater total travel: `20.343 m -> 28.398 m`;
- more steps: `7 -> 10`.

These values do not support an efficiency or overall effectiveness improvement in this episode.

### 7.2 Causal limitation

The two runs did not produce identical step-1 detector outputs even though their initial panoramas were identical. This shows detector stochasticity before route divergence. Therefore, differences in route metrics cannot be attributed solely to the edge-prompt relaxation. The result should be presented as a diagnostic failure analysis, not as a controlled causal ablation.

### 7.3 Scope limitation

Only one preselected three-agent episode was tested. The observation that no candidate survived in this case does not establish a population-level failure rate. A paper-wide conclusion would require multiple fixed cases or seeds with controlled detection outputs.

## 8. Recommended reporting language

### 8.1 Copy-ready implementation paragraph

> We additionally evaluated a relaxed edge-eligibility variant in which a non-current viewpoint first observed at the current step could immediately serve as an uncertain edge endpoint. For a newly observed viewpoint absent from the prior graph, the evaluator initialized its prior state as ungrounded and unvisited, while retaining all other structural requirements, including the exact edge schema, viewpoint-type constraint, current-viewpoint exclusion, and positive distance prediction.

### 8.2 Copy-ready failure-analysis paragraph

> In the examined three-agent episode, the relaxed eligibility rule did not produce a materialized uncertain edge. Qwen proposed 22 optional edge candidates across six planning steps, but every candidate was removed by the unchanged structural repair rules before graph update; accordingly, all accepted semantic outputs contained an empty `new_edges` list and all saved hypothesis snapshots contained zero ungrounded edges. Retained rejected responses reveal a recurring schema-compliance failure in which the model used alternative endpoint fields and omitted the required edge type and distance. Because the corrected run retained only aggregate rejection counts rather than unrepaired edge objects, we cannot assign a precise rejection category to every candidate. We therefore report Edge-JNLL as unavailable rather than zero.

### 8.3 Copy-ready interpretation paragraph

> This result indicates that relaxing endpoint timing is necessary but not sufficient for producing usable structural hypotheses. The intervention expanded the set of eligible endpoints, but useful edge generation still depended on exact structured-output compliance and satisfaction of the remaining topology constraints. The episode showed a small increase in PWGS but worse verified progress and route-efficiency metrics. Moreover, the detector outputs differed at the initial step, so the observed route deltas cannot be causally attributed to the graph-prompt change alone.

### 8.4 Suggested table note

> `--` denotes that Edge-JNLL is not estimable because no ungrounded edge prediction survived schema repair and structural validation. It does not denote zero error.

## 9. Recommended follow-up experiment

A valid follow-up should preserve the same algorithmic constraints while improving observability and output-contract compliance:

1. Create another separate prompt variant that repeats the exact five-field `new_edges` schema immediately beside the relaxation instruction.
2. Require a positive `dist` for every candidate and explicitly forbid alternative endpoint-field names.
3. Save the raw pre-repair payload for every accepted response.
4. Save a per-edge rejection record with mutually exclusive reason codes, such as:
   - `schema_keys`;
   - `non_vv_type`;
   - `self_edge`;
   - `endpoint_not_currently_visible`;
   - `current_viewpoint_endpoint`;
   - `missing_status`;
   - `grounded_endpoint`;
   - `visited_endpoint`.
5. Report four counts separately: proposed, schema-valid, structurally valid, and materialized edges.
6. Hold the detector outputs fixed when the initial observations are identical, or evaluate multiple detector seeds, so the prompt ablation is causally interpretable.
7. Evaluate several frozen multi-agent cases rather than drawing a conclusion from one episode.

This follow-up should not infer missing distances, rename malformed fields automatically, or insert edges post hoc. Those operations would change the model prediction rather than evaluate it.

## 10. Claim--evidence map

| Claim | Evidence | Status |
|---|---|---|
| Newly observed viewpoints became immediately eligible endpoints. | Relaxed helper at `mllm_client.py:3639--3655`; focused first-step regression test. | Supported |
| Qwen attempted to generate uncertain edges in the V2 episode. | Aggregate repair log: 22 candidates removed across six steps. | Supported |
| No uncertain edge entered the saved graph. | Eight accepted semantic files with zero `new_edges`; nine snapshots with zero ungrounded edges. | Supported |
| Schema noncompliance occurred. | Preserved responses using `viewpoint_node_indices` or source/target fields and omitting `dist`. | Supported |
| Every V2 candidate failed specifically because of schema keys. | V2 pre-repair objects and per-edge reasons were not persisted. | Not supported |
| The temporal relaxation improved route efficiency. | Higher distance, more steps, and lower Team-PPL in this episode. | Contradicted for this episode |
| The temporal relaxation generally provides no benefit. | Only one stochastic episode was run. | Needs broader evidence |

## 11. Adversarial self-review

### Contribution

- Does the text distinguish the endpoint-timing contribution from unrelated schema requirements? **Yes.**
- Does it avoid claiming that the temporal relaxation itself failed to activate? **Yes.**

### Writing clarity

- Are “proposed,” “retained,” and “materialized” edges defined separately? **Yes.**
- Is `N/A` distinguished from a perfect zero Edge-JNLL? **Yes.**

### Experimental strength

- Is the one-case scope disclosed? **Yes.**
- Is detector stochasticity disclosed as a causal confound? **Yes.**

### Evaluation completeness

- Are aggregate candidate counts, accepted-edge counts, and materialized-edge counts reported? **Yes.**
- Are exact V2 per-edge rejection reasons available? **No; this is explicitly identified as missing evidence.**

### Method-design soundness

- Does the report recommend weakening structural validity merely to obtain nonempty results? **No.**
- Does the follow-up preserve general validation rather than introducing heuristic edge reconstruction? **Yes.**

