# Qwen-Thinking relaxed new-edge prompt: one-case comparison

This is a controlled diagnostic on the frozen three-agent case `RPmz2sHmrrY_case_0030`. It is not sufficient for a paper-wide claim about effectiveness or efficiency.

| Variant | Internal outcome | Verified success | Verified progress | Team-PPL-total | Team-PPL-makespan | Total distance (m) | Max-agent distance (m) | Steps | F1 | PWGS | New edges | Edge-JNLL |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Original Qwen-Thinking | completed / all_targets_found | 0.000 | 0.625 | 0.364 | 0.481 | 20.343 | 8.254 | 7 | 0.667 | 0.626 | 0 | -- |
| Relaxed new-edge prompt | completed / all_targets_found | 0.000 | 0.500 | 0.209 | 0.313 | 28.398 | 10.164 | 10 | 0.400 | 0.652 | 0 | -- |

The internal outcome is based on the online detector's target state. Verified success and progress independently check the recorded found viewpoints against oracle-detectable viewpoints; an internally completed route can therefore have verified success equal to zero.

## Relaxed minus original

| Metric | Difference | Better direction |
|---|---:|---|
| verified success | 0.000 | higher is better |
| progress | -0.125 | higher is better |
| team ppl total | -0.156 | higher is better |
| team ppl makespan | -0.169 | higher is better |
| pwgs | 0.026 | higher is better |
| steps completed | 3.000 | lower is better |
| total distance | 8.055 | lower is better |
| maximum agent distance | 1.911 | lower is better |

## Edge audit

The relaxed run produced 0 last-ungrounded edge prediction(s) available for Edge-JNLL.
The original run has no ungrounded edge prediction, so its Edge-JNLL remains `--`; the two variants therefore do not have a directly comparable Edge-JNLL pair.

## Interpretation

The step-1 detection outputs do not match. Because the initial panoramas are identical, this is detector stochasticity before the routes diverge. The observed route/effectiveness differences therefore cannot be attributed solely to the graph-prompt change.

A benefit is supported for this case only if the relaxed row improves the task/route metrics in their stated directions. Even then, a single stochastic episode is an ablation example, not evidence of an average improvement over the 100-case set.

## Claim--evidence map

- Claim: the relaxed contract can create usable uncertain edges. | Evidence: saved `new_edges`, last-ungrounded snapshots, and `edge_predictions.csv`. | Status: not supported in this run.
- Claim: relaxation improves this episode's effectiveness. | Evidence: success, progress, and PWGS relative to the original row. | Status: case-specific only.
- Claim: relaxation improves this episode's efficiency. | Evidence: Team-PPL, total distance, maximum-agent distance, and steps. | Status: case-specific only.
- Claim: relaxation generally improves the proposed method. | Evidence: one episode. | Status: needs a multi-seed or full-sample ablation.

## Self-review

- The comparison uses the same frozen case, Qwen-Thinking model configuration, detector family, optimization parameters, and 30-step budget.
- Detection F1 is reported only as an on-policy diagnostic because the variants may execute different routes.
- Edge-JNLL is not imputed for the original run.
- No population-level claim is made from one case.
