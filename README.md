# PROMOTICK-AUTH

Módulo serverless de **identidad y gestión de usuarios** del backend de
Promotick. Expone 7 operaciones sobre AWS Lambda + API Gateway HTTP API v2:

| Op                            | Método / Path                       | Quién puede invocarla | CU asociado |
|-------------------------------|-------------------------------------|-----------------------|-------------|
| Login                         | `POST /auth/login`                  | Público               | CU001       |
| Completar password inicial    | `POST /auth/complete-new-password`  | Público (con session) | CU001       |
| Iniciar recuperación de pass  | `POST /auth/forgot-password`        | Público               | CU001       |
| Confirmar nueva contraseña    | `POST /auth/confirm-forgot-password`| Público (con código)  | CU001       |
| Crear usuario                 | `POST /users`                       | Solo `ADMIN`          | CU003       |
| Listar usuarios               | `GET  /users`                       | Solo `ADMIN`          | CU003       |
| Actualizar usuario            | `PATCH /users/{user_id}`            | Solo `ADMIN`          | CU003       |

> La autenticación está **completamente delegada a AWS Cognito**. Este módulo
> NO almacena contraseñas; solo persiste el perfil del usuario en la tabla
> `promotick_users` (DynamoDB) y orquesta las llamadas a Cognito.

> Existe una colección Postman lista para usar en
> [`Promotick-Auth.postman_collection.json`](./Promotick-Auth.postman_collection.json).
> Impórtala en Postman y reemplaza la base URL por la salida de
> `serverless deploy` (`endpoints` → `httpApi`).

---

## 1. Arquitectura — hexagonal ligera (ports & adapters)

```
┌─────────────────────────────────────────────────────────────┐
│  handlers/   (entry points Lambda — wiring en cold start)   │
│      │                                                       │
│      ▼                                                       │
│  domain/services   ←──────  domain/ports (Protocol)         │
│      │                              ▲                        │
│      ▼                              │                        │
│  domain/user (dataclass)            │                        │
│                                     │                        │
│                            adapters/ (boto3, Cognito, Dynamo)│
└─────────────────────────────────────────────────────────────┘
```

**Regla de oro:** `domain/` **no** importa `boto3`, `requests` ni ningún SDK.
Si un servicio necesita I/O, declara un `Protocol` en `domain/ports.py` y el
handler inyecta la implementación concreta.

### Capas

| Capa       | Carpeta              | Puede importar de                  | NO puede importar de |
|------------|----------------------|------------------------------------|----------------------|
| Entidades  | `src/domain/user.py` | nada externo                       | adapters, SDKs       |
| Puertos    | `src/domain/ports.py`| `domain/`                          | adapters, SDKs       |
| Servicios  | `src/domain/services.py` | `domain/`                      | adapters, SDKs       |
| Adapters   | `src/adapters/`      | `domain/`, `boto3`                 | handlers             |
| Handlers   | `src/handlers/`      | `domain/`, `adapters/`             | (evitar boto3 directo) |

---

## 2. Estructura de archivos

```
promotick-auth/
├── serverless.yml                      # Deploy: 7 Lambdas + JWT authorizer + Cognito (vía include)
├── infrastructure/
│   └── cognito.yml                     # User Pool + App Client + Groups (incluido vía ${file(...)})
├── Promotick-Auth.postman_collection.json   # colección lista para probar la API
├── README.md                           # este archivo
└── src/
    ├── handlers/
    │   ├── login.py                    # CU001 — login (con rate limiting)
    │   ├── complete_new_password.py    # CU001 — completar password inicial
    │   ├── forgot_password.py          # CU001 — iniciar recuperación
    │   ├── confirm_forgot_password.py  # CU001 — confirmar nueva contraseña
    │   ├── create_user.py              # CU003 — crear (Cognito + Dynamo)
    │   ├── list_users.py               # CU003 — listar
    │   └── update_user.py              # CU003 — actualizar (rol, estado, nombre)
    ├── shared/
    │   ├── http.py                     # helpers: json_response, parse_body, claims, require_admin
    │   └── audit.py                    # audit_log + helpers de target_key
    ├── domain/
    │   ├── user.py                     # @dataclass(frozen=True) User + invariantes
    │   ├── ports.py                    # UserRepository, AuthProvider, LoginRateLimiter, errores
    │   └── services.py                 # LoginService, ForgotPasswordService, CreateUserService, …
    └── adapters/
        ├── dynamo_user_repository.py
        ├── dynamo_audit_log_repository.py
        ├── dynamo_login_rate_limiter.py    # cuenta fallos en audit_logs (RNF rate limiting)
        ├── strict_email_validator.py
        └── cognito_auth_adapter.py
```

