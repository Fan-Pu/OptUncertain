# Selected benchmark case

- Method: GPT54Medium proposed framework
- Batch: balanced 100-case test sample
- Case: `RPmz2sHmrrY_case_0030`
- Scan: `RPmz2sHmrrY`
- Configuration: three agents and eight targets
- Recommended illustration: observation Steps 1 and 2

## Contents

- `selected_case.json`: the exact sampled-case definition.
- `RPmz2sHmrrY_connectivity.json`: the scan connectivity graph.
- `raw_outputs/`: saved detector and graph-MLLM responses.
- `debug_outputs/`: panoramas, graph layouts, hypotheses, optimized routes,
  and route summaries for the complete episode.

These files were copied from the completed GPT54Medium batch. No API calls were
made to prepare this folder.

## Visual alignment audit

The Step 1 and Step 2 panoramas were inspected directly against the generated
graph artifacts.

- Agent 0 observes a Christmas-decorated living room with a television, curio
  cabinets, seating, and multiple trees. Regions 59 and 60 separate the TV and
  curio nook from the larger sectional-and-tree sitting area.
- Agent 1 observes a lavender bedroom with a blue quilt, a corner desk beneath
  the windows, wall signs, and a bedroom doorway. Region 61 describes these
  visible elements accurately.
- Agent 2 observes a yellow bedroom with a red quilt, a Christmas tree, a
  television, and a doorway into a bright bathroom vanity area. Regions 62 and
  63 correctly separate the bedroom from the visible bathroom.
- At Step 1, the strongest hypotheses for targets 0 and 1 are living-room
  viewpoints 50 and 21 beside the Christmas displays. The strongest hypothesis
  for target 7 is bedroom viewpoint 46, where the wall-sign and workbench area
  is visible. The remaining bedroom-sign hypotheses likewise concentrate on
  bedroom viewpoints rather than the living-room regions.

The semantic decomposition and target-location hypotheses are therefore
consistent with the observations used in the selected illustration.
