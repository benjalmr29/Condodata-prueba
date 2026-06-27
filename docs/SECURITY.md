# Seguridad

## Capas de protección implementadas

### 1. Autenticación — JWT con expiración

Todos los endpoints (excepto `/health`) requieren un token Bearer válido.
Los tokens incluyen `condominio_id` en el payload y expiran en 8 horas por defecto.

```
POST /auth/login  →  { access_token, token_type }
Authorization: Bearer <token>
```

### 2. Aislamiento de datos — Row-Level Security (PostgreSQL)

Cada tabla en el schema `raw` tiene RLS habilitado. Una query solo puede
leer o escribir filas donde `condominio_id` coincide con
`current_setting('app.condominio_id')`, que se establece al inicio de cada
sesión autenticada via `tenant_session(condominio_id)`.

Esto significa que incluso si hay un bug en la lógica de la API, la base de
datos rechaza el acceso a datos de otros condominios a nivel de motor.

### 3. Privilegios mínimos en PostgreSQL

Cuatro roles con permisos estrictamente necesarios:

| Rol | Permisos |
|---|---|
| `condodata_ingestion` | INSERT/SELECT en `raw.*` y `audit.*` |
| `condodata_api` | SELECT en `staging.*` y `marts.*` |
| `condodata_dbt` | SELECT en `raw.*`, ALL en `staging.*` y `marts.*` |
| `condodata_readonly` | SELECT en `marts.*` |

### 4. Rate limiting

60 requests/minuto por IP por defecto (configurable en `.env`).
Responde con `429 Too Many Requests` y header `Retry-After: 60`.

### 5. Validación de archivos subidos

Antes de procesar cualquier archivo:
- Extensión validada contra lista blanca (`.pdf`, `.xlsx`, `.csv`)
- Magic bytes verificados (el contenido debe corresponder a la extensión)
- Path traversal bloqueado (`../`, rutas absolutas, caracteres especiales)
- Tamaño máximo configurable (default 10 MB)
- Hash SHA-256 calculado para detectar duplicados

### 6. HTTP Security Headers

Agregados por `SecurityHeadersMiddleware` en cada respuesta:

```
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 1; mode=block
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: geolocation=(), microphone=(), camera=()
Cache-Control: no-store
Strict-Transport-Security: max-age=63072000 (solo en producción)
```

El header `Server` se elimina para no exponer información del stack.

### 7. Puertos no expuestos públicamente

En `docker-compose.yml` todos los puertos están bindeados a `127.0.0.1`:

```yaml
ports:
  - "127.0.0.1:5432:5432"   # PostgreSQL — solo localhost
  - "127.0.0.1:8080:8080"   # Airflow — solo localhost
  - "127.0.0.1:3000:3000"   # Metabase — solo localhost
  - "127.0.0.1:8000:8000"   # API — solo localhost
```

En producción, la API queda detrás de un reverse proxy (nginx/Caddy) que
maneja TLS. Los demás servicios nunca se exponen al exterior.

### 8. Contenedores hardened

Todos los contenedores tienen:
- `security_opt: no-new-privileges:true` — impide escalación de privilegios
- El contenedor de la API corre con `read_only: true` y `tmpfs: /tmp`
- Volúmenes montados como `:ro` donde no se necesita escritura

### 9. Secretos

Los secretos nunca tienen valores por defecto. El script
`scripts/generate_secrets.py` genera contraseñas criptográficamente fuertes
y el Fernet key de Airflow. El archivo `.env` está en `.gitignore` y
nunca se commitea.

### 10. Logging de auditoría

Toda actividad queda registrada:
- `audit.ingestion_log` — cada corrida del pipeline con status y hash del archivo
- `security.access_log` — cada request HTTP con usuario, IP y duración
- `security_opt` de PostgreSQL — conexiones, desconexiones, DDL
