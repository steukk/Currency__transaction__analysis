# AS-IS Metrics

| Metric | Value |
|---|---:|
| Deal count | 10,000 |
| Average total processing time, minutes | 136.4 |
| Median total processing time, minutes | 118.1 |
| SLA met rate | 86.7% |
| SLA breach rate | 13.3% |
| STP rate | 49.5% |
| Manual processing rate | 50.5% |
| Average rework count | 0.31 |
| Registration error rate | 5.0% |
| Settlement issue rate | 3.5% |
| Average manual steps per deal | 3.33 |
| Average processing cost, USD | 44.29 |
| First Pass Yield | 69.3% |

## Time Decomposition

| stage | avg_minutes | median_minutes | p90_minutes | share_of_total_wait |
| --- | --- | --- | --- | --- |
| request_to_quote | 9.63 | 8.12 | 18.74 | 0.07 |
| quote_to_accept | 19.15 | 13.03 | 32.49 | 0.14 |
| accept_to_limit_check | 17.97 | 9.42 | 35.74 | 0.13 |
| limit_check_to_capture | 25.67 | 16.78 | 59.31 | 0.19 |
| capture_to_confirmation | 20.84 | 15.02 | 38.87 | 0.15 |
| confirmation_to_settlement | 43.11 | 32.22 | 74.34 | 0.32 |

The largest average waiting block is `confirmation_to_settlement` at 43.1 minutes.