---

## 3. Infraestructura

Este módulo es **dueño** de Cognito (User Pool + App Client + Groups). La tabla
`promotick_users` y demás recursos compartidos viven en `promotick-infra` y se
consumen vía CloudFormation Outputs.

| Recurso             | Origen                                            | Var de entorno         |
|---------------------|---------------------------------------------------|------------------------|
| Tabla `promotick_users` | `${cf:promotick-infra-dynamodb.UsersTableName}` (externo) | `USERS_TABLE_NAME`     |
| Cognito User Pool   | `Ref: PromotickUserPool` (este stack)             | `USER_POOL_ID`         |
| Cognito App Client  | `Ref: PromotickUserPoolClient` (este stack)       | `USER_POOL_CLIENT_ID`  |
| IAM role            | `arn:aws:iam::${AWS::AccountId}:role/LabRole`     | (no aplica)            |

### Outputs expuestos a otros módulos

Otros repos (`promotick-products`, `-suppliers`, etc.) consumen el User Pool
con `${cf:promotick-auth-${stage}.<Output>}`:

- `UserPoolId`
- `UserPoolArn`
- `UserPoolClientId`

### Modelo de la tabla `promotick_users`

- **Partition Key:** `user_id` (uuid v4 interno).
- **GSI 1 — `by_email`:** PK `email` (lookup login y unicidad).
- **GSI 2 — `by_cognito_sub`:** PK `cognito_sub` (lookup desde claims JWT).
- **Campos:** `user_id, email, full_name, cognito_sub, role, is_active, created_at, updated_at`.
- **No** guarda credenciales — Cognito es la única fuente.

---

## 4. Reglas de negocio implementadas

| RN / Restricción                                                              | Dónde se aplica                                |
|-------------------------------------------------------------------------------|------------------------------------------------|
| Roles válidos: `ADMIN`, `EJEC`, `VIEWER` (estáticos, inmutables)             | `domain/user.py::VALID_ROLES`                  |
| Rol obligatorio al crear                                                     | `User.new()` valida vía `_validate_role`       |
| Solo `ADMIN` puede crear / listar / actualizar usuarios                       | `handlers/_http.py::require_admin`             |
| Email único en el sistema                                                     | `CreateUserService.create` + GSI `by_email` + `UsernameExistsException` |
| Auto-bloqueo: un ADMIN no puede desactivarse a sí mismo                       | `UpdateUserService.update`                     |
| Login rechaza usuarios `is_active=False` aunque Cognito autorice              | `LoginService.login`                           |
| Idempotencia al crear (ConditionExpression sobre `user_id`)                   | `DynamoUserRepository.save_if_absent`          |
| Update solo si el `user_id` existe (no upsert silencioso)                     | `DynamoUserRepository.update`                  |
| Admin no digita contraseñas — Cognito envía email de bienvenida              | `CognitoAuthAdapter.admin_create_user` (`DesiredDeliveryMediums=EMAIL`) |
| **RNF — Rate limiting**: 5 intentos fallidos en 1 min ⇒ bloqueo 5 min por cuenta | `LoginService.login` + `DynamoLoginRateLimiter` (consulta `audit_logs`) |
| Toda operación auditada (éxito / fallo / blocked) en tabla `audit_logs` con TTL 365d | `shared/audit.py::audit_log` en cada handler |

---

