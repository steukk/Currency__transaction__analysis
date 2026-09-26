# Bottleneck Analysis

## Confirmed Problems

1. Limit checks are a major delay source. `limit_delay` represents 960 deals and has an SLA breach rate of 31.7%.
2. Settlement instructions are not validated early enough. `incomplete_ssi` represents 762 deals and averages 1.17 rework loops.
3. Manual re-entry remains material. Manual processing rate is 50.5%, with 3.33 manual steps per deal on average.
4. Settlement exceptions are lower frequency but high impact. `settlement_fail` represents 347 deals and has an average total time of 313.1 minutes.
5. SLA monitoring is reactive. SLA breach rate is 13.3%, and the process has no dedicated early-warning step in AS-IS.

## Interpretation

The main value of the redesign is not changing FX pricing. It is reducing waiting time, duplicate manual entry, late validation and exception handling effort.
