# Hypothesis-quality results

## Result

Geodesic NDCG@5 and PWGS are reported on the common evaluable support: 30/34 single-agent episodes and 53/66 multi-agent episodes. Each episode first averages its active target--time scores; the table then gives an unweighted mean across episodes.

| Method | Single-agent G-NDCG@5 $\uparrow$ | Multi-agent G-NDCG@5 $\uparrow$ | Single-agent PWGS $\uparrow$ | Multi-agent PWGS $\uparrow$ | Edge-JNLL $\downarrow$ |
|---|---:|---:|---:|---:|---:|
| GPT-Medium | 0.863 | 0.833 | 0.572 | 0.684 | -- |
| Qwen-Thinking | 0.863 | 0.790 | 0.559 | 0.631 | -- |
| Qwen-Instant | 0.853 | 0.755 | 0.540 | 0.601 | -- |
| Gemma-Instant | 0.884 | 0.790 | 0.568 | 0.633 | -- |

Edge-JNLL is unavailable, rather than zero: every readable saved `hypothesis_step` contains zero ungrounded edges, and every raw semantic response for all four methods has `new_edges: []`. The required last-ungrounded prediction therefore does not exist.

## Copy-ready LaTeX

```latex
\begin{table}[tbp]
\centering
\caption{Hypothesis-quality metrics on the common evaluable subset. Higher values are better.}
\label{tab:hypothesis_quality_common}
\begin{tabular}{lcccc}
\toprule
& \multicolumn{2}{c}{G-NDCG@5} & \multicolumn{2}{c}{PWGS} \\
\cmidrule(lr){2-3}\cmidrule(lr){4-5}
Method & Single & Multi & Single & Multi \\
\midrule
GPT-Medium & 0.863 & 0.833 & 0.572 & 0.684 \\
Qwen-Thinking & 0.863 & 0.790 & 0.559 & 0.631 \\
Qwen-Instant & 0.853 & 0.755 & 0.540 & 0.601 \\
Gemma-Instant & 0.884 & 0.790 & 0.568 & 0.633 \\
\bottomrule
\end{tabular}
\par\smallskip
\parbox{\columnwidth}{\footnotesize Both metrics use 30/34 single-agent episodes and 53/66 multi-agent episodes for which all four methods contain an evaluable saved target distribution. G-NDCG@5 ranks eligible viewpoints by predicted target probability and uses normalized geodesic proximity as relevance.}
\end{table}
```

## Computation and caveats

- For every active target at every saved hypothesis state, the evaluator uses only eligible viewpoints: viewpoint nodes that are ungrounded, unvisited, and not occupied by an agent.
- Saved nonempty distributions must sum to one within an absolute serialization tolerance of $10^{-6}$. They are never renormalized by the evaluator.
- An episode that finishes before a nonempty target hypothesis exists is not applicable; it is not assigned PWGS $=1$.
- For G-NDCG@5, the relevance of viewpoint $v$ is $1-d(v,\mathcal{O}_t)/D_t^{\max}$, where $d(v,\mathcal{O}_t)$ is its shortest-path distance to the nearest oracle-detectable viewpoint and $D_t^{\max}$ is the maximum finite such distance in the scan. DCG ranks viewpoints by saved target probability; IDCG ranks the same eligible viewpoints by relevance. Exact probability ties use their expected DCG under uniform tie-breaking, so viewpoint identifiers cannot determine the score.
- PWGS and G-NDCG@5 are on-policy diagnostics because the four methods save hypotheses along different executed trajectories. Common episode support removes missing-episode imbalance, but it does not make their target--time query sets identical.
- Geodesics are computed on the complete weighted connectivity graph. If an included Matterport viewpoint is disconnected from every oracle-detectable viewpoint, it is outside that target's evaluable navigation component and is disclosed in the JSON audit; any saved eligible hypothesis on such a viewpoint would fail evaluation.
- Edge-JNLL must use the final saved `grounded=false` prediction for an edge and ignore a later grounded replacement. No such predictions are present in these runs.

## Artifact audit

- Invalid saved snapshot: `/workspace/OptUncertain/mllm_debug_outputs_balanced100_GPT54Medium/zsNo4HB9uLZ_case_0001/hypothesis_step_0009.json` (0 bytes). Its episode was excluded through the common-support rule; the file was not repaired or overwritten.
- Invalid target--time distribution: `/workspace/OptUncertain/mllm_debug_outputs_balanced100_Gemma431BThinking/zsNo4HB9uLZ_case_0013/hypothesis_step_0004.json`, target `0` (Saved PWGS probabilities sum to 0.75, not one; refusing to renormalize malformed data.). That target--time record was excluded without renormalization; other valid records in its episode remain evaluable.
- Invalid target--time distribution: `/workspace/OptUncertain/mllm_debug_outputs_balanced100_Gemma431BThinking/zsNo4HB9uLZ_case_0013/hypothesis_step_0004.json`, target `4` (Saved PWGS probabilities sum to 0.75, not one; refusing to renormalize malformed data.). That target--time record was excluded without renormalization; other valid records in its episode remain evaluable.
- Invalid target--time distribution: `/workspace/OptUncertain/mllm_debug_outputs_balanced100_Gemma431BThinking/zsNo4HB9uLZ_case_0013/hypothesis_step_0004.json`, target `6` (Saved PWGS probabilities sum to 0.75, not one; refusing to renormalize malformed data.). That target--time record was excluded without renormalization; other valid records in its episode remain evaluable.
- Invalid target--time distribution: `/workspace/OptUncertain/mllm_debug_outputs_balanced100_Gemma431BThinking/zsNo4HB9uLZ_case_0013/hypothesis_step_0004.json`, target `7` (Saved PWGS probabilities sum to 0.69230769230769229, not one; refusing to renormalize malformed data.). That target--time record was excluded without renormalization; other valid records in its episode remain evaluable.

## Claim--evidence map

- The G-NDCG@5 and PWGS values come from `summary_hypothesis_metrics.csv`; episode-level scores and support counts are in `case_hypothesis_metrics.csv`.
- Manifest hashes, malformed artifacts, exclusions, empty-support states, and edge-candidate counts are recorded in `hypothesis_metric_audit.json`.
- No API call, benchmark execution, cache mutation, or artifact repair is part of this evaluator.

## Self-review

- Metric direction and averaging order are stated explicitly.
- Missing hypotheses are separated from numeric performance.
- The unavailable Edge-JNLL is shown as `--`, not as a favorable zero.
- Precision beyond three decimals remains available in the raw CSV output.
