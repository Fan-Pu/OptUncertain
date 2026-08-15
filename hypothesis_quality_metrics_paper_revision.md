# Paper Revision Guide: Hypothesis-Quality Metrics

## Purpose

This report explains how to add two headline hypothesis-quality metrics to the paper:

1. **Probability-Weighted Geodesic Score (PWGS)** for target-location probabilities;
2. **Edge Joint Negative Log-Likelihood (Edge-JNLL)** for the complete structural edge hypothesis.

The definitions below are aligned with the current mathematical model and reuse the paper's existing macros whenever possible. Every newly introduced mathematical notation is also defined through a LaTeX macro.

The recommended paper structure is:

- retain **Progress** and the two **Team-PPL** metrics as end-to-end navigation measures;
- remove detector precision, recall, and F1 from the headline method-comparison tables;
- add a separate hypothesis-quality subsection and table reporting PWGS and Edge-JNLL;
- evaluate target, edge-existence, and edge-distance hypotheses before they are exposed to oracle information.

## 1. Why these metrics are appropriate

### 1.1 Probability-Weighted Geodesic Score

The paper states that the raw target scores are relative scores rather than calibrated probabilities. They are normalized over the eligible viewpoint set and then used by the MILP. PWGS therefore evaluates the resulting normalized distribution directly.

PWGS has the following properties:

- it equals one when all target probability is assigned to oracle-detectable viewpoints;
- it gives partial credit to probability assigned near an oracle-detectable viewpoint;
- it penalizes probability assigned farther away;
- it uses the complete probability distribution rather than only its top-ranked elements;
- it is normalized to \([0,1]\), making results comparable across targets and scans of different spatial scales;
- it generalizes Oracle-Visible Probability Mass: replacing normalized geodesic distance with a binary correct/incorrect cost reduces PWGS to the oracle-visible mass.

### 1.2 Edge Joint Negative Log-Likelihood

Each ungrounded edge hypothesis already defines one joint probabilistic prediction: the edge is absent with probability \(1-p\), or it exists with probability \(p\) and has a Gaussian distance distribution. Edge-JNLL evaluates the probability assigned by this complete prediction to the ground-truth outcome.

For a nonexistent edge, the loss is simply \(-\log(1-p)\). For an existing edge, the loss is the negative log of the existence probability plus the Gaussian negative log-likelihood of its true distance. These are not two separately designed metrics or a weighted combination; they are the two possible outcomes of one joint edge model.

Edge-JNLL has the following properties:

- it is one scalar, lower-is-better metric;
- it evaluates edge existence, distance-mean accuracy, and distance uncertainty simultaneously;
- it uses no probability threshold, distance tolerance, normalization constant, or fitted component weight;
- a confident false edge, a missed true edge, an incorrect distance mean, or an unjustifiably narrow distance variance all receive a large penalty;
- it is a proper log score for the probabilistic edge model.

## 2. Macro block to add to the preamble

Insert the following block after the existing numerical-experiment macros, currently ending with `\detFone`.

```latex
% hypothesis-quality evaluation notation
\newcommand{\evalEligibleVPs}[2]{\mathbf{V}_{\mathrm{elig},#1}^{#2}}
\newcommand{\evalActiveTargets}[2]{\targetSet_{\mathrm{act},#1}^{#2}}
\newcommand{\evalTargetProb}[4]{p_{#1,#3,#4}^{\mathrm{goal},#2}}
\newcommand{\oracleGeodesicDist}[3]{d_{#1}^{\mathrm{geo}}(#2,#3)}
\newcommand{\targetOracleDist}[3]{\Delta_{#1,#2}(#3)}
\newcommand{\targetOracleDistMax}[2]{\Delta_{#1,#2}^{\max}}
\newcommand{\targetHypEvalSet}[1]{\mathcal{H}_{#1}^{\mathrm{tar}}}
\newcommand{\episodePWGS}[1]{\mathrm{PWGS}_{#1}}
\newcommand{\probWeightedGeodesicScore}{\mathrm{PWGS}}

\newcommand{\oracleVPEdges}[1]{\mathbf{E}_{#1}^{\mathrm{GT}}}
\newcommand{\indicator}[1]{\mathbb{I}\!\left[#1\right]}
\newcommand{\edgeHypEvalSet}[1]{\mathcal{H}_{#1}^{\mathrm{edge}}}
\newcommand{\edgeEvalTime}[2]{t_{#1,#2}^{-}}
\newcommand{\oracleEdgeExist}[2]{y_{#1,#2}^{\mathrm{edge}}}
\newcommand{\edgeEvalExistProb}[2]{\widehat p_{#1,#2}^{\mathrm{edge}}}
\newcommand{\edgePredMean}[2]{\widehat\mu_{#1,#2}}
\newcommand{\edgePredStd}[2]{\widehat\sigma_{#1,#2}}
\newcommand{\oracleEdgeDist}[2]{d_{#1,#2}^{\mathrm{GT}}}
\newcommand{\edgeJointLogLoss}[2]{\ell_{#1,#2}^{\mathrm{edge}}}
\newcommand{\episodeEdgeJointNLL}[1]{\mathrm{EJNLL}_{#1}}
\newcommand{\edgeJointNLL}{\mathrm{EJNLL}}
```

