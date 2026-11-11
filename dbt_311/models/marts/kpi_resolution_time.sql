-- KPI 2: Time to resolution - median and 90th percentile (mean shown only to illustrate skew).
-- GROUPING SETS returns one row per agency+problem plus an agency-wide row (problem = 'ALL').
select
    agency,
    coalesce(problem, 'ALL')                             as problem,
    count(*)                                             as requests_closed,
    round(quantile_cont(resolution_hours, 0.5) / 24, 2)  as median_days,
    round(quantile_cont(resolution_hours, 0.9) / 24, 2)  as p90_days,
    round(avg(resolution_hours) / 24, 2)                 as mean_days
from {{ ref('int_requests_enriched') }}
where resolution_hours is not null
group by grouping sets ((agency, problem), (agency))