## 5. Contratos HTTP

Todos los endpoints autenticados esperan `Authorization: Bearer <access_token>`
(el `access_token` que devuelve `/auth/login`). Los públicos no llevan auth.

Los ejemplos de request / response que siguen están **tomados de la colección
Postman** (`Promotick-Auth.postman_collection.json`).

---

### 5.1 POST `/auth/login`  *(público)*

Autentica a un usuario contra Cognito y devuelve tokens JWT + perfil.

**Request**
```http
POST /auth/login
Content-Type: application/json
```
```json
{
  "email": "admin@gmail.com",
  "password": "@dm1n12345"
}
```

**Response — 200 OK**
```json
{
  "tokens": {
    "id_token": "eyJraWQiOiJDSXplUElxVm5x...",
    "access_token": "eyJraWQiOiJJSDRjcHFhMnkr...",
    "refresh_token": "eyJjdHkiOiJKV1QiLCJlbmM...",
    "expires_in": 3600,
    "token_type": "Bearer"
  },
  "user": {
    "user_id": "5c0b47fc-269f-49ef-ac1a-3a535b3e5125",
    "cognito_sub": "84c804e8-70f1-705f-b818-1f0a1144e117",
    "email": "admin@gmail.com",
    "full_name": "Promotick Admin",
    "role": "ADMIN",
    "is_active": true,
    "created_at": "2026-05-19T07:41:50Z",
    "updated_at": "2026-05-19T07:41:50Z"
  }
}
```

**Response — 200 OK (challenge: cambiar contraseña inicial)**
```json
{
  "challenge": "NEW_PASSWORD_REQUIRED",
  "session": "AYABeLkOrg7uJRMlttK0hbY...",
  "email": "user@gmail.com",
  "message": "Se requiere establecer una nueva contraseña"
}
```
> El cliente debe llamar a `POST /auth/complete-new-password` con
> `email`, `new_password` y el `session` recibido.

**Response — 429 Too Many Requests** *(RNF rate limiting)*
```http
HTTP/1.1 429 Too Many Requests
retry-after: 279
Content-Type: application/json
```
```json
{
  "error": "Demasiados intentos fallidos. Vuelve a intentar en 279 segundos",
  "retry_after": 279
}
```
> Se dispara cuando se detectan ≥ 5 fallos de login en una ventana de 60 s
> para el mismo email. El bloqueo dura 5 min desde el 5° fallo. El servidor
> devuelve el header HTTP estándar `Retry-After` con los segundos restantes.

**Otros errores**

| Código | Cuándo                                                  | Body                                                |
|--------|---------------------------------------------------------|-----------------------------------------------------|
| 400    | JSON malformado, falta `email` o `password`            | `{ "error": "..." }`                                |
| 401    | Credenciales inválidas                                  | `{ "error": "Credenciales inválidas" }`            |
| 403    | Usuario `is_active=false` aunque Cognito autorizó      | `{ "error": "Usuario inactivo" }`                  |
| 404    | Cognito autorizó pero no hay perfil en DynamoDB         | `{ "error": "...no tiene perfil en el sistema" }`  |

---

### 5.2 POST `/auth/complete-new-password`  *(público, requiere `session`)*

Completa el reto `NEW_PASSWORD_REQUIRED` devuelto por `/auth/login` cuando
el usuario inicia sesión con su contraseña temporal por primera vez.

**Request**
```http
POST /auth/complete-new-password
Content-Type: application/json
```
```json
{
  "email": "user@gmail.com",
  "new_password": "user@080112",
  "session": "AYABeLkOrg7uJRMlttK0hbY..."
}
```

**Response — 200 OK**

Mismo shape que `/auth/login` 200 OK (`tokens` + `user`).

**Errores**

| Código | Causa                                                          |
|--------|----------------------------------------------------------------|
| 400    | JSON malformado, falta `email`/`new_password`/`session`, contraseña no cumple política |
| 401    | `session` expirado o inválido                                  |
| 403    | Usuario `is_active=false`                                      |
| 404    | El email no tiene perfil en DynamoDB                           |