### Macro meanings

| Macro | Meaning |
|---|---|
| `\evalEligibleVPs{i}{t}` | Eligible viewpoint set in episode \(i\) at time \(t\) |
| `\evalActiveTargets{i}{t}` | Active target set in episode \(i\) at time \(t\) |
| `\evalTargetProb{i}{t}{v}{k}` | Normalized probability assigned to target \(k\) at viewpoint \(v\) |
| `\oracleGeodesicDist{i}{v}{u}` | Ground-truth shortest-path distance between viewpoints \(v\) and \(u\) |
| `\targetOracleDist{i}{k}{v}` | Distance from \(v\) to the nearest oracle-detectable viewpoint for target \(k\) |
| `\targetOracleDistMax{i}{k}` | Largest such target distance in episode \(i\) |
| `\targetHypEvalSet{i}` | Active time-target pairs evaluated for PWGS |
| `\episodePWGS{i}` | Episode-level PWGS |
| `\probWeightedGeodesicScore` | Dataset-level PWGS |
| `\oracleVPEdges{i}` | Ground-truth navigation edge set for episode \(i\) |
| `\indicator{condition}` | Indicator equal to one when the stated condition holds |
| `\edgeHypEvalSet{i}` | Fixed candidate set of ungrounded edge hypotheses |
| `\edgeEvalTime{i}{e}` | Last instant at which edge \(e\) remains ungrounded |
| `\oracleEdgeExist{i}{e}` | Binary ground-truth existence label for edge \(e\) |
| `\edgeEvalExistProb{i}{e}` | Last pre-grounding existence probability |
| `\edgePredMean{i}{e}` | Last pre-grounding edge-distance mean |
| `\edgePredStd{i}{e}` | Last pre-grounding edge-distance standard deviation |
| `\oracleEdgeDist{i}{e}` | Ground-truth distance of an existing edge |
| `\edgeJointLogLoss{i}{e}` | Joint negative log-likelihood of candidate edge \(e\) |
| `\episodeEdgeJointNLL{i}` | Episode-level Edge Joint Negative Log-Likelihood |
| `\edgeJointNLL` | Dataset-level Edge Joint Negative Log-Likelihood |

## 3. Correct a notation inconsistency in the existing evaluation section

The paper already defines

```latex
\newcommand{\evalViewpoints}[1]{\mathbf{V}_{#1}}
```

but the Evaluation Metrics subsection currently writes `\viewpoints{i}` for the episode-level navigation viewpoint set. The latter macro is already used in the method section for the time-indexed online viewpoint set.

Change:

```latex
let $\evalAgents{i}\subseteq\agentSet$ be the robot team,
$\evalTargets{i}\subseteq\targetSet$ the target set,
$\viewpoints{i}$ the navigation viewpoint set
```

to:

```latex
let $\evalAgents{i}\subseteq\agentSet$ be the robot team,
$\evalTargets{i}\subseteq\targetSet$ the target set,
$\evalViewpoints{i}$ the complete evaluation navigation viewpoint set
```

