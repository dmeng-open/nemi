# V3

V3 is the learned ranker. It trains on `recommendation_candidates` and `interaction_events`, then adds another `CandidateRanker`. `HeuristicRanker` stays the baseline. Recall@K and NDCG@K are the comparison before a model replaces that baseline.

That ranker is not in this tree. Single-activity plans still use the heuristic. Multi-part evenings are [V2](../v2/plan.md).
