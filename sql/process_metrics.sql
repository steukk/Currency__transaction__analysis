-- Process metrics for data/synthetic_deals.csv loaded as table synthetic_deals.
-- Timestamp function names may need minor adjustment depending on SQL engine.

SELECT
  COUNT(*) AS deal_count,
  AVG(DATEDIFF('minute', request_time, settlement_time)) AS avg_total_minutes,
  MEDIAN(DATEDIFF('minute', request_time, settlement_time)) AS median_total_minutes,
  AVG(CASE WHEN sla_breach = false THEN 1 ELSE 0 END) AS sla_met_rate,
  AVG(CASE WHEN manual_processing_flag = false THEN 1 ELSE 0 END) AS stp_rate,
  AVG(CASE WHEN manual_processing_flag = true THEN 1 ELSE 0 END) AS manual_processing_rate,
  AVG(rework_count) AS avg_rework_count,
  AVG(manual_steps_count) AS avg_manual_steps,
  AVG(CASE WHEN rework_count = 0 AND deal_status = 'settled' THEN 1 ELSE 0 END) AS first_pass_yield
FROM synthetic_deals;