This separates the complete offline evaluation graph \(\evalViewpoints{i}\) from the online accumulated set \(\viewpoints{1:t}\).

## 4. Evaluation timing and information boundary

PWGS and Edge-JNLL must be computed using oracle annotations only after the online run has finished. Oracle labels must never enter graph generation, graph updating, optimization, or action selection.

Use the following evaluation instants:

- **PWGS:** after the target probabilities have been updated at time \(t\), but before the MILP is solved and the agents move;
- **Edge-JNLL:** at the last instant when each candidate edge is still ungrounded.

Do not score grounded edges using their post-grounding state. After grounding, the framework sets the existence probability to one and replaces the uncertain distance with the measured value. Scoring that state would leak the evaluation answer into the prediction and would make Edge-JNLL trivially favorable.

## 5. Copy-paste subsection for the paper

Replace the current `Detection F1 Score` paragraph with the following material. It can remain inside `\subsection{Evaluation Metrics}` after Team-PPL and before implementation details.

```latex
\paragraph{\textbf{Hypothesis-quality evaluation}}
In addition to end-to-end search performance, we evaluate the
target-location and structural hypotheses maintained by the online graph.
All oracle quantities introduced below are used only for offline evaluation
and are unavailable during graph generation, graph updating, optimization,
and execution. Target-location hypotheses are evaluated immediately after
the graph update and before action selection. Edge hypotheses are evaluated
at their last ungrounded state, before their existence or distance is
revealed by the navigation system.

\paragraph{\textbf{Probability-Weighted Geodesic Score}}
For episode $i$, let $\oracleGeodesicDist{i}{v}{u}$ denote the
shortest-path distance between viewpoints $v,u\in\evalViewpoints{i}$ in
the complete ground-truth navigation graph. For target
$k\in\evalTargets{i}$, define the distance from viewpoint $v$ to its
nearest oracle-detectable viewpoint as
\begin{equation}
\targetOracleDist{i}{k}{v}
:=
\min_{u\in\oracleDetectable{i}{k}}
\oracleGeodesicDist{i}{v}{u},
\qquad
v\in\evalViewpoints{i}.
\label{eq:pwgs_oracle_distance}
\end{equation}
We normalize this quantity by the largest target-specific distance
\begin{equation}
\targetOracleDistMax{i}{k}
:=
\max_{v\in\evalViewpoints{i}}
\targetOracleDist{i}{k}{v}.
\label{eq:pwgs_max_distance}
\end{equation}
Let $\evalEligibleVPs{i}{t}$ and $\evalActiveTargets{i}{t}$ denote the
eligible viewpoints and active targets after the graph update at time $t$,
and let $\evalTargetProb{i}{t}{v}{k}$ be the normalized target-location
probability corresponding to $\targetProb{t}{v}{k}$ in episode $i$.
The evaluated active target-time pairs are
\begin{equation}
\targetHypEvalSet{i}
:=
\left\{
(t,k):
1\leq t\leq\episodeHorizon{i},~
k\in\evalActiveTargets{i}{t}
\right\}.
\label{eq:pwgs_eval_set}
\end{equation}
The episode-level Probability-Weighted Geodesic Score is
\begin{equation}
\episodePWGS{i}
:=
\frac{1}{|\targetHypEvalSet{i}|}
\sum_{(t,k)\in\targetHypEvalSet{i}}
\left[
1-
\sum_{v\in\evalEligibleVPs{i}{t}}
\evalTargetProb{i}{t}{v}{k}
\frac{\targetOracleDist{i}{k}{v}}
{\targetOracleDistMax{i}{k}}
\right].
\label{eq:pwgs_episode}
\end{equation}
The dataset-level score is
\begin{equation}
\probWeightedGeodesicScore
:=
\frac{1}{|\episodeSet|}
\sum_{i\in\episodeSet}
\episodePWGS{i}.
\label{eq:pwgs_dataset}
\end{equation}
The score lies in $[0,1]$, and higher is better. A score of one means
that all target-location probability is assigned to oracle-detectable
viewpoints. Probability assigned to a non-detectable viewpoint receives
partial credit according to its ground-truth geodesic proximity to the
nearest detectable viewpoint.

\paragraph{\textbf{Edge Joint Negative Log-Likelihood}}
For each episode $i$, let $\edgeHypEvalSet{i}$ be a method-independent
candidate set of ungrounded edges supplied to every evaluated hypothesis
generator. Let $\oracleVPEdges{i}$ be the complete ground-truth navigation
edge set and define
\begin{equation}
\oracleEdgeExist{i}{e}
:=
\indicator{e\in\oracleVPEdges{i}},
\qquad
e\in\edgeHypEvalSet{i}.
\label{eq:edge_oracle_exist_label}
\end{equation}
Let $\edgeEvalTime{i}{e}$ denote the last evaluation instant before edge
$e$ becomes grounded, is removed, or the episode terminates. At that
instant, define the predicted existence probability, distance mean, and
distance standard deviation as
\begin{equation}
\begin{aligned}
\edgeEvalExistProb{i}{e}
&:=
\condEdgeExistProb{\edgeEvalTime{i}{e}}{e},\\
\edgePredMean{i}{e}
&:=
\travelDist{\edgeEvalTime{i}{e}}{e},\\
\left(\edgePredStd{i}{e}\right)^2
&:=
\travelDistVar{\edgeEvalTime{i}{e}}{e}.
\end{aligned}
\label{eq:edge_joint_prediction}
\end{equation}
For an existing edge, let $\oracleEdgeDist{i}{e}$ denote its ground-truth
travel distance in meters. The joint log loss of candidate edge $e$ is
\begin{equation}
\edgeJointLogLoss{i}{e}
:=
\begin{cases}
-\log\!\left(
1-\edgeEvalExistProb{i}{e}
\right),
&
\oracleEdgeExist{i}{e}=0,
\\[3pt]
-\log\!\left(
\edgeEvalExistProb{i}{e}
\right)
+
\dfrac{1}{2}
\log\!\left(
2\pi\left(\edgePredStd{i}{e}\right)^2
\right)
+
\dfrac{
\left(
\oracleEdgeDist{i}{e}-\edgePredMean{i}{e}
\right)^2
}{
2\left(\edgePredStd{i}{e}\right)^2
},
&
\oracleEdgeExist{i}{e}=1.
\end{cases}
\label{eq:edge_joint_log_loss}
\end{equation}
The first branch evaluates the probability assigned to edge absence. The
second branch is the negative logarithm of the probability assigned to
edge existence plus the Gaussian negative log-likelihood of the true
distance. Thus, both outcomes arise from one joint probabilistic edge
model rather than from a weighted combination of separate metrics.

The episode-level and dataset-level scores are
\begin{equation}
\episodeEdgeJointNLL{i}
:=
\frac{1}{|\edgeHypEvalSet{i}|}
\sum_{e\in\edgeHypEvalSet{i}}
\edgeJointLogLoss{i}{e},
\label{eq:edge_joint_nll_episode}
\end{equation}
\begin{equation}
\edgeJointNLL
:=
\frac{1}{|\episodeSet|}
\sum_{i\in\episodeSet}
\episodeEdgeJointNLL{i}.
\label{eq:edge_joint_nll_dataset}
\end{equation}
Edge-JNLL is lower-is-better. It has no threshold, tolerance, user-chosen
normalization scale, or component weight. The evaluation uses distances
in meters for every method and natural logarithms, so the reported unit is
nats per candidate edge. Exact boundary probabilities produce the mathematically
appropriate infinite penalty when contradicted by the oracle outcome;
therefore, the metric definition does not clip probabilities or variances.
```

