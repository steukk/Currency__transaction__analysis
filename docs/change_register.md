# Change Register

| AS-IS problem | TO-BE change | Requirement | Metric |
|---|---|---|---|
| Repeated manual entry | Automatic transfer of accepted deal data to trade capture | FR-004 | Manual processing rate, manual steps per deal |
| Late limit check | Pre-trade limit check before trader quote request | FR-002 | Rejected-after-quote rate, quote effort lost |
| Incomplete settlement instructions | Mandatory SSI validation in request form | FR-001 | Rework rate, settlement fail rate |
| No SLA early warning | SLA timer and notification service | FR-006 | SLA breach rate |
| Standard and problem deals share one route | Exception queue with owner, type and due time | FR-005 | Exception aging, first pass yield |
| Duplicate client requests | Idempotent request handling and single deal ID | FR-003, NFR-003 | Duplicate request rate |
