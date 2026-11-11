-- KPI 3: Backlog - requests open at the end of each day = running total of (opened - closed).
-- Only requests created since 2024-01-01 are in scope, so early 2024 understates the true backlog (warm-up).
-- Requests with status Closed but no closed date are excluded: they are closed, but we cannot say when.
with days as (
    select cast(d as date) as day
    from generate_series(
        (select min(created_at)::date from {{ ref('int_requests_enriched') }}),
        cast(timestamp '{{ var("snapshot_ts") }}' as date),
        interval 1 day
    ) as t(d)
),

agencies as (
    select distinct agency from {{ ref('int_requests_enriched') }}
),

opened as (
    select agency, created_at::date as day, count(*) as n
    from {{ ref('int_requests_enriched') }}
    where not is_closed_without_date
    group by 1, 2
),

closed as (
    select agency, closed_at::date as day, count(*) as n
    from {{ ref('int_requests_enriched') }}
    where closed_at is not null
    group by 1, 2
)

select
    a.agency,
    d.day,
    coalesce(o.n, 0) as opened,
    coalesce(c.n, 0) as closed,
    sum(coalesce(o.n, 0) - coalesce(c.n, 0)) over (
        partition by a.agency
        order by d.day
        rows between unbounded preceding and current row
    ) as open_backlog
from agencies a
cross join days d
left join opened o on o.agency = a.agency and o.day = d.day
left join closed c on c.agency = a.agency and c.day = d.day