## 6. Aggregation protocol

The aggregation order matters because methods terminate after different numbers of steps and may produce different numbers of graph hypotheses.

### 6.1 PWGS

Use the following order:

1. compute one PWGS value for each active target at each post-update, pre-action step;
2. average these values within each episode;
3. average the episode-level scores across episodes.

Do not pool all active target-step pairs across the dataset before averaging. Such micro-averaging would give greater weight to long, unsuccessful episodes.

For Dec-Graph:

1. apply the same PWGS definition to each agent's private graph;
2. average the private-graph scores across active agents at each target-step pair;
3. perform the episode and dataset aggregation above.

Do not evaluate the union of Dec-Graph's private graphs. That union is not available to any Dec-Graph agent during planning and would overstate the usable hypothesis quality.

### 6.2 Edge-JNLL

For a fair comparison, `\edgeHypEvalSet{i}` must be fixed independently of the evaluated method. Every model must receive the same candidate edge set and return an existence probability, distance mean, and distance variance for every candidate.

Do not define `\edgeHypEvalSet{i}` separately as “the edges proposed by each method.” That would permit a conservative method to avoid difficult candidates and obtain an artificially favorable Edge-JNLL.

Recommended aggregation:

1. score each candidate edge once using its last ungrounded posterior;
2. average candidate-edge scores within each episode;
3. average episode scores across the common episode set.

