# CondoData Platform

![CI](https://github.com/TU_USUARIO/condodata/actions/workflows/ci.yml/badge.svg)
![dbt](https://img.shields.io/badge/dbt-1.7-orange)
![Python](https://img.shields.io/badge/python-3.11-blue)
![License](https://img.shields.io/badge/license-MIT-green)

Pipeline de datos end-to-end para administración financiera de condominios.
Transforma estados de cuenta, registros de cuotas y comprobantes de gastos en
reportes automatizados y dashboards en tiempo real.

## Stack

| Capa | Tecnología |
|---|---|
| Ingesta | Python 3.11 · pdfplumber · pandas |
| Orquestación | Apache Airflow 2.8 |
| Transformación | dbt-core 1.7 · PostgreSQL 16 |
| Calidad | Great Expectations · dbt tests |
| Serving | FastAPI · Metabase |
| Infraestructura | Docker · Terraform · AWS |
| CI/CD | GitHub Actions |

## Inicio rápido

```bash
cp .env.example .env
make up
```

Servicios disponibles:

- Airflow UI → http://localhost:8080
- Metabase → http://localhost:3000
- API docs → http://localhost:8000/docs

## Estructura

```
condodata/
├── ingestion/        extractores por fuente de datos
├── dbt/              modelos de transformación SQL
├── orchestration/    DAGs de Airflow
├── api/              endpoints FastAPI
├── quality/          suites de Great Expectations
├── infra/            configuración Terraform
└── tests/            pruebas unitarias e integración
```

## Comandos

```bash
make up           levantar stack completo
make down         detener stack
make test         correr tests
make dbt-run      ejecutar modelos dbt
make dbt-test     ejecutar tests dbt
make lint         verificar calidad de código
```

## Desarrollo

Ver [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) para guía de contribución y
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) para decisiones de diseño.
