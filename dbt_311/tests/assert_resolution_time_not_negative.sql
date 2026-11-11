-- Closed date must be on or after created date
select request_id, resolution_hours
from {{ ref('int_requests_enriched') }}
where resolution_hours < 0
