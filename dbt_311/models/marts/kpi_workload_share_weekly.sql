-- KPI 7: Workload distribution - each agency's share of weekly volume, and its week-over-week change.
with weekly as (
    select agency, week_start, sum(requests_opened) as requests_opened
    from {{ ref('kpi_volume_weekly') }}
    group by 1, 2
),

shares as (
    select
        *,
        requests_opened * 1.0 / sum(requests_opened) over (partition by week_start) as share_of_week
    from weekly
)

select
    *,
    share_of_week - lag(share_of_week) over (partition by agency order by week_start) as share_change_wow
from shares