---

### 5.3 POST `/auth/forgot-password`  *(público)*

Inicia el flujo de recuperación: Cognito envía un código de 6 dígitos al
correo del usuario.

**Request**
```http
POST /auth/forgot-password
Content-Type: application/json
```
```json
{ "email": "user@gmail.com" }
```

**Response — 200 OK**
```json
{
  "message": "Si el correo está registrado, recibirás un código de verificación de 6 dígitos en los próximos minutos."
}
```
> El mensaje es **deliberadamente genérico** para no filtrar la existencia
> de cuentas (enumeración).

**Errores**

| Código | Causa                              |
|--------|------------------------------------|
| 400    | JSON malformado o `email` vacío    |

---

### 5.4 POST `/auth/confirm-forgot-password`  *(público)*

Confirma el código recibido por correo y establece la nueva contraseña.

**Request**
```http
POST /auth/confirm-forgot-password
Content-Type: application/json
```
```json
{
  "email": "user@gmail.com",
  "code": "349412", #dado por cognito
  "new_password": "user@2358"
}
```

**Response — 200 OK**
```json
{ "message": "Contraseña actualizada correctamente, ya puedes iniciar sesión" }
```

**Errores**

| Código | Causa                                                       |
|--------|-------------------------------------------------------------|
| 400    | JSON malformado, faltan campos, código inválido / expirado, contraseña no cumple política |
| 401    | Solicitud no autorizada por Cognito                         |
| 404    | El email no existe                                          |

---

### 5.5 POST `/users`  *(Bearer JWT — solo rol `ADMIN`)*

Crea un usuario en Cognito y persiste su perfil en DynamoDB. Cognito envía
automáticamente un email de bienvenida con la contraseña temporal.

**Request**
```http
POST /users
Authorization: Bearer <access_token de un ADMIN>
Content-Type: application/json
```
```json
{
  "email": "user@gmail.com",
  "full_name": "EjecutivoDemo",
  "role": "EJEC"
}
```

**Response — 201 Created**
```json
{
  "user": {
    "user_id": "3b8ad7ab-f6a3-47b1-bcdc-d2460d10a6c4",
    "cognito_sub": "...",
    "email": "user@gmail.com",
    "full_name": "EjecutivoDemo",
    "role": "EJEC",
    "is_active": true,
    "created_at": "2026-05-19T08:15:22Z",
    "updated_at": "2026-05-19T08:15:22Z"
  }
}
```

**Errores**

| Código | Causa                                                                                |
|--------|--------------------------------------------------------------------------------------|
| 400    | Falta `email` / `role` / `full_name`, email inválido (formato / dominio sin MX), rol distinto de `ADMIN`/`EJEC`/`VIEWER` |
| 403    | JWT no pertenece a un usuario del grupo `ADMIN`                                      |
| 409    | El email ya está registrado                                                          |

---

### 5.6 GET `/users`  *(Bearer JWT — solo rol `ADMIN`)*

Lista usuarios del sistema. Acepta `?limit=<int>` (default 50, máx 1000).

**Request**
```http
GET /users?limit=100
Authorization: Bearer <access_token de un ADMIN>
```

**Response — 200 OK**
```json
{
  "users": [
    {
      "user_id": "5c0b47fc-269f-49ef-ac1a-3a535b3e5125",
      "email": "admin@gmail.com",
      "full_name": "Promotick Admin",
      "role": "ADMIN",
      "is_active": true,
      "created_at": "2026-05-19T07:41:50Z",
      "updated_at": "2026-05-19T07:41:50Z"
    }
  ],
  "count": 1
}
```

**Errores**

| Código | Causa                                          |
|--------|------------------------------------------------|
| 403    | JWT no pertenece a un usuario del grupo `ADMIN`|

---

### 5.7 PATCH `/users/{user_id}`  *(Bearer JWT — solo rol `ADMIN`)*

