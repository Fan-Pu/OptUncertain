# Common-Support Performance Metrics

All task metrics and Target-Balanced PWGS (TB-PWGS) below use the identical PWGS-evaluable case set for every method.

- Single-agent common support: 30/34 cases.
- Multi-agent common support: 53/66 cases.
- Progress and both Team-PPL variants are equal-weight episode means.
- F1 is micro-aggregated after summing TP, FP, and FN over the matched cases.
- TB-PWGS averages over time within each target, then equally over targets within each episode, and finally equally over episodes.

## Single-agent results

| Method | Cases | Progress ↑ | Team-PPL Total ↑ | Team-PPL Makespan ↑ | F1 ↑ | TB-PWGS ↑ |
|---|---:|---:|---:|---:|---:|---:|
| GPT-Medium | 30 | 0.271 | 0.172 | 0.172 | 0.332 | 0.601 |
| Qwen-Thinking | 30 | 0.275 | 0.146 | 0.146 | 0.330 | 0.590 |
| Qwen-Instant | 30 | 0.271 | 0.142 | 0.142 | 0.388 | 0.568 |
| Gemma-Instant | 30 | 0.217 | 0.164 | 0.164 | 0.310 | 0.580 |

### Single-agent travel distances

| Method | Mean total distance (m) ↓ | Mean maximum-agent distance (m) ↓ |
|---|---:|---:|
| GPT-Medium | 43.020 | 43.020 |
| Qwen-Thinking | 46.352 | 46.352 |
| Qwen-Instant | 47.589 | 47.589 |
| Gemma-Instant | 31.016 | 31.016 |

## Multi-agent results

| Method | Cases | Progress ↑ | Team-PPL Total ↑ | Team-PPL Makespan ↑ | F1 ↑ | TB-PWGS ↑ |
|---|---:|---:|---:|---:|---:|---:|
| GPT-Medium | 53 | 0.500 | 0.129 | 0.267 | 0.449 | 0.697 |
| Qwen-Thinking | 53 | 0.465 | 0.133 | 0.290 | 0.431 | 0.629 |
| Qwen-Instant | 53 | 0.474 | 0.105 | 0.244 | 0.379 | 0.596 |
| Gemma-Instant | 53 | 0.467 | 0.102 | 0.233 | 0.401 | 0.636 |

### Multi-agent travel distances

| Method | Mean total distance (m) ↓ | Mean maximum-agent distance (m) ↓ |
|---|---:|---:|
| GPT-Medium | 38.631 | 13.080 |
| Qwen-Thinking | 41.249 | 13.545 |
| Qwen-Instant | 52.787 | 17.130 |
| Gemma-Instant | 48.193 | 15.529 |

## Copy-ready LaTeX

```latex
\begin{table}[t]
\centering
\caption{Performance on the common 30 single-agent test cases. All metrics are computed on identical cases.}
\label{tab:common_single_metrics}
\begin{tabular}{lccccc}
\toprule
Method & Progress & \multicolumn{2}{c}{Team-PPL} & F1 & TB-PWGS \\
\cmidrule(lr){3-4}
 & & Total & Makespan & & \\
\midrule
GPT-Medium & 0.271 & 0.172 & 0.172 & 0.332 & 0.601 \\
Qwen-Thinking & 0.275 & 0.146 & 0.146 & 0.330 & 0.590 \\
Qwen-Instant & 0.271 & 0.142 & 0.142 & 0.388 & 0.568 \\
Gemma-Instant & 0.217 & 0.164 & 0.164 & 0.310 & 0.580 \\
\bottomrule
\end{tabular}
\end{table}

\begin{table}[t]
\centering
\caption{Performance on the common 53 multi-agent test cases. All metrics are computed on identical cases.}
\label{tab:common_multi_metrics}
\begin{tabular}{lccccc}
\toprule
Method & Progress & \multicolumn{2}{c}{Team-PPL} & F1 & TB-PWGS \\
\cmidrule(lr){3-4}
 & & Total & Makespan & & \\
\midrule
GPT-Medium & 0.500 & 0.129 & 0.267 & 0.449 & 0.697 \\
Qwen-Thinking & 0.465 & 0.133 & 0.290 & 0.431 & 0.629 \\
Qwen-Instant & 0.474 & 0.105 & 0.244 & 0.379 & 0.596 \\
Gemma-Instant & 0.467 & 0.102 & 0.233 & 0.401 & 0.636 \\
\bottomrule
\end{tabular}
\end{table}
```
