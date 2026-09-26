-- Stage waiting-time decomposition.

SELECT 'request_to_quote' AS stage, AVG(DATEDIFF('minute', request_time, quote_time)) AS avg_minutes FROM synthetic_deals
UNION ALL
SELECT 'quote_to_accept', AVG(DATEDIFF('minute', quote_time, client_accept_time)) FROM synthetic_deals
UNION ALL
SELECT 'accept_to_limit_check', AVG(DATEDIFF('minute', client_accept_time, limit_check_time)) FROM synthetic_deals
UNION ALL
SELECT 'limit_check_to_capture', AVG(DATEDIFF('minute', limit_check_time, trade_capture_time)) FROM synthetic_deals
UNION ALL
SELECT 'capture_to_confirmation', AVG(DATEDIFF('minute', trade_capture_time, confirmation_time)) FROM synthetic_deals
UNION ALL
SELECT 'confirmation_to_settlement', AVG(DATEDIFF('minute', confirmation_time, settlement_time)) FROM synthetic_deals;