Actualiza un usuario. Todos los campos del body son opcionales; si se cambia
`role`, se sincroniza el grupo de Cognito. Si se cambia `is_active`, se
habilita/deshabilita al usuario en Cognito.

**Request — cambiar rol**
```http
PATCH /users/3b8ad7ab-f6a3-47b1-bcdc-d2460d10a6c4
Authorization: Bearer <access_token de un ADMIN>
Content-Type: application/json
```
```json
{ "role": "VIEWER" }
```

**Request — desactivar usuario**
```http
PATCH /users/3b8ad7ab-f6a3-47b1-bcdc-d2460d10a6c4
Authorization: Bearer <access_token de un ADMIN>
Content-Type: application/json
```
```json
{ "is_active": false }
```

**Request — actualizar varios campos a la vez**
```json
{
  "full_name": "Nuevo Nombre",
  "role": "VIEWER",
  "is_active": true
}
```

**Response — 200 OK**
```json
{
  "user": {
    "user_id": "3b8ad7ab-f6a3-47b1-bcdc-d2460d10a6c4",
    "cognito_sub": "...",
    "email": "user@gmail.com",
    "full_name": "EjecutivoDemo",
    "role": "VIEWER",
    "is_active": true,
    "created_at": "2026-05-19T08:15:22Z",
    "updated_at": "2026-05-19T08:42:11Z"
  }
}
```

**Errores**

| Código | Causa                                                                                 |
|--------|---------------------------------------------------------------------------------------|
| 400    | `user_id` ausente, rol inválido, `is_active` no es boolean (`true`/`false`)          |
| 403    | JWT no pertenece a un ADMIN **o** un ADMIN intenta desactivarse a sí mismo            |
| 404    | El `user_id` no existe                                                                |

---

### 5.8 Auditoría

Todas las operaciones (incluyendo intentos fallidos y bloqueos por rate
limiting) se registran en la tabla `promotick_<stage>_audit_logs` con TTL
de 365 días. Campos relevantes:

| Campo         | Ejemplo                                                  |
|---------------|----------------------------------------------------------|
| `event_id`    | UUID v4 (PK)                                             |
| `target_key`  | `email#elmervssz01@gmail.com` o `user#<uuid>` o `users#list` |
| `created_at`  | ISO-8601 con ms (SK del GSI `by_target_created`)         |
| `event_type`  | `auth.login`, `auth.complete_new_password`, `user.created`, `user.updated`, `user.listed`, `auth.forgot_password.start`, `auth.forgot_password.confirm` |
| `status`      | `success` / `failed` / `denied` / `challenge` / `blocked`|
| `status_code` | el código HTTP devuelto                                  |
| `actor_id` / `actor_email` | extraídos del JWT cuando aplica             |
| `ip` / `user_agent` / `http_method` / `path` | request context           |
| `metadata`    | dict con detalles específicos del evento                 |
| `expires_at`  | epoch para el TTL                                        |

El rate limiter (`DynamoLoginRateLimiter`) **reutiliza esta tabla**: consulta
el GSI `by_target_created` filtrando `event_type=auth.login` y `status=failed`
en los últimos 5 min para decidir si bloquea.

---

## 6. Desarrollo local

Aún no hay setup local (sin `requirements*.txt`, sin `pytest.ini`, sin
`.env.example`). El deploy se hace directo desde la EC2 con `LabRole` — ver
sección 7.

Convención clave (sigue aplicando):
- Wiring de dependencias **siempre a nivel de módulo** en el handler (cold
  start optimization). Nada de instanciar adapters dentro del `def handler`.

---

## 7. Deploy

El deploy NO corre desde laptops ni desde GitHub Actions externo. Corre desde
una EC2 dentro de la cuenta AWS con `LabRole` como instance profile:

```bash
# en la EC2 (LabRole asumido automáticamente)
serverless deploy --stage dev
```

Pre-requisito: la stack `promotick-infra` ya desplegada con la tabla
`promotick_users`. Cognito vive en este mismo stack — no hace falta nada
externo.

---

## 8. Anti-patrones — rechazar

