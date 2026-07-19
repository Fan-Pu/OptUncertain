# Mathematical Revision Report: Lexicographic Objective Used in the 100-Case Experiments

## 1. Purpose and central conclusion

The current paper describes the proposed rolling-horizon MILP using one normalized, weighted objective. That formulation does **not** match the optimizer used for the reported 100-case experiments.

The implemented and evaluated model uses a **two-priority lexicographic objective**:

1. maximize the aggregate target-directed reward; and
2. among solutions attaining the best target reward, minimize a weighted, normalized route cost comprising travel distance, edge-nonexistence risk, node-nonexistence risk, and revisits.

The mathematical model in the paper should therefore be revised from a scalarized five-term objective to a hierarchical objective. The constraints remain part of one MILP. This is not two independently formulated planning models, and it is not a user-level procedure that solves one model and then constructs another. It is one Gurobi multi-objective model with two objective priorities.

This conclusion is supported by both the implementation and the saved experimental records:

- `config/default_config.json` sets `target_directed_mode` to `true`.
- `optimization_model/optimizer.py` defines two objectives using `setObjectiveN`, with priorities 2 and 1.
- all 4,372 saved optimizer decisions from the four proposed-method 100-case variants record `is_multi_objective: true` and `status_name: OPTIMAL`.

## 2. Main discrepancies in the current paper

| Item | Current paper | Model used in the experiments | Required revision |
|---|---|---|---|
| Objective structure | One normalized weighted sum | Two-priority lexicographic objective | Replace the single weighted objective with primary and secondary problems |
| Primary objective | Weighted normalized goal term | Unnormalized aggregate target reward $G^t$ | Remove goal normalization and $w^{\mathrm{goal}}$ from the active objective |
| Goal coefficient | $w^{\mathrm{goal}}$, configured as 0.45 | Inactive when `target_directed_mode=true` | Do not report 0.45 as an active experimental objective coefficient |
| Target reward | Maximum target probability at every selected node | Reward assigned through binary target--viewpoint--agent variables | Define $G^t$ using $a_{k,v,q}^t$ |
| Target uniqueness | Current text says every active target is assigned exactly once | Each active target is assigned **at most once** | Replace equality by an upper-bound constraint |
| Node uncertainty | Mentioned in experimental settings but absent from the mathematical objective | Explicit node-nonexistence term with weight 0.03 | Define and normalize the missing node term |
| Secondary weights | Presented as part of a five-term trade-off | Used only within the secondary route-cost priority | Explain that these are within-priority trade-off coefficients |
| Objective tolerances | Not stated in the model section | Absolute and relative degradation tolerances are both zero | State that the secondary objective cannot degrade the primary optimum |
| Meaning of "balancing" | Suggests target reward can be exchanged for lower travel or risk | No secondary improvement may sacrifice target reward | Replace "balances" with lexicographic language throughout the paper |

## 3. Recommended notation

The paper already defines most of the necessary notation. Add the following symbols or macros:

```latex
% node-nonexistence objective term and weight
\newcommand{\nodeUnreliaWeight}{w^{\mathrm{node}}}
\newcommand{\nodeTerm}[1]{H^{#1}}

% node-nonexistence term bounds
\newcommand{\nodeUnreliaWeightUB}{U^{\mathrm{node}}}
\newcommand{\nodeUnreliaWeightLB}{L^{\mathrm{node}}}

% feasible set and secondary route-cost objective
\newcommand{\feasibleSet}[1]{\mathcal{F}^{#1}}
\newcommand{\routeCostTerm}[1]{\Psi^{#1}}
\newcommand{\optimalGoalTerm}[1]{G^{#1,*}}
```

Here, $H^t$ is recommended for the node-nonexistence term to avoid reusing $N^t$, because the paper already uses $\mathbf{N}^t$ for the node set.

The macro

```latex
\newcommand{\nodeTargetWeight}{w^{\mathrm{goal}}}
```

should be removed from the active model formulation. It may be retained only if the paper explicitly introduces the unevaluated single-objective mode as a separate model variant. Otherwise, retaining it implies that the reported experiments used the 0.45 goal weight, which they did not.

## 4. Correct target-reward formulation

### 4.1 Active targets and eligible reward endpoints

Let

\[
\mathbf K_{\mathrm{act}}^t
:=
\{k\in\mathbf K:f_k^t=0\}
\]

be the active, not-yet-found targets. For each agent $q$, let $\mathbf R_q^t$ be its eligible target-reward endpoints. To match the implementation, an eligible endpoint is a reachable viewpoint that:

