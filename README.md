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
      "id": "plant",
      "description": "green plant on the table",
      "distance_threshold_m": 1.0
    }
  ],
  "mllm": {
    "model_name": "meta-llama/Llama-4-Maverick-17B-128E-Instruct:cheapest",
    "max_new_tokens": 160
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
    "arc_weight": 0.4444,
    "node_weight": 0.1111,
    "ungrounded_reward_weight": 0.8
  }
}
```

## Dependencies

SigLIP scoring requires:

```bash
pip install torch transformers
```

The MLLM client uses the Hugging Face router through the OpenAI-compatible API and requires `HF_TOKEN`.

The optimizer requires `gurobipy` and a working Gurobi license.
