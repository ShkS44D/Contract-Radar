# Observed-risk score (formula version 1.0)

Only completed scans have a score, grade, risk, or breakdown. A score is a summary of observed findings, not assurance that a contract is safe.

1. Deduplicate canonical rule IDs and overlapping source evidence.
2. Severity weights: critical 35, high 22, medium 10, low 4, info 0, gas 0.
3. Confidence factors: high 1.0, medium 0.75, low 0.5.
4. Group by canonical rule ID and sort weighted instances descending.
5. For each group, `penalty = min(1.5 * max_severity_weight, sum(weighted_instance_i / sqrt(i)))`, with i starting at 1. Round group penalties to four decimal places for reproducible report arithmetic.
6. `score = clamp(round(100 - min(100, sum(group_penalties))), 0, 100)` using Python round (ties to even).

Grades/risk bands: A/Low >=90, B/Moderate >=80, C/Elevated >=70, D/High >=60, F/Very high below 60. Presence of any critical finding forces Critical risk; a high finding imposes at least High risk. Grade remains formula-derived. Report both so a favorable numeric score cannot obscure a material finding.

Example: one high/high-confidence finding deducts 22 (score 78, grade C, High risk). Repeated findings of that same rule can deduct at most 33 (score floor 67 from that rule alone). Distinct issue types can still reduce the score to zero. Informational/gas findings are shown but do not deduct points.

Capability detectors and native Slither findings share this model; their conservative confidence matters. Findings not discovered by the engines cannot affect the score. Always read evidence, remediation, scan warnings, and limitations alongside the numeric result.