- Importar `boto3` desde `src/domain/*`.
- Crear roles IAM propios — usar SIEMPRE `LabRole`.
- Crear la tabla DynamoDB desde este repo — vive en `promotick-infra`. (El
  User Pool sí vive aquí, en `infrastructure/cognito.yml`.)
- Llamar a otra Lambda con `boto3.client("lambda").invoke(...)` — usar API Gateway / EventBridge.
- Hardcodear `USERS_TABLE_NAME`, `USER_POOL_ID`, etc. — siempre por `os.environ`.
- Permitir creación de usuario con rol distinto a `ADMIN / EJEC / VIEWER`.
- Saltarse `ConditionExpression` en escrituras "crear si no existe".
- Quitar `DeletionPolicy: Retain` / `UpdateReplacePolicy: Retain` del User Pool
  — borraría a todos los usuarios reales si alguien hace `serverless remove`.

---

## 9. Bloque MCP — contexto para IA / nuevos contribuyentes

> Si eres una IA (Claude, Copilot, Cursor, …) o un humano nuevo: lee este
> bloque ANTES de proponer cambios. Aquí está condensado el contexto que
> evita errores típicos.

### 9.1 Identidad del módulo

- **Nombre:** `promotick-auth`
- **Propósito:** módulo de identidad — login + gestión de usuarios (ABM) del
  sistema Promotick. **Dueño** de Cognito (User Pool + App Client + Groups).
- **Stack:** Python 3.12, AWS Lambda, API Gateway (HTTP API v2), DynamoDB
  (consumida), Cognito (creada aquí), Serverless Framework. Región fija
  `us-east-1`.
- **Restricción de cuenta:** AWS Academy Learner Lab — solo `LabRole`, sin
  crear roles nuevos. Credenciales expiran cada ~4h.
- **Tipo de repo:** uno entre varios (`promotick-products`, `-suppliers`,
  `-uploads`, `-exports`, …). NO se comunica con otros repos por
  `lambda.invoke`; solo vía API Gateway / EventBridge.

### 9.2 Reglas no negociables

1. **Capa `domain/` libre de SDKs.** Si un servicio necesita I/O, agrega un
   `Protocol` en `domain/ports.py` e inyéctalo desde el handler.
2. **Roles válidos = `{ADMIN, EJEC, VIEWER}`.** Si necesitas otro rol, primero
   se actualiza `documento_de_analisis.md` y `RN-0004`. NO añadir roles
   dinámicamente.
3. **Solo ADMIN crea/edita/lista usuarios.** Enforcement en el handler vía
   `require_admin(event)` leyendo `cognito:groups` / `custom:role` del JWT.
4. **Cognito es la única fuente de credenciales.** DynamoDB guarda perfil,
   no contraseñas, no hashes.
5. **Idempotencia en escrituras** — `ConditionExpression` siempre. Manejar
   `ConditionalCheckFailedException` devolviendo bool o excepción tipada;
   nunca dejarla escapar como 500.
6. **Wiring a nivel de módulo** en el handler (fuera de `def handler`). Esto
   amortiza el cold start.
7. **Variables vía `serverless.yml → environment → os.environ[...]`.**
   Nombres: `USERS_TABLE_NAME`, `USER_POOL_ID`, `USER_POOL_CLIENT_ID`.
8. **Cognito vive en este repo.** El User Pool, App Client y Groups están en
   `infrastructure/cognito.yml`, incluido desde `serverless.yml`. Otros stacks
   lo consumen vía `${cf:promotick-auth-${stage}.UserPoolId}` etc.

### 9.3 Mapa rápido: dónde tocar qué