The common candidate set should contain both existing and nonexistent
edges in every evaluated episode. A nonexistent edge contributes only its
absence log loss because no ground-truth distance exists. An existing edge
contributes both its existence and Gaussian-distance likelihood through
the single second branch of `\edgeJointLogLoss{i}{e}`.

## 7. Initial versus updated hypotheses

The main table should use the final pre-grounding predictions because they represent the combined output of hypothesis generation and online updating.

If the paper also wants to demonstrate that the update rules improve the hypotheses, use the same metrics at two stages:

- **Initial:** immediately after an edge is first generated;
- **Updated:** at `\edgeEvalTime{i}{e}`, immediately before grounding, removal, or termination.

Use Edge-JNLL as the structural score:

```latex
$\edgeJointNLL^{\mathrm{init}}$
\quad\text{and}\quad
$\edgeJointNLL^{\mathrm{upd}}$.
```

The improvement is

\[
\edgeJointNLL^{\mathrm{init}}
-
\edgeJointNLL^{\mathrm{upd}}.
\]

A positive difference indicates that the complete joint edge hypothesis improved.

## 8. Recommended table organization

Do not add the hypothesis metrics to the existing navigation-performance tables. Progress and Team-PPL measure task outcomes, while PWGS and Edge-JNLL measure internal hypotheses. Mixing them would weaken the message of both groups.

Use a separate table:

```latex
\begin{table}[tbp]
\small
\centering
\caption{Quality of target-location and structural graph hypotheses.
Edge-JNLL is the mean joint log loss per candidate edge.}
\label{tab:hypothesis_quality}
\setlength{\tabcolsep}{4pt}
\renewcommand{\arraystretch}{1.12}
\begin{tabular}{@{}lrr@{}}
\toprule
Method
& \multicolumn{1}{c}{PWGS $\uparrow$}
& \multicolumn{1}{c}{Edge-JNLL (nats) $\downarrow$} \\
\midrule
GPT-Medium    & -- & -- \\
Qwen-Thinking & -- & -- \\
Qwen-Instant  & -- & -- \\
Gemma-Instant & -- & -- \\
Dec-Graph*    & -- & -- \\
\bottomrule
\end{tabular}
\end{table}
```

The Oracle should not be inserted as a row because it does not generate uncertain hypotheses. VLFM-G should not receive Edge-JNLL because it does not generate the same probabilistic ungrounded-edge representation. If a target score is computed for VLFM-G, it should be reported only when its score can be normalized over the same candidate viewpoint support without introducing an additional heuristic transformation.

## 9. Applicability to the existing 100-case experiment

### 9.1 PWGS

PWGS can be computed offline from the existing artifacts:

- `hypothesis_step_XXXX.json` provides `target_probs`;
- `scenarios/batch_test.json` provides oracle-detectable viewpoint IDs;
- the complete connectivity graph provides shortest-path distances;
- episode manifests and graph snapshots provide active targets and eligible viewpoints.

No new paid MLLM calls are required for PWGS.

### 9.2 Edge-JNLL

The current balanced-100 graph snapshots for GPT-Medium, Gemma-Instant, Qwen-Thinking, Qwen-Instant, and Dec-Graph contain no edges whose saved state has `grounded=false`. Therefore:

- Edge-JNLL cannot be estimated from the current 100-case outputs;
- scoring grounded edges would be invalid because their probabilities and distances have already been replaced by verified values.

