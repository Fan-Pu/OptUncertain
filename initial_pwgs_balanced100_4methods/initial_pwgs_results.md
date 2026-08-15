# Initial-PWGS results

Only saved step-1 hypotheses are evaluated. A case--target query is included only when the target remains active in all four methods, giving identical query support.

| Method | Single-agent Initial-PWGS $\uparrow$ | Multi-agent Initial-PWGS $\uparrow$ |
|---|---:|---:|
| GPT-Medium | 0.518 | 0.652 |
| Qwen-Thinking | 0.501 | 0.589 |
| Qwen-Instant | 0.503 | 0.557 |
| Gemma-Instant | 0.479 | 0.603 |

Support: 33/34 single-agent cases and 53/66 multi-agent cases. Targets are averaged within cases, followed by an unweighted average across cases.

An empty model-generated location distribution receives zero. Saved targets already marked found by at least one method are excluded for every method because no matched four-method hypothesis query exists.

## Copy-ready LaTeX

```latex
\begin{table}[tbp]
\centering
\caption{Initial target-location hypothesis quality on matched step-1 case--target queries. Higher is better.}
\label{tab:initial_pwgs}
\begin{tabular}{lcc}
\toprule
Method & Single agent & Multi agent \\
\midrule
GPT-Medium & 0.518 & 0.652 \\
Qwen-Thinking & 0.501 & 0.589 \\
Qwen-Instant & 0.503 & 0.557 \\
Gemma-Instant & 0.479 & 0.603 \\
\bottomrule
\end{tabular}
\end{table}
```

## Audit

- Frozen manifest hash: `ec14c3efdcc190d8a3872e0f22cd89a9481485498a7fa1794610f043dd02a7e5`.
- Step-1 `target_found` disagreements across methods: 42.
- Zero-scored empty distributions by method: `{'GPT-Medium': 0, 'Qwen-Thinking': 0, 'Qwen-Instant': 0, 'Gemma-Instant': 3}`.
