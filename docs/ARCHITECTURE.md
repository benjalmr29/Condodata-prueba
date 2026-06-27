# Arquitectura

## Decisiones de diseño

### Bronze / Silver / Gold layers

Los datos siguen un modelo de tres capas:

- **Bronze (raw)**: datos exactamente como llegaron. Nunca se modifican.
  Esquema `raw` en PostgreSQL.
- **Silver (staging)**: limpieza 1:1. Tipos correctos, fechas normalizadas,
  strings sin espacios. Esquema `staging`. Modelos dbt materializados como views.
- **Gold (marts)**: lógica de negocio. Métricas agregadas, cálculos de mora,
  flujo de caja. Esquema `marts`. Modelos dbt materializados como tablas.

### Multi-tenant desde el inicio

Cada registro en las tablas raw incluye `condominio_id`. Las vistas de staging
y los marts filtran por este campo. La API usa JWT con `condominio_id` en el
payload para que cada cliente solo acceda a sus datos.

### Inmutabilidad del raw

La capa bronze es append-only. Si un archivo se reprocesa, se agrega
una nueva entrada con `ingested_at` actualizado. El hash del archivo
(`source_hash`) permite detectar duplicados antes de insertar.

### Orquestación

Airflow corre el pipeline completo una vez al mes, o bajo demanda cuando
el administrador sube un archivo nuevo. El DAG sigue el orden:

```
ingesta → validación GE → dbt run → dbt test → notificación
```

Si cualquier paso falla, el DAG se detiene y envía alerta. No se entregan
datos parciales al dashboard.