Before reporting Edge-JNLL, add a controlled structural-hypothesis benchmark with:

1. a common candidate edge set for all evaluated graph models;
2. both existing and nonexistent candidate edges;
3. ground-truth distances for the existing candidates;
4. saved initial predictions;
5. saved updated predictions immediately before oracle revelation.

Until this experiment exists, the paper may define Edge-JNLL as a planned evaluation metric, but it must not present numerical claims about edge-hypothesis accuracy or update quality.

## 10. Interpretation text for the results section

After numerical values are available, use a paragraph with this logic:

```latex
PWGS evaluates whether each method concentrates its target-location
probability near oracle-detectable viewpoints. Edge-JNLL evaluates each
complete edge hypothesis as one joint probabilistic prediction: an edge
is either absent, or it exists with a Gaussian travel distance. A lower
Edge-JNLL means that the method assigns greater likelihood to the correct
edge existence outcomes and to the true distances of existing edges.
```

Avoid saying that PWGS measures calibrated target probabilities. The method section explicitly states that the raw target scores are not calibrated; PWGS measures the spatial quality of the normalized target-location distribution.

Avoid describing Edge-JNLL as an accuracy percentage. It is an average log loss in nats per candidate edge. It evaluates existence confidence, distance-mean error, and distance uncertainty jointly.

## 11. Recommended citations

PWGS is a task-specific metric introduced for this paper and does not require an external citation. Edge-JNLL instantiates the standard logarithmic scoring rule for the paper's Bernoulli-existence/Gaussian-distance edge model. Cite a standard proper-scoring-rule reference, such as Gneiting and Raftery, “Strictly Proper Scoring Rules, Prediction, and Estimation,” 2007, when Edge-JNLL is introduced.

## 12. Claim–evidence map

| Claim | Required evidence | Status |
|---|---|---|
| The target-location hypotheses concentrate probability near correct search locations. | PWGS over the frozen 100-case sample, macro-averaged by episode. | Computable from saved outputs |
| The complete structural edge hypotheses are accurate. | Edge-JNLL on a common candidate-edge benchmark containing existing and nonexistent edges. | Needs new structural benchmark |
| Online updating improves structural hypotheses. | Initial-versus-updated Edge-JNLL on matched edge candidates. | Needs new structural benchmark |
| Shared graph information improves the hypotheses available to each agent. | Centralized PWGS versus agent-averaged private Dec-Graph PWGS. | Computable from saved outputs |

## 13. Brief explanation and limitation of the current detection F1

### 13.1 What the reported F1 is based on

The current evaluator does not compute detection F1 on one fixed image set shared by all variants. It computes the score from the detector checks generated while each method executes its own routes.

For one method, define the evaluated detector-query set as

```latex
\begin{equation}
\detectQuerySet
:=
\left\{
(i,t,q,k):
q\in\evalAgents{i},\
k\in\evalActiveTargets{i}{t},\
\text{agent $q$ is checked at time $t$}
\right\}.
\end{equation}
```

Each element is one active-target check for one agent at its current viewpoint. The saved detector output is `\detOutput{i}{t}{q}{k}`. Its oracle label is based on whether the agent's current viewpoint belongs to the manually defined oracle-detectable viewpoint set of that target:

```latex
\begin{equation}
\oracleDetLabel{i}{t}{q}{k}
:=
\indicator{
\evalCurrentVp{i}{t}{q}
\in
\oracleDetectable{i}{k}
}.
\end{equation}
```

Thus:

```latex
\begin{align}
\truePositive
&=
\sum_{(i,t,q,k)\in\detectQuerySet}
\indicator{
\detOutput{i}{t}{q}{k}=1
\wedge
\oracleDetLabel{i}{t}{q}{k}=1
},\\
\falsePositive
&=
\sum_{(i,t,q,k)\in\detectQuerySet}
\indicator{
\detOutput{i}{t}{q}{k}=1
\wedge
\oracleDetLabel{i}{t}{q}{k}=0
},\\
\falseNegative
&=
\sum_{(i,t,q,k)\in\detectQuerySet}
\indicator{
\detOutput{i}{t}{q}{k}=0
\wedge
\oracleDetLabel{i}{t}{q}{k}=1
}.
\end{align}
\begin{equation}
\detPrecision
=
\frac{\truePositive}{\truePositive+\falsePositive},
\qquad
\detRecall
=
\frac{\truePositive}{\truePositive+\falseNegative},
\qquad
\detFone
=
\frac{2\truePositive}
{2\truePositive+\falsePositive+\falseNegative}.
\end{equation}
```

