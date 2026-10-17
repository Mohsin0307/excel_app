-- Total opportunities
SELECT COUNT(DISTINCT opp_id) FROM opportunities;

-- Active (not archived) opportunities
SELECT COUNT(*) FROM opportunities WHERE COALESCE(opp_archived, 0) = 0;

-- Opportunities with scholarship
SELECT COUNT(*) FROM opportunities WHERE scholarship_raw IS NOT NULL AND LOWER(TRIM(scholarship_raw)) NOT IN ('','0','0.0','[]','false','nan','no','none','null','{}');

-- Scholarship opportunities by category
SELECT opp_category, SUM(CASE WHEN scholarship_raw IS NOT NULL AND LOWER(TRIM(scholarship_raw)) NOT IN ('','0','0.0','[]','false','nan','no','none','null','{}') THEN 1 ELSE 0 END) FROM opportunities GROUP BY opp_category;

-- Average reward
SELECT AVG(reward_num) FROM opportunities;

-- Top 10 reward values
SELECT reward_num FROM opportunities WHERE reward_num IS NOT NULL ORDER BY reward_num DESC, opp_id LIMIT 10;

-- Lowest 10 reward values
SELECT reward_num FROM opportunities WHERE reward_num IS NOT NULL ORDER BY reward_num ASC, opp_id LIMIT 10;

-- Opportunities created: last 7 active dates
SELECT opp_created, COUNT(*) FROM opportunities WHERE opp_created IS NOT NULL
GROUP BY opp_created ORDER BY opp_created DESC LIMIT 7;

-- New opportunities 2025Q4
SELECT COUNT(*) FROM opportunities WHERE opp_created BETWEEN '2025-10-01' AND '2025-12-31';

-- New opportunities 2026Q1
SELECT COUNT(*) FROM opportunities WHERE opp_created BETWEEN '2026-01-01' AND '2026-03-31';

-- New opportunities 2025Q4
SELECT COUNT(*) FROM opportunities WHERE opp_created BETWEEN '2025-10-01' AND '2025-12-31';

-- New opportunities 2026Q1
SELECT COUNT(*) FROM opportunities WHERE opp_created BETWEEN '2026-01-01' AND '2026-03-31';
