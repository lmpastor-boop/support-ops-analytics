-- KPI 4: SLA attainment - share of requests resolved within the target for their problem type.
-- Requests still open but not yet past their target are excluded (met_sla is NULL).
select
    agency,
    problem,
    date_trunc('month', created_at)::date      as month_start,
    any_value(sla_days)                        as sla_days,
    any_value(sla_note)                        as sla_note,
    count(met_sla)                             as requests_evaluated,
    sum(case when met_sla then 1 else 0 end)   as met_target,
    round(avg(case when met_sla then 1.0 else 0.0 end) filter (where met_sla is not null), 4)
                                               as sla_attainment
from {{ ref('int_requests_enriched') }}
group by 1, 2, 3