True negatives do not enter F1. The implementation sums `TP`, `FP`, and `FN` over all evaluated checks and episodes before computing the ratios, so the reported value is a **micro-averaged detection F1**.

### 13.2 Why F1 values across the variants are not directly comparable

The user's concern is correct: every variant induces a different `\detectQuerySet`. Its routes determine:

- which panoramas and viewpoints are checked;
- how many detection steps are executed;
- which targets remain active at each step;
- how often the detector encounters easy, difficult, or occluded views.

A method that reaches a target quickly removes that target from later checks. A longer route produces more detector opportunities and potentially more false negatives. Consequently, differences in the reported F1 combine two effects: detector behavior and the method-dependent distribution of observations. They do **not** isolate the quality of the generated target or edge hypotheses.

The value is still meaningful as a **route-conditioned (on-policy) detector diagnostic**: it answers, “How accurate was the detector on the observations that this policy actually encountered?” It should not be interpreted as a controlled head-to-head detector comparison among variants.

### 13.3 Recommended paper treatment

Remove F1 from the headline variant-comparison table, as already recommended in this report. If it is retained for transparency, label it “route-conditioned detection F1” and place it in an appendix or diagnostic table with the preceding caveat.

A short copy-paste-ready explanation is:

```latex
\paragraph{\textbf{Route-conditioned detection F1.}}
For diagnostic purposes, we compare each detector output with an oracle
visibility label indicating whether the agent's current viewpoint belongs
to the target's oracle-detectable viewpoint set. We micro-aggregate true
positives, false positives, and false negatives over all active-target
checks encountered during execution and compute
$\detFone=2\truePositive/(2\truePositive+\falsePositive+\falseNegative)$.
Because each navigation variant visits different viewpoints, terminates
at different times, and removes found targets from subsequent checks, its
detector-query set is policy dependent. The resulting F1 is therefore an
on-policy detector diagnostic rather than a directly comparable measure
of graph-hypothesis quality.
```

For a strictly comparable detector evaluation, all variants would need to be scored on the same frozen set of panorama-target queries. Because the variants use the same detector, however, that controlled score would evaluate the shared detector rather than distinguish the navigation or hypothesis-generation methods. PWGS is the more relevant comparative metric for target-location hypothesis quality.

## 14. Final self-review checklist

- [ ] The complete offline viewpoint set uses `\evalViewpoints{i}`, not the time-indexed `\viewpoints{i}`.
- [ ] Every new mathematical symbol is introduced through a macro.
- [ ] PWGS uses normalized `target_probs`, not uncalibrated raw scores.
- [ ] PWGS is evaluated only for active targets at post-update, pre-action states.
- [ ] Dec-Graph private graphs are averaged rather than merged.
- [ ] The edge candidate set is fixed across methods.
- [ ] Edge-JNLL is evaluated on the last ungrounded posterior before oracle revelation.
- [ ] The distance standard deviation is the square root of the stored variance and is strictly positive.
- [ ] Nonexistent edges use the absence branch; existing edges use the joint existence-and-distance branch.
- [ ] Edge probabilities and variances are not clipped for evaluation.
- [ ] Every method uses metres and the natural logarithm, so Edge-JNLL is reported in nats per candidate edge.
- [ ] Ground-truth connectivity and distances are used only offline.
- [ ] Dataset results are macro-averaged by episode.
- [ ] Edge-JNLL is not reported for the existing 100-case outputs unless a valid ungrounded-edge benchmark is added.
- [ ] Table headers include metric directions and the Edge-JNLL unit.
- [ ] Any retained detection F1 is labeled as route-conditioned and is not used as a controlled comparison of graph-hypothesis quality.
- [ ] Claims in the Abstract and Conclusion are restricted to metrics that have actually been computed.
