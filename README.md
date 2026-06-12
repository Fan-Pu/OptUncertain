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
python main.py scenarios/paper_multi_agent_example.json
```

## Scenario Schema

The scenario file must contain:

```json
{
  "scan_id": "17DRP5sb8fy",
  "agents": [
    {
      "id": "agent0",
      "start_viewpoint_id": "10c252c90fa24ef3b698c6f54d984c5c",
      "heading": 0.0,
      "elevation": 0.0
    }
  ],
  "targets": [
    {
      "description": "green plant on the table",
      "distance_threshold_m": 1.0
    }
  ],
  "mllm": {
    "model_name": "meta-llama/Llama-4-Maverick-17B-128E-Instruct:cheapest",
    "max_new_tokens": 160,
    "base_url": "https://api.deepinfra.com/v1/openai",
    "graph_base_url": "https://api.deepinfra.com/v1/openai",
    "detection_base_url": "https://api.deepinfra.com/v1/openai",
    "api_key_env": "DEEPINFRA_TOKEN",
    "graph_api_key_env": "DEEPINFRA_TOKEN",
    "detection_api_key_env": "DEEPINFRA_TOKEN",
    "read_saved_raw_outputs": false,
    "raw_output_dir": "mllm_raw_outputs",
    "open_vocab_verification": {
      "enabled": true,
      "model_name": "google/owlv2-base-patch16-ensemble",
      "score_threshold": 0.15,
      "device": "cuda"
    }
  },
  "bayes": {
    "eta_goal": 5.0,
    "eta_exist": 5.0,
    "sigma_vv2": 4.0,
    "sigma_vz2": 9.0,
    "kappa_vv": 1.0,
    "kappa_vz": 1.0,
    "varrho": 0.75,
    "omega_vz": 0.7,
    "eta_vz": 5.0,
    "epsilon": 1e-6
  },
  "optimizer": {
    "goal_weight": 0.2222,
    "dist_weight": 0.2222,
    "arc_weight": 0.3333,
    "node_weight": 0.1111,
    "visit_weight": 0.1111
  }
}
```

## Dependencies

SigLIP scoring requires:

```bash
pip install torch transformers
```

Open-vocabulary verification uses OWLv2 through Transformers. If
`open_vocab_verification.device` is omitted, CUDA is used when available,
otherwise CPU is used. The default `score_threshold` is
`OPEN_VOCAB_SCORE_THRESHOLD` in `semantic_persistence/mllm_client.py`.
Verification traces include each checked target's `score`, `score_threshold`,
accepted/rejected flag, and boxes at or above the threshold.

The MLLM client uses OpenAI-compatible APIs. `base_url` and `api_key_env`
configure both detection and graph calls by default. `graph_base_url`,
`detection_base_url`, `graph_api_key_env`, and `detection_api_key_env` can split
the routers.

The optimizer requires `gurobipy` and a working Gurobi license.