- is not the current viewpoint of any agent;
- is ungrounded;
- has not previously been visited; and
- remains reachable in the admissible planning graph after excluded visited dead ends are removed.

The current paper says "non-current and ungrounded," but its displayed set only imposes $\tau_v^t=0$. The displayed definition should either include all four conditions or state that $\mathbf R_q^t$ is produced by applying these filters to the candidate viewpoint set.

### 4.2 Assignment-based reward

The implemented target reward is not

\[
\sum_q\sum_v
\max_k\{(1-f_k^t)p_{v,k}^{\mathrm{goal},t}\}
y_{v,q}^t.
\]

That expression belongs to the alternative non-target-directed mode. In the evaluated target-directed mode, define the reward as

\[
G^t
:=
\sum_{q\in\mathbf Q}
\sum_{v\in\mathbf R_q^t}
\sum_{k\in\mathbf K_{\mathrm{act}}^t}
p_{v,k}^{\mathrm{goal},t}a_{k,v,q}^t.
\tag{R1}
\]

The probability $p_{v,k}^{\mathrm{goal},t}$ in (R1) is the processed target-location probability stored in `target_probs`, because the experimental configuration has `target_directed_use_raw_target_probs=false`. Calling $G^t$ "unnormalized" means that the aggregate reward is not transformed by the objective-term min--max normalization; it does **not** mean that the raw MLLM score is used.

### 4.3 Assignment constraints

The assignment variable may be active only at a selected endpoint:

\[
a_{k,v,q}^t\le y_{v,q}^t,
\qquad
\forall q\in\mathbf Q,\ v\in\mathbf R_q^t,\ k\in\mathbf K.
\tag{R2}
\]

Assignments with zero target reward are prohibited:

\[
a_{k,v,q}^t=0
\quad\text{if}\quad
p_{v,k}^{\mathrm{goal},t}=0.
\tag{R3}
\]

Each target can contribute reward at most once across the entire team:

\[
\sum_{q\in\mathbf Q}
\sum_{v\in\mathbf R_q^t}
a_{k,v,q}^t
\le 1-f_k^t,
\qquad
\forall k\in\mathbf K.
\tag{R4}
\]

Equation (R4) should replace the current equality. When $f_k^t=1$, it forces all assignments for target $k$ to zero. When $f_k^t=0$, the target may be assigned at most once. A positive feasible assignment is encouraged by the primary objective, but the model does not impose that every active target must be assigned exactly once.

The implementation conditionally adds

\[
\sum_{k\in\mathbf K_{\mathrm{act}}^t}
\sum_{v\in\mathbf R_q^t}
a_{k,v,q}^t\ge 1,
\qquad \forall q\in\mathbf Q,
\tag{R5}
\]

only when:

1. the number of active targets is at least the number of agents; and
2. the bipartite graph between agents and positive-reward targets admits a matching that covers every agent with a distinct target.

The current prose should be changed from "when every agent has at least one positive reward endpoint" to this full-matching condition. Individual positive candidates do not by themselves guarantee a distinct target for every agent.

## 5. Correct secondary objective terms

The secondary objective contains four terms.

### 5.1 Travel distance

\[
D^t
:=
\sum_{q\in\mathbf Q}
\sum_{(i,j)\in\mathbf E^t}
d_{\{i,j\}}^t x_{i,j,q}^t.
\tag{C1}
\]

### 5.2 Edge-nonexistence risk

\[
A^t
:=
\sum_{q\in\mathbf Q}
\sum_{(i,j)\in\mathbf E^t}
\left(1-p_{\mathrm{exist},\{i,j\}}^{t,\mathrm{cond}}\right)
x_{i,j,q}^t.
\tag{C2}
\]

### 5.3 Node-nonexistence risk

The current paper omits this implemented term. Add

\[
H^t
:=
\sum_{q\in\mathbf Q}
\sum_{n\in\mathbf N_q^t}
\left(1-p_n^{\mathrm{exist},t}\right)y_{n,q}^t.
\tag{C3}
\]

This term penalizes selected hypothesized nodes in proportion to their nonexistence probability. It is distinct from $A^t$: $A^t$ represents uncertain connectivity, whereas $H^t$ represents uncertain node existence.

### 5.4 Revisit penalty

\[
R^t
:=
\sum_{q\in\mathbf Q}
\sum_{v\in\mathbf V_q^t}
\tau_v^t y_{v,q}^t.
\tag{C4}
\]

## 6. Normalization used by the secondary objective

Define

