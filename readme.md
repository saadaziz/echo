
# Echo Client App (API Gateway / Browser UI)

The **Echo client app** is a secure, Flask-based API gateway and user interface for your microservices platform. It provides unified web UI for document upload, RAG querying, job/status monitoring, and integrated Single Sign-On (SSO) authentication.

---

## Overview

- **Web UI**: Upload docs, monitor jobs, run RAG queries, view logs.
- **Authentication**: OAuth2/OIDC (Authorization Code Flow) with identity-backend.
- **Secure Gateway**: Validates JWTs on every user request.
- **Service Orchestration**: Integrates with Worker, Parser, Logging, and Identity microservices.

---

## Architecture Diagrams

### 1. System Context Diagram

![System Context Diagram](https://aurorahours.com/images/Echo-system-context.png)

<details>
<summary>View PlantUML Source</summary>

```plantuml
@startuml
actor User
package "Echo Client (API Gateway)" as UI {
}
package "Identity Backend" as ID {
}
package "Worker Service" as Worker {
}
package "Parser Service" as Parser {
}
package "Logging Service" as Log {
}
User --> UI : Browser / HTTPS
UI <--> ID : OIDC / JWT Auth
UI <--> Worker : Job Queue / Status
Worker <--> Parser : Parse Doc
UI <--> Log : Logs API
Worker <--> Log : Logs API
@enduml
```

</details>

---

### 2. Component Diagram

![Component Diagram](https://aurorahours.com/images/Echo-client-api-gw.png)

<details>
<summary>View PlantUML Source</summary>

```plantuml
@startuml
package "Echo Client (API Gateway)" {
  [Flask Web App] --> [Template Renderer]
  [Flask Web App] --> [Session/JWT Handler]
  [Flask Web App] --> [REST Client]
  [REST Client] --> [Identity Backend API]
  [REST Client] --> [Worker API]
  [REST Client] --> [Logging Service API]
  [REST Client] --> [Parser Service API]
}
@enduml
```

</details>

---

### 3. REST/Service Call Diagram

![REST Service Call Diagram](https://aurorahours.com/images/Echo-REST-service-calls.png)

<details>
<summary>View PlantUML Source</summary>

```plantuml
@startuml
actor User
participant "Echo Client\n(API Gateway)" as UI
participant "Identity Backend" as ID
participant "Worker" as W
participant "Parser" as P
participant "Logging" as Log

User -> UI : Visit /
UI -> ID : /authorize (OIDC login)
User -> ID : Enter creds
ID -> UI : /callback?code=...
UI -> ID : /token (get JWT)
UI -> UI : Store JWT in session
User -> UI : Upload file
UI -> W : POST /job
W -> P : POST /parse
P -> W : Return parsed text
W -> W : Store result
UI -> W : GET /job/status
UI -> Log : GET /logs.json
@enduml
```

</details>

---

### 4. OAuth2/OIDC Login Sequence

![OAuth2/OIDC Login Sequence](https://aurorahours.com/images/OAuth2-OIDC-Login-Sequence.png)

<details>
<summary>View PlantUML Source</summary>

```plantuml
@startuml
actor User as U
participant "Browser (Echo UI)" as C
participant "Identity Backend" as I

U -> C : GET http://localhost:5000/
C -> C : Check session for JWT
alt No valid JWT
    C -> I : /authorize?client_id=...&redirect_uri=...&state=...
    I -> U : Show login form
    U -> I : Submit username/password
    I -> I : Validate credentials
    alt Success
        I -> C : /callback?code=...
        C -> I : POST /token
        I -> C : Return JWT
        C -> C : Store JWT in session
        C -> U : Redirect to home
    else Failure
        I -> U : Show error
    end
else Valid JWT
    C -> U : Render dashboard
end
@enduml
```

</details>

---

### 5. Service-to-Service JWT Auth Sequence

![Service-to-Service JWT Auth Sequence](https://aurorahours.com/images/Echo-Service-to-Service.png)

<details>
<summary>View PlantUML Source</summary>

```plantuml
@startuml
participant "Worker Service" as W
participant "Logging Service" as L

W -> W : Create JWT (sign with shared secret)\nInclude: iss, aud, exp, etc.
W -> L : POST /log { log data }, Authorization: Bearer <JWT>
L -> L : Verify JWT signature, claims, expiry
alt Valid JWT
    L -> L : Process log, store in DB
    L -> W : 200 OK
else Invalid JWT
    L -> W : 401 Unauthorized
end
@enduml
```

</details>

---

## Environment Variables

Set in `.env` or your deployment environment:

| Variable               | Description                                 | Example/Default                            |
| ---------------------- | ------------------------------------------- | ------------------------------------------ |
| `FLASK_SECRET_KEY`     | Session encryption key (strong, random)     | `super_secret_flask_key`                   |
| `JWT_SECRET_KEY`       | Must match identity-backend                 | `your_shared_secret`                       |
| `JWT_ISSUER`           | Must match identity-backend                 | `https://aurorahours.com/identity-backend` |
| `IDENTITY_BACKEND_URL` | URL of identity-backend                     | `https://aurorahours.com/identity-backend` |
| `CLIENT_ID`            | OIDC client\_id for this app                | `browser-ui`                               |
| `CLIENT_SECRET`        | OIDC client\_secret (from identity-backend) | `dev-client-secret`                        |
| `OPENAI_API_KEY`       | OpenAI (or Ollama) key for RAG queries      | `sk-...`                                   |

---

## Setup

### 1. Install Requirements

```bash
pip install -r requirements.txt
```

* Flask, requests, PyJWT, python-dotenv, etc.

### 2. Configure Environment

Create `.env` or set vars as above.

### 3. Run the App

```bash
python api_gateway.py
```

For production, run with Gunicorn or uWSGI, and always use HTTPS.

---

## Core Features

* **SSO Login:**
  Enforces login via identity-backend (OIDC Authorization Code Flow).
  JWT is stored in session, validated per request.

* **File Upload and Job Queueing:**
  Upload via web form, queue job for Worker, Worker invokes Parser, results returned and shown.

* **RAG Query:**
  User enters question, app gathers parsed docs, calls OpenAI/Ollama API, shows response.

* **Centralized Logging:**
  Logs actions and events via Logging Service; displays logs in a secure admin view.

---

## Endpoints

| Endpoint    | Description                          | Auth Required? |
| ----------- | ------------------------------------ | :------------: |
| `/`         | Home/dashboard (requires login)      |        ✅       |
| `/login`    | Initiate login (redirects to SSO)    |        ❌       |
| `/callback` | Handles auth code, exchanges for JWT |        ❌       |
| `/upload`   | Upload document for processing       |        ✅       |
| `/query-ui` | RAG query interface                  |        ✅       |
| `/logs`     | View logs (admin, restrict in prod)  |        ✅       |

---

## Security

* All secrets must be strong, unique, and never checked into source control.
* JWT signature verification is enforced for all protected routes.
* Session cookies should be set with `Secure`, `HttpOnly`, and `SameSite` flags.
* CSRF protection recommended for all browser form POSTs.
* Logs endpoint must be restricted or disabled in production.

---

## Troubleshooting

* **Token expired**: User must re-login. Session tokens default to 15 minutes.
* **Invalid audience/issuer**: Check env vars, match with identity-backend.
* **Signature verification failed**: Secrets do not match across services.

---

## Updating Diagrams

* Store all PlantUML sources in `/docs/architecture/` in your repo.
* Generate PNGs with PlantUML and link them in this README.

---

## Launching locally

```bash
(base) PS C:\Users\saad0\Documents\source\echo> python api_gateway.py 2>&1 | tee flask.log
```
---

## License

MIT (c) 2025 Saad Aziz and partners
