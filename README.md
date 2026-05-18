# promotick-auth

Módulo serverless de **identidad y gestión de usuarios** del backend de
Promotick. Expone 4 operaciones sobre AWS Lambda + API Gateway:

| Op            | Método / Path           | Quién puede invocarla | CU asociado |
|---------------|-------------------------|-----------------------|-------------|
| Login         | `POST /auth/login`      | Público               | CU001       |
| Crear usuario | `POST /users`           | Solo `ADMIN`          | CU003       |
| Listar        | `GET  /users`           | Solo `ADMIN`          | CU003       |
| Actualizar    | `PATCH /users/{id}`     | Solo `ADMIN`          | CU003       |

> La autenticación está **completamente delegada a AWS Cognito**. Este módulo
> NO almacena contraseñas; solo persiste el perfil del usuario en la tabla
> `promotick_users` (DynamoDB) y orquesta las llamadas a Cognito.

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
├── serverless.yml              # Deploy: 4 Lambdas + JWT authorizer
├── requirements.txt            # boto3 (runtime)
├── requirements-dev.txt        # pytest, moto, mypy, ruff
├── pytest.ini
├── .env.example                # vars para pruebas locales
├── .gitignore
├── README.md                   # este archivo
Promotick
└── src/
    ├── handlers/
    │   ├── _http.py            # helpers: json_response, parse_body, claims, require_admin
    │   ├── login.py            # CU001
    │   ├── create_user.py      # CU003 — crear (Cognito + Dynamo)
    │   ├── list_users.py       # CU003 — listar
    │   └── update_user.py      # CU003 — actualizar (rol, estado, nombre)
    ├── domain/
    │   ├── user.py             # @dataclass(frozen=True) User + invariantes
    │   ├── ports.py            # UserRepository, AuthProvider, AuthTokens, errores
    │   └── services.py         # LoginService, CreateUserService, ListUsersService, UpdateUserService
    └── adapters/
        ├── dynamo_user_repository.py
        └── cognito_auth_adapter.py
```

---

## 3. Infraestructura consumida

Todo viene de **CloudFormation Outputs** de `promotick-infra` — este repo
NO crea infraestructura compartida.

| Recurso             | Output consumido                                  | Var de entorno         |
|---------------------|---------------------------------------------------|------------------------|
| Tabla `promotick_users` | `${cf:promotick-infra-dynamodb.UsersTableName}` | `USERS_TABLE_NAME`     |
| Cognito User Pool   | `${cf:promotick-infra-cognito.UserPoolId}`        | `USER_POOL_ID`         |
| Cognito App Client  | `${cf:promotick-infra-cognito.UserPoolClientId}`  | `USER_POOL_CLIENT_ID`  |
| IAM role            | `arn:aws:iam::${AWS::AccountId}:role/LabRole`     | (no aplica)            |

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

---

## 5. Contratos HTTP

### POST `/auth/login`  (público)
```json
// request
{ "email": "ana@x.com", "password": "..." }

// 200 OK
{
  "tokens": { "id_token": "...", "access_token": "...", "refresh_token": "...",
              "expires_in": 3600, "token_type": "Bearer" },
  "user":   { "user_id": "...", "email": "ana@x.com", "role": "EJEC", ... }
}
// 401 credenciales inválidas · 403 user inactivo · 404 sin perfil
```

### POST `/users`  (Bearer JWT, rol ADMIN)
```json
// request
{ "email": "nuevo@x.com", "full_name": "Nuevo Usuario", "role": "EJEC" }

// 201 Created → { "user": { ... } }
// 400 rol inválido / email inválido · 403 no ADMIN · 409 email duplicado
```

### GET `/users?limit=100`  (Bearer JWT, rol ADMIN)
```json
// 200 OK → { "users": [ ... ], "count": N }
```

### PATCH `/users/{user_id}`  (Bearer JWT, rol ADMIN)
```json
// request — todos los campos opcionales
{ "full_name": "Nuevo Nombre", "role": "VIEWER", "is_active": false }

// 200 OK → { "user": { ... } }
// 400 rol inválido · 403 no ADMIN o auto-bloqueo · 404 user no existe
```

---

## 6. Desarrollo local

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env       # editar si hace falta
pytest tests/              # unit + integración (moto, sin AWS real)
```

Convenciones:
- Lint: `ruff check src/`
- Tipos: `mypy src/`
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

Pre-requisito: la stack `promotick-infra` ya desplegada (tabla + Cognito).

---

## 8. Anti-patrones — rechazar

- Importar `boto3` desde `src/domain/*`.
- Crear roles IAM propios — usar SIEMPRE `LabRole`.
- Crear la tabla DynamoDB o el User Pool desde este repo — viven en `promotick-infra`.
- Llamar a otra Lambda con `boto3.client("lambda").invoke(...)` — usar API Gateway / EventBridge.
- Hardcodear `USERS_TABLE_NAME`, `USER_POOL_ID`, etc. — siempre por `os.environ`.
- Permitir creación de usuario con rol distinto a `ADMIN / EJEC / VIEWER`.
- Saltarse `ConditionExpression` en escrituras "crear si no existe".
- Mergear sin tests (`pytest tests/` debe pasar).

---

## 9. Bloque MCP — contexto para IA / nuevos contribuyentes

> Si eres una IA (Claude, Copilot, Cursor, …) o un humano nuevo: lee este
> bloque ANTES de proponer cambios. Aquí está condensado el contexto que
> evita errores típicos.

### 9.1 Identidad del módulo

- **Nombre:** `promotick-auth`
- **Propósito:** módulo de identidad — login + gestión de usuarios (ABM) del
  sistema Promotick.
- **Stack:** Python 3.12, AWS Lambda, API Gateway (HTTP API v2), DynamoDB,
  Cognito, Serverless Framework. Región fija `us-east-1`.
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
8. **Test obligatorio por cambio.** Unit con fakes (rápido) + integración
   con `moto` cuando toques adapters.

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
7. **Tests.** Unit con `FakeUserRepository` + integración con `moto`.

### 9.5 Anti-patrones — la IA debe detenerse y preguntar si le piden:

- "Importa `boto3` en `services.py` para ahorrar líneas." → No.
- "Crea una tabla DynamoDB nueva en este repo." → No, va en `promotick-infra`.
- "Llama a la Lambda de products con `boto3.invoke`." → No, vía API/EventBridge.
- "Hardcodea `promotick_users` para acelerar." → No, va por env.
- "Agrega el rol `SUPERVISOR` rápidamente." → No, los roles son estáticos
  por RN-0004; primero se actualiza el doc de análisis.
- "Permite que cualquier usuario autenticado liste usuarios." → No, solo ADMIN.
- "Sálta los tests, ya los corremos después." → No.
- "Crea un IAM role nuevo para este Lambda." → No, `LabRole` siempre.

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