| Quieres…                                       | Edita                                            |
|------------------------------------------------|--------------------------------------------------|
| Cambiar reglas de negocio (validaciones)       | `src/domain/services.py` / `src/domain/user.py`  |
| Añadir un nuevo dato persistido                | entidad → adapter (`_to_item`/`_from_item`) → migración en `promotick-infra` |
| Añadir una nueva consulta (ej. `by_role`)      | añadir GSI en `promotick-infra` → método en `ports.UserRepository` → impl en `dynamo_user_repository.py` → servicio |
| Añadir un nuevo endpoint                       | nuevo `src/handlers/<op>.py` + entrada en `serverless.yml` `functions:` |
| Cambiar permisos de un endpoint                | `serverless.yml` (authorizer) + `require_admin` / lógica de claims |
| Bug en respuesta HTTP                          | `src/handlers/_http.py` o el handler concreto    |
| Bug en integración con Cognito                 | `src/adapters/cognito_auth_adapter.py`           |
| Bug en persistencia                            | `src/adapters/dynamo_user_repository.py`         |

### 9.4 Receta: añadir una operación nueva

1. **Modelo de datos.** ¿La operación necesita un acceso que el GSI actual
   no soporta? Antes de codear, propón el GSI en `promotick-infra`
   (`infrastructure/cloudformation/01-dynamodb.yml`).
2. **Puerto.** Añade el método al `Protocol` correspondiente en
   `domain/ports.py`.
3. **Servicio.** Caso de uso en `domain/services.py`. Solo lógica, sin AWS.
4. **Adapter.** Implementa el método del puerto en `adapters/`. Aquí va `boto3`.
5. **Handler.** Cableo + traducción de evento en `src/handlers/<op>.py`.
   Reusa `_http.json_response`, `parse_body`, `require_admin`.
6. **Serverless.** Registra la función en `serverless.yml` con su trigger y
   `authorizer: cognitoJwt` si requiere autenticación.
7. **Tests.** (Pendiente: aún no hay suite local configurada.)

### 9.5 Anti-patrones — la IA debe detenerse y preguntar si le piden:

- "Importa `boto3` en `services.py` para ahorrar líneas." → No.
- "Crea una tabla DynamoDB nueva en este repo." → No, va en `promotick-infra`.
- "Llama a la Lambda de products con `boto3.invoke`." → No, vía API/EventBridge.
- "Hardcodea `promotick_users` para acelerar." → No, va por env.
- "Agrega el rol `SUPERVISOR` rápidamente." → No, los roles son estáticos
  por RN-0004; primero se actualiza el doc de análisis.
- "Permite que cualquier usuario autenticado liste usuarios." → No, solo ADMIN.
- "Crea un IAM role nuevo para este Lambda." → No, `LabRole` siempre.
- "Activa `ALLOW_USER_PASSWORD_AUTH` o `ALLOW_USER_SRP_AUTH` en el App Client."
  → No, solo `ALLOW_ADMIN_USER_PASSWORD_AUTH` + `ALLOW_REFRESH_TOKEN_AUTH`.
- "Saca `DeletionPolicy: Retain` del User Pool, es ruido." → No, protege a
  los usuarios reales de un `serverless remove` accidental.
- "Pon un trigger PostConfirmation en Cognito." → No mientras el flujo sea
  admin-create-only; el perfil ya se persiste en `CreateUserService.create`.

### 9.6 Archivos a leer antes de proponer cambios

1. `intrucciones.md` — convenciones globales del backend Promotick.
2. `documento_de_analisis.md` — CUs (CU001, CU003), RNs (RN-0001..RN-0004),
   actores (Administrador / Ejecutivo / Visualizador).
3. `README.md` (este archivo) — específico de `promotick-auth`.
4. `serverless.yml` — qué Lambdas existen, qué env consumen.

### 9.7 Glosario corto

- **Cognito sub:** identificador único e inmutable del usuario en el User
  Pool. Se persiste en `cognito_sub` para correlacionar el JWT con el perfil.
- **JWT claims (HTTP API v2):** disponibles en
  `event.requestContext.authorizer.jwt.claims`. Helper: `_http.claims(event)`.
- **`LabRole`:** único rol IAM permitido en la cuenta Academy. Todas las
  Lambdas lo asumen.
- **`promotick-infra`:** repo "raíz" que crea las 13 tablas DynamoDB y el
  Cognito User Pool. Expone Outputs que este repo consume.
