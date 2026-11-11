-- One clean row per service request.
--  * renames API fields to the current 311 labels (complaint_type -> problem, descriptor -> problem_detail)
--  * de-duplicates on request_id with ROW_NUMBER (keeps the most recently closed version)
--  * applies the snapshot: closures after snapshot_ts count as still open
--  * drops rows whose closed date is before their created date (data errors; counted in the notebook)
--  * flags requests whose status is Closed but have no closed date (closed, date unknown)
with src as (
    select * from {{ source('nyc311', 'raw_311') }}
),

typed as (
    select
        cast(unique_key as bigint)                 as request_id,
        cast(created_date as timestamp)            as created_at,
        cast(closed_date as timestamp)             as closed_at_raw,
        agency,
        complaint_type                             as problem,
        descriptor                                 as problem_detail,
        status,
        open_data_channel_type                     as channel,
        nullif(upper(trim(incident_address)), '')  as incident_address,
        incident_zip,
        borough,
        try_cast(latitude as double)               as latitude,
        try_cast(longitude as double)              as longitude
    from src
),

deduped as (
    select
        *,
        row_number() over (
            partition by request_id
            order by closed_at_raw desc nulls last
        ) as row_num
    from typed
)

select
    request_id,
    created_at,
    case when closed_at_raw <= timestamp '{{ var("snapshot_ts") }}' then closed_at_raw end as closed_at,
    (closed_at_raw is null and status = 'Closed')                                          as is_closed_without_date,
    agency,
    problem,
    problem_detail,
    status,
    channel,
    incident_address,
    incident_zip,
    borough,
    latitude,
    longitude,
    -- location used for repeat/duplicate logic: street address + borough, else rounded lat/long (~10 m)
    coalesce(
        incident_address || ' | ' || coalesce(borough, ''),
        case when latitude is not null and longitude is not null
             then cast(round(latitude, 4) as varchar) || ',' || cast(round(longitude, 4) as varchar) end
    ) as location_key
from deduped
where row_num = 1
  and created_at <= timestamp '{{ var("snapshot_ts") }}'
  and (closed_at_raw is null or closed_at_raw >= created_at)
