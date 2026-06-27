with source as (
    select * from {{ source('raw', 'bank_transactions') }}
),

renamed as (
    select
        id,
        condominio_id,
        source_file,
        ingested_at,
        raw_date::date                              as fecha,
        trim(raw_description)                       as descripcion,
        replace(raw_amount, ',', '.')::numeric(12,2) as monto,
        raw_reference                               as referencia,
        page_number,
        row_number
    from source
    where raw_date is not null
      and raw_amount is not null
)

select * from renamed