\[
\mathcal M_s^t(X)
:=
\begin{cases}
0, & U_s^t=L_s^t,\\[2mm]
\dfrac{X-L_s^t}{U_s^t-L_s^t}, & U_s^t>L_s^t,
\end{cases}
\tag{N1}
\]

for

\[
s\in\{\mathrm{dist},\mathrm{arc},\mathrm{node},\mathrm{visit}\}.
\]

The goal term should be excluded from this set in the active formulation. Although the implementation computes goal bounds for diagnostic output, the primary solver objective uses $G^t$, not $\mathcal M_{\mathrm{goal}}^t(G^t)$.

The existing distance, arc, and revisit bounds can be retained, subject to notation cleanup. Add the node bounds

\[
L_{\mathrm{node}}^t=0,
\qquad
U_{\mathrm{node}}^t
=
\sum_{q\in\mathbf Q}
\sum_{n\in\mathbf N_q^t}
\left(1-p_n^{\mathrm{exist},t}\right).
\tag{N2}
\]

The paper's current goal-bound derivation is not needed to define the active optimization model. It can be deleted or moved to an implementation-diagnostics paragraph with an explicit statement that it is not used by either objective priority.

## 7. Correct two-priority mathematical formulation

Let $\mathcal F^t$ denote the feasible set defined by all path-construction, grounded-first-hop, dead-end exclusion, assignment, first-action uniqueness, variable-domain, and subtour-elimination constraints.

Define the normalized secondary route cost as

\[
\Psi^t
:=
0.17\,\mathcal M_{\mathrm{dist}}^t(D^t)
+0.05\,\mathcal M_{\mathrm{arc}}^t(A^t)
+0.03\,\mathcal M_{\mathrm{node}}^t(H^t)
+0.30\,\mathcal M_{\mathrm{visit}}^t(R^t).
\tag{L1}
\]

The primary problem is

\[
G^{t,*}
:=
\max_{(x,y,u,a)\in\mathcal F^t}G^t.
\tag{L2}
\]

The secondary problem is

\[
\min_{(x,y,u,a)\in\mathcal F^t}
\Psi^t
\quad\text{s.t.}\quad
G^t=G^{t,*}.
\tag{L3}
\]

Equivalently, the complete objective can be written compactly as

\[
\operatorname{lexmax}_{(x,y,u,a)\in\mathcal F^t}
\left(
G^t,
-\Psi^t
\right).
\tag{L4}
\]

Equations (L2)--(L4) communicate the central behavioral property: a reduction in distance, structural risk, or revisits is accepted only if it leaves the maximum attainable target reward unchanged.

### Interpretation of the weights

The coefficients $(0.17,0.05,0.03,0.30)$ do not need to sum to one because they operate only within the secondary priority. Their sum is 0.55 because the configured 0.45 goal coefficient belongs to the alternative single-weighted-objective code path and is inactive in the evaluated target-directed mode.

Multiplying all four secondary weights by the same positive constant would leave the secondary ranking unchanged. Nevertheless, the paper should retain the actual values $(0.17,0.05,0.03,0.30)$ to reproduce the implementation exactly; it should not silently replace them with normalized values.

### Exact preservation of the primary optimum

The two Gurobi objectives have absolute and relative degradation tolerances equal to zero:

\[
\epsilon_{\mathrm{abs}}=0,
\qquad
\epsilon_{\mathrm{rel}}=0.
\tag{L5}
\]

Mathematically, this gives the equality $G^t=G^{t,*}$ in (L3). The secondary objective is therefore a tie-breaker over primary-optimal solutions, not a term that trades target reward for route efficiency.

## 8. Paste-ready replacement for the paper's objective subsection

The following LaTeX can replace the text beginning with `\paragraph{\textbf{Objective Function}}` through the current single weighted objective. The term definitions may be split across equations if needed for IEEE column width.

