-- KPI 6: Duplicates - same problem at the same location within 1 hour of a previous request
-- (usually several people reporting the same incident).
select
    agency,
    date_trunc('month', created_at)::date                     as month_start,
    count(*)                                                  as located_requests,
    sum(case when is_duplicate_1h then 1 else 0 end)          as duplicate_requests,
    round(avg(case when is_duplicate_1h then 1.0 else 0.0 end), 4) as duplicate_rate
from {{ ref('int_requests_enriched') }}
where location_key is not null
group by 1, 2
