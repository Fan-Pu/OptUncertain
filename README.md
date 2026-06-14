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
    "sigma_vz2": 9.0,
    "kappa_vv": 1.0,
    "kappa_vz": 1.0,
    "varrho": 0.75,
    "eta_vz": 5.0,
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

SigLIP scoring requires:

```bash
pip install torch transformers
```

The MLLM client uses OpenAI-compatible APIs. The runtime currently routes
detection through Hugging Face (`HF_TOKEN`) and graph generation through
DashScope (`DASHSCOPE_API_KEY`) in `main.py`.

The optimizer requires `gurobipy` and a working Gurobi license.
