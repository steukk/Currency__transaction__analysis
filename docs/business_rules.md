# Business Rules

| ID | Rule |
|---|---|
| BRULE-001 | A deal cannot be confirmed when the available client trading limit is insufficient. |
| BRULE-002 | A change to notional, currency pair, value date or direction after client acceptance requires repeated client approval. |
| BRULE-003 | Deals above the high-value threshold require additional Middle Office control. |
| BRULE-004 | A quote expires if the client does not accept within the configured validity window. |
| BRULE-005 | Settlement cannot start until SSI completeness has been validated. |
| BRULE-006 | Retried requests must reuse the original client request reference to prevent duplicate deals. |
