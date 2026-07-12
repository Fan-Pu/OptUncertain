# OptUncertain

This repository now implements the paper-style shared multi-agent, multi-target rolling-horizon pipeline:

- one annotated panorama image per agent is sent to the MLLM at each step
- all agents share one persistent hypothesis graph
- target probabilities are tracked per target on both viewpoint and region layers
- region existence, edge distance, and edge existence are updated with the paper's Bayesian rules
- planning is solved as a joint multi-agent MILP with target uniqueness across agents

## Runtime

Run the entrypoint with a JSON scenario file:

```bash
python main.py scenarios/test6.json
```

Shared MLLM, Bayes, and optimizer settings are read from
`config/default_config.json`. Per-scenario output directories are inferred from
the scenario filename, for example `scenarios/test6.json` writes to
`mllm_raw_outputs/test6` and `mllm_debug_outputs/test6`.

## Scenario Schema

Single-test scenario files contain only scan, agent, and target definitions:

```json
{
  "scan_id": "2azQ1b91cZZ",
  "agents": [
    {
      "id": "agent0",
      "start_viewpoint_id": "3fb5a48d8a71413aacaa51f6bc569e59",
      "heading": 0.0,
      "elevation": 0.0
    }
  ],
  "targets": [
    {
      "target_id": "0",
      "description": "the car brochure in the small storage room beyond the circular floor pattern across the formal living room"
    }
  ]
}
```

The central config contains:

```json
{
  "mllm": {
    "detection_model_name": "google/gemma-4-31B-it:deepinfra",
    "graph_model_name": "qwen3.5-plus",
    "read_saved_raw_outputs": true,
    "max_validation_retries": 4
  },
  "bayes": {
    "sigma_vv2": 4.0,
    "kappa_vv": 1.0,
    "varrho": 0.75,
    "epsilon": 1e-6
  },
  "optimizer": {
    "goal_weight": 0.5,
    "dist_weight": 0.2,
    "arc_weight": 0.05,
    "node_weight": 0.05,
    "visit_weight": 0.2
  }
}
```

Batch scenario files contain `scans`, `agent_num_selections`, and
`target_num_selections`, with optional `max_steps` applied to each generated
case. Batch mode generates concrete cases grouped by scan id, writes
`mllm_debug_outputs/<batch_name>/generated_cases.json`, and runs each generated
case using the same central config. Agent starts and targets are sampled without
replacement; the run fails if a requested count exceeds the available viewpoints
or listed targets for a scan. When a generated case reaches `max_steps`, its
logs and route summary are saved with `stop_reason: "max_steps"` and the batch
runner continues to the next case. Batch cases that stop with incomplete status,
including `max_steps` and `mllm_retry_exhausted`, are recorded incrementally in
`mllm_debug_outputs/<batch_name>/skipped_cases.json`. If an API provider reports
credit, balance, billing, or quota exhaustion, batch mode writes
`batch_termination.json`, updates `batch_progress.json`, and stops. Re-running
the same batch config resumes from the terminated case using the saved
`generated_cases.json`; changing the batch config requires deleting the old
generated batch output.

## Dependencies

The MLLM client uses OpenAI-compatible APIs. The runtime currently routes
detection through Hugging Face (`HF_TOKEN`) and graph generation through
DashScope (`DASHSCOPE_API_KEY`) in `main.py`.

The optimizer requires `gurobipy` and a working Gurobi license.

## Training-Free Benchmarks

Install the VLFM-G assignment dependency inside the runtime environment:

```bash
python3 -m pip install -r requirements-benchmarks.txt
```

VLFM-G uses the official `Salesforce/blip2-itm-vit-g` checkpoint pinned in
`config/default_config.json`. The checkpoint is approximately 4.69 GB and is
downloaded by Transformers on the first semantic cache miss. The implementation
does not substitute another encoder when the checkpoint cannot be loaded.

Calibrate VLFM-G on the deterministic 20-case held-out set, then run both
benchmarks on the exact completed GPT54Medium 100-case sample:

```bash
python3 run_benchmark_sweep.py --batch-config scenarios/batch_test.json --method vlfm_g --calibrate
python3 run_benchmark_sweep.py --batch-config scenarios/batch_test.json --method vlfm_g
python3 run_benchmark_sweep.py --batch-config scenarios/batch_test.json --method mllm_direct
```

The final output roots are `mllm_debug_outputs_balanced100_VLFMG` and
`mllm_debug_outputs_balanced100_MLLMDirect_GPT54Medium`. Both methods reuse the
shared GPT5.4 detection cache. MLLM-Direct action calls use GPT54Medium in
standard service tier; detection calls retain flex tier.

After both 100-case runs finish, add them to the existing comparison:

```bash
python3 evaluate_batch_metrics.py \
  --batch-config scenarios/batch_test.json \
  --generated-cases mllm_debug_outputs_balanced100_GPT54Medium/batch_test/sampled_generated_cases.json \
  --oracle-summaries mllm_debug_outputs_balanced100_GPT54Medium/batch_test/oracle_summaries.json \
  --method GPT54Medium=mllm_debug_outputs_balanced100_GPT54Medium \
  --method Gemma431BThinking=mllm_debug_outputs_balanced100_Gemma431BThinking \
  --method Qwen36_35BA3BThinking=mllm_debug_outputs_balanced100_Qwen36_35BA3BThinking \
  --method Qwen36_35BA3BInstant=mllm_debug_outputs_balanced100_Qwen36_35BA3BInstant \
  --method VLFM-G=mllm_debug_outputs_balanced100_VLFMG \
  --method MLLM-Direct=mllm_debug_outputs_balanced100_MLLMDirect_GPT54Medium \
  --out mllm_debug_outputs_balanced100_GPT54Medium/batch_test/metrics_all_methods_with_benchmarks
```
