-- KPI 5: Repeat rate - same problem at the same location 1 hour to 30 days after a previous request.
select
    agency,
    date_trunc('month', created_at)::date                   as month_start,
    count(*)                                                as located_requests,
    sum(case when is_repeat_30d then 1 else 0 end)          as repeat_requests,
    round(avg(case when is_repeat_30d then 1.0 else 0.0 end), 4) as repeat_rate
from {{ ref('int_requests_enriched') }}
where location_key is not null
group by 1, 2
