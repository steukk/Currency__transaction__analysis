-- Operational risk event profile.

SELECT
  exception_type,
  COUNT(*) AS deal_count,
  AVG(CASE WHEN sla_breach = true THEN 1 ELSE 0 END) AS sla_breach_rate,
  AVG(rework_count) AS avg_rework_count,
  AVG(manual_steps_count) AS avg_manual_steps
FROM synthetic_deals
GROUP BY exception_type
ORDER BY deal_count DESC;

