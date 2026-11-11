-- KPI 1: Ticket volume - requests opened per week, by agency and problem (complete weeks only)
select
    agency,
    problem,
    date_trunc('week', created_at)::date as week_start,
    count(*)                             as requests_opened
from {{ ref('int_requests_enriched') }}
where date_trunc('week', created_at) + interval 7 day
      <= timestamp '{{ var("snapshot_ts") }}' + interval 1 second
group by 1, 2, 3