```latex
\paragraph{\textbf{Lexicographic Objective}}
The target-directed optimizer uses a two-priority lexicographic objective.
Its primary objective maximizes target-directed reward, and its secondary
objective minimizes normalized route cost without degrading the optimal
primary reward. For each active target, reward can be credited to at most
one selected agent--endpoint pair. Accordingly, define
\begin{equation}
\goalTerm{t}
:=
\sum_{q\in\agentSet}
\sum_{v\in\rewardVPs{t}{q}}
\sum_{k\in\actTargets{t}}
\targetProb{t}{v}{k}
\targetAssignVar{t}{k}{v}{q}.
\label{eq:goal_term}
\end{equation}

The route-cost terms are
\begin{align}
\distTerm{t}
&:=
\sum_{q\in\agentSet}
\sum_{\orEdgeWrap{i}{j}\in\VPEdges{t}}
\travelDist{t}{\edgeWrap{i}{j}}
\arcSelectVar{t}{i,j}{q},\\
\arcTerm{t}
&:=
\sum_{q\in\agentSet}
\sum_{\orEdgeWrap{i}{j}\in\VPEdges{t}}
\left(1-\condEdgeExistProb{t}{\edgeWrap{i}{j}}\right)
\arcSelectVar{t}{i,j}{q},\\
\nodeTerm{t}
&:=
\sum_{q\in\agentSet}
\sum_{n\in\candidateNodes{t}{q}}
\left(1-\existProb{t}{n}\right)
\multiAgentNodeSelectVar{t}{n}{q},\\
\visitTerm{t}
&:=
\sum_{q\in\agentSet}
\sum_{v\in\candidateVPs{t}{q}}
\nodeVisitTimes{t}{v}
\multiAgentNodeSelectVar{t}{v}{q}.
\end{align}

For
$s\in\{\mathrm{dist},\mathrm{arc},\mathrm{node},\mathrm{visit}\}$,
let
\begin{equation}
\normTerm{t}{s}{X}
:=
\begin{cases}
0, & U^s=L^s,\\
\dfrac{X-L^s}{U^s-L^s}, & U^s>L^s.
\end{cases}
\label{eq:objective_normalization}
\end{equation}
The normalized secondary route cost is
\begin{equation}
\begin{aligned}
\routeCostTerm{t}
:={}&
0.17\normTerm{t}{\mathrm{dist}}{\distTerm{t}}
+0.05\normTerm{t}{\mathrm{arc}}{\arcTerm{t}}\\
&+0.03\normTerm{t}{\mathrm{node}}{\nodeTerm{t}}
+0.30\normTerm{t}{\mathrm{visit}}{\visitTerm{t}}.
\end{aligned}
\label{eq:secondary_route_cost}
\end{equation}

Let $\feasibleSet{t}$ denote the feasible set induced by
constraints~\eqref{eq:multi_agent_depart}--\eqref{eq:mtz} and the
variable domains. The first-priority optimum is
\begin{equation}
\optimalGoalTerm{t}
:=
\max_{(x,y,u,a)\in\feasibleSet{t}}
\goalTerm{t}.
\label{eq:primary_objective}
\end{equation}
The second-priority problem is
\begin{equation}
\begin{aligned}
\min_{(x,y,u,a)\in\feasibleSet{t}}\quad
&\routeCostTerm{t}\\
\mathrm{s.t.}\quad
&\goalTerm{t}=\optimalGoalTerm{t}.
\end{aligned}
\label{eq:secondary_objective}
\end{equation}
Thus, route efficiency and structural reliability break ties among
target-reward-optimal solutions; they cannot be improved by sacrificing
target reward. In the implementation, the two Gurobi objective priorities
use zero absolute and relative degradation tolerances.
```

### Required replacement for the target-uniqueness equation

Replace the current equality by:

```latex
Each target can contribute reward at most once across the team, and a
found target cannot contribute additional reward:
\begin{equation}
\sum_{q\in\agentSet}
\sum_{v\in\rewardVPs{t}{q}}
\targetAssignVar{t}{k}{v}{q}
\le
1-\targetFound{t}{k},
\qquad
\forall k\in\targetSet.
\label{eq:target_assignment_unique}
\end{equation}
```

## 9. Revisions outside the objective subsection

The mathematical correction should be propagated to the prose so that the paper does not continue to imply a compensatory weighted trade-off.

### Abstract

Current idea:

> the MILP explicitly accounts for structural uncertainty while balancing exploration, uncertainty reduction, and task completion.

Recommended replacement:

> The resulting rolling-horizon multi-agent MILP first maximizes target-directed search reward and then, without degrading that reward, minimizes a normalized combination of travel distance, structural risk, and revisits.

### Introduction: method summary

Current idea:

> selects coordinated routes by balancing target likelihood, travel cost, revisits, and structural uncertainty.

Recommended replacement:

> selects coordinated routes through a lexicographic objective that prioritizes target-directed reward and uses travel cost, structural uncertainty, and revisits to discriminate among reward-optimal plans.

### Contribution statement

Recommended replacement:

> We formulate cooperative search as a rolling-horizon MILP with a hierarchical objective: it first maximizes uniquely assigned target-location reward and then minimizes normalized travel, edge-risk, node-risk, and revisit costs while preserving the primary optimum.

### Numerical-experiment implementation details

