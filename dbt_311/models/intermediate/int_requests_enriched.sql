-- Adds SLA target, resolution time, SLA outcome, and repeat/duplicate flags.
with requests as (
    select * from {{ ref('stg_service_requests') }}
),

sla as (
    select * from {{ ref('sla_targets') }}
),

with_sla as (
    -- problem-specific target if one exists, otherwise the agency default
    select
        r.*,
        coalesce(specific.sla_days, fallback.sla_days) as sla_days,
        coalesce(specific.note, fallback.note)         as sla_note
    from requests r
    left join sla as specific
        on specific.agency = r.agency and specific.problem = r.problem
    left join sla as fallback
        on fallback.agency = r.agency and fallback.problem = '*default*'
),

with_prev as (
    -- previous request for the same problem at the same location
    select
        *,
        lag(created_at) over (
            partition by location_key, problem
            order by created_at, request_id
        ) as prev_same_location_problem_at
    from with_sla
)

select
    *,
    case when closed_at is not null
         then (epoch(closed_at) - epoch(created_at)) / 3600.0 end            as resolution_hours,
    closed_at is null and not is_closed_without_date                          as is_open_at_snapshot,
    -- SLA outcome: TRUE met, FALSE breached (closed late, or still open past target),
    -- NULL = open and not yet due, or closed with an unknown date
    case
        when is_closed_without_date then null
        when closed_at is not null
            then (epoch(closed_at) - epoch(created_at)) / 86400.0 <= sla_days
        when created_at + to_days(cast(sla_days as integer)) < timestamp '{{ var("snapshot_ts") }}'
            then false
    end                                                                       as met_sla,
    coalesce(location_key is not null
             and created_at - prev_same_location_problem_at <= interval 1 hour, false)
                                                                              as is_duplicate_1h,
    coalesce(location_key is not null
             and created_at - prev_same_location_problem_at >  interval 1 hour
             and created_at - prev_same_location_problem_at <= interval 30 day, false)
                                                                              as is_repeat_30d
from with_prev
