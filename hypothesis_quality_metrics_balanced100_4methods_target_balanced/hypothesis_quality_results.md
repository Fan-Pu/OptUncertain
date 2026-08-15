# Hypothesis-quality results

## Result

Target-balanced PWGS (TB-PWGS) is reported on the common evaluable support: 30/34 single-agent episodes and 53/66 multi-agent episodes. For each episode, active target--time scores are first averaged over time within each target and then equally across evaluable targets. The table finally gives an unweighted mean across episodes.

| Method | Single-agent TB-PWGS $\uparrow$ | Multi-agent TB-PWGS $\uparrow$ | Single-agent pooled PWGS $\uparrow$ | Multi-agent pooled PWGS $\uparrow$ |
|---|---:|---:|---:|---:|
| GPT-Medium | 0.601 | 0.697 | 0.572 | 0.684 |
| Qwen-Thinking | 0.590 | 0.629 | 0.559 | 0.631 |
| Qwen-Instant | 0.568 | 0.596 | 0.540 | 0.601 |
| Gemma-Instant | 0.580 | 0.636 | 0.568 | 0.633 |

Edge-JNLL is unavailable, rather than zero: every readable saved `hypothesis_step` contains zero ungrounded edges, and every raw semantic response for all four methods has `new_edges: []`. The required last-ungrounded prediction therefore does not exist.

## Copy-ready LaTeX

```latex
\begin{table}[tbp]
\centering
\caption{Target-location hypothesis quality on the common evaluable subset. Higher values are better.}
\label{tab:target_balanced_pwgs}
\begin{tabular}{lcccc}
\toprule
& \multicolumn{2}{c}{TB-PWGS} & \multicolumn{2}{c}{Pooled PWGS} \\
\cmidrule(lr){2-3}\cmidrule(lr){4-5}
Method & Single & Multi & Single & Multi \\
\midrule
GPT-Medium & 0.601 & 0.697 & 0.572 & 0.684 \\
Qwen-Thinking & 0.590 & 0.629 & 0.559 & 0.631 \\
Qwen-Instant & 0.568 & 0.596 & 0.540 & 0.601 \\
Gemma-Instant & 0.580 & 0.636 & 0.568 & 0.633 \\
\bottomrule
\end{tabular}
\par\smallskip
\parbox{\columnwidth}{\footnotesize Both aggregations use 30/34 single-agent episodes and 53/66 multi-agent episodes for which all four methods contain an evaluable saved target distribution. TB-PWGS first averages over time within each target, then targets within each episode, and finally episodes.}
\end{table}
```

## Computation and caveats

- For every active target at every saved hypothesis state, the evaluator uses only eligible viewpoints: viewpoint nodes that are ungrounded, unvisited, and not occupied by an agent.
- Saved nonempty distributions must sum to one within an absolute serialization tolerance of $10^{-6}$. They are never renormalized by the evaluator.
- An episode that finishes before a nonempty target hypothesis exists is not applicable; it is not assigned PWGS $=1$.
- TB-PWGS computes a temporal mean for every target with at least one valid target--time score, gives those evaluable targets equal weight within the episode, and then gives episodes equal weight within the single- or multi-agent group.
- TB-PWGS is still an on-policy diagnostic because the four methods save hypotheses along different executed trajectories. Target balancing removes duration-based target weights, while common episode support removes missing-episode imbalance; neither makes the target--time contexts identical.
- Geodesics are computed on the complete weighted connectivity graph. If an included Matterport viewpoint is disconnected from every oracle-detectable viewpoint, it is outside that target's evaluable navigation component and is disclosed in the JSON audit; any saved eligible hypothesis on such a viewpoint would fail evaluation.
- Edge-JNLL must use the final saved `grounded=false` prediction for an edge and ignore a later grounded replacement. No such predictions are present in these runs.

## Artifact audit

- Invalid saved snapshot: `/workspace/OptUncertain/mllm_debug_outputs_balanced100_GPT54Medium/zsNo4HB9uLZ_case_0001/hypothesis_step_0009.json` (0 bytes). Its episode was excluded through the common-support rule; the file was not repaired or overwritten.
- Invalid target--time distribution: `/workspace/OptUncertain/mllm_debug_outputs_balanced100_Gemma431BThinking/zsNo4HB9uLZ_case_0013/hypothesis_step_0004.json`, target `0` (Saved PWGS probabilities sum to 0.75, not one; refusing to renormalize malformed data.). That target--time record was excluded without renormalization; other valid records in its episode remain evaluable.
- Invalid target--time distribution: `/workspace/OptUncertain/mllm_debug_outputs_balanced100_Gemma431BThinking/zsNo4HB9uLZ_case_0013/hypothesis_step_0004.json`, target `4` (Saved PWGS probabilities sum to 0.75, not one; refusing to renormalize malformed data.). That target--time record was excluded without renormalization; other valid records in its episode remain evaluable.
- Invalid target--time distribution: `/workspace/OptUncertain/mllm_debug_outputs_balanced100_Gemma431BThinking/zsNo4HB9uLZ_case_0013/hypothesis_step_0004.json`, target `6` (Saved PWGS probabilities sum to 0.75, not one; refusing to renormalize malformed data.). That target--time record was excluded without renormalization; other valid records in its episode remain evaluable.
- Invalid target--time distribution: `/workspace/OptUncertain/mllm_debug_outputs_balanced100_Gemma431BThinking/zsNo4HB9uLZ_case_0013/hypothesis_step_0004.json`, target `7` (Saved PWGS probabilities sum to 0.69230769230769229, not one; refusing to renormalize malformed data.). That target--time record was excluded without renormalization; other valid records in its episode remain evaluable.

## Claim--evidence map

- The TB-PWGS and pooled PWGS values come from `summary_hypothesis_metrics.csv`; episode-level values are in `case_hypothesis_metrics.csv`, and target-level temporal means are in `target_hypothesis_metrics.csv`.
- Manifest hashes, malformed artifacts, exclusions, empty-support states, and edge-candidate counts are recorded in `hypothesis_metric_audit.json`.
- No API call, benchmark execution, cache mutation, or artifact repair is part of this evaluator.

## Self-review

- Metric direction and averaging order are stated explicitly.
- Missing hypotheses are separated from numeric performance.
- The unavailable Edge-JNLL is shown as `--`, not as a favorable zero.
- Precision beyond three decimals remains available in the raw CSV output.