The current implementation-details paragraph is directionally correct, but it should explicitly state the zero tolerances and the absence of an active goal weight:

> All proposed MLLM variants use the same two-priority target-directed MILP. The primary objective maximizes the unnormalized aggregate target reward constructed from the processed viewpoint-level target probabilities. The secondary objective minimizes normalized route cost using coefficients 0.17, 0.05, 0.03, and 0.30 for travel distance, hypothesized-edge nonexistence, node nonexistence, and revisits, respectively. Both objective-degradation tolerances are zero, so the secondary objective cannot reduce the optimal primary reward. The configured scalar goal coefficient 0.45 is inactive in this target-directed mode.

### Conclusion

Current idea:

> coordinates the agents by balancing target reward, travel distance, structural uncertainty, and repeated visits.

Recommended replacement:

> coordinates the agents by first maximizing target-directed reward and then minimizing travel distance, structural uncertainty, and repeated visits over the set of reward-optimal plans.

## 10. Statements that should not appear after revision

Avoid the following descriptions for the evaluated proposed method:

- "a single weighted objective";
- "a weighted sum of target reward and route costs";
- "the five objective weights sum to one";
- "the target weight is 0.45";
- "the model trades a small reduction in target reward for shorter routes";
- "every active target is forced to be assigned exactly once"; and
- "all objective terms, including goal reward, are normalized before optimization."

Accurate descriptions include:

- "two-priority lexicographic MILP";
- "hierarchical multi-objective MILP";
- "target reward is the primary objective"; and
- "weighted normalized route cost is the secondary tie-breaking objective."

## 11. Important implementation-reporting nuances

### 11.1 The inactive 0.45 goal weight

The configuration retains `goal_weight: 0.45`, and the generic objective-term logging code may display a diagnostic `weighted_contribution` based on this value. This diagnostic does not describe the objective used by the target-directed solver. The paper should derive the mathematical formulation from the active `setObjectiveN` calls, not from the generic contribution report.

### 11.2 Meaning of the saved objective value

Because the model is multi-objective, a saved scalar `objective_value` should not be interpreted as the value of a five-term weighted utility. The scientifically meaningful quantities are the primary target reward, the secondary route cost and its components, and the lexicographic priority order.

### 11.3 Solver semantics

The paper may present (L2) and (L3) as two mathematical stages for clarity. It should immediately clarify that both stages are encoded in one Gurobi model using hierarchical objectives. This prevents readers from incorrectly inferring that the rolling-horizon controller makes two separate external optimization calls or changes the feasible set between stages.

## 12. Final consistency checklist

Before compiling the revised manuscript, verify all of the following:

- [ ] $G^t$ is defined using the assignment variables $a_{k,v,q}^t$.
- [ ] The active target reward uses processed $p_{v,k}^{\mathrm{goal},t}$, not raw MLLM scores.
- [ ] Target assignment is "at most once," not "exactly once."
- [ ] The conditional per-agent assignment constraint is tied to a full distinct-target matching.
- [ ] The node-nonexistence term appears in the term definitions, normalization, objective, and bounds.
- [ ] Goal normalization is absent from the active primary objective.
- [ ] The primary objective is shown before the secondary objective.
- [ ] The secondary problem explicitly preserves $G^{t,*}$.
- [ ] The four reported secondary coefficients are 0.17, 0.05, 0.03, and 0.30.
- [ ] The paper does not require these four coefficients to sum to one.
- [ ] The 0.45 goal coefficient is identified as inactive or omitted entirely.
- [ ] Zero absolute and relative objective-degradation tolerances are stated.
- [ ] Abstract, introduction, contributions, model section, experiment settings, and conclusion all use the same lexicographic interpretation.
- [ ] The single-objective label `eq:weighted_objective` is removed or renamed.
- [ ] No table or caption calls the evaluated formulation a one-layer weighted objective.

## 13. Source locations used for verification

- Active experiment configuration: `config/default_config.json`, optimizer settings.
- Objective construction: `optimization_model/optimizer.py`, especially the target reward at lines 257--287, cost terms at lines 289--312, and hierarchical objectives at lines 384--406.
- Target-assignment constraints: `optimization_model/optimizer.py`, especially lines 516--625.
- Objective bounds: `optimization_model/optimizer.py`, especially lines 1217--1382.
- Solver metadata: `optimization_model/optimizer.py`, especially lines 830--846.
- Persisted experiment evidence: the `optimizer_routes_step_*.json` files under the four proposed-method `mllm_debug_outputs_balanced100_*` directories.
