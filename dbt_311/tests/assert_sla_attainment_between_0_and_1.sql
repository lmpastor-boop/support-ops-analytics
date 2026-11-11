select * from {{ ref('kpi_sla_attainment_monthly') }}
where sla_attainment < 0 or sla_attainment > 1
