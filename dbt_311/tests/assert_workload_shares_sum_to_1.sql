-- Each week's agency shares must add to 100%
select week_start, sum(share_of_week) as total_share
from {{ ref('kpi_workload_share_weekly') }}
group by 1
having abs(sum(share_of_week) - 1) > 0.0001
