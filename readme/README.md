# Ardur Appraisal Management System

A streamlined internal web application for mortgage underwriters to upload, process, and review US residential appraisal documents with automated OCR extraction and quality control validation.

---

## Quick Start

### Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Java | 21+ | Backend runtime |
| Maven | 3.9+ | Build tool |
| PostgreSQL | 15+ | Database |
| Python | 3.11+ | OCR service |

### 1. Start the Database

```bash
# Using Docker (recommended)
docker run --name appraisal-db -e POSTGRES_DB=appraisal_dev \
  -e POSTGRES_PASSWORD=localdev -p 5432:5432 -d postgres:15

# Or use your local PostgreSQL installation
createdb appraisal_dev
```

### 2. Start the OCR Microservice

```bash
cd ocr-service
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --port 5001
```

### 3. Start the Java Backend

```bash
cd backend
./mvnw spring-boot:run -Dspring.profiles.active=dev
```

### 4. Access the Application

Open your browser to **http://localhost:8080**

**Default Users:**
| Email | Password | Role |
|-------|----------|------|
| admin@example.com | Admin123! | ADMIN |
| underwriter@example.com | Under123! | UNDERWRITER |

---

## Project Structure

```
ardurApprisal/
├── readme/                    # Documentation (you are here)
│   ├── README.md
│   ├── IMPLEMENTATION_PLAN.md
│   ├── ARCHITECTURE.md
│   └── API_REFERENCE.md
├── src/main/java/             # Java backend source
│   └── com/ardur/appraisal/
│       ├── auth/              # Authentication module
│       ├── appraisal/         # Core appraisal logic
│       ├── ocr/               # OCR integration client
│       ├── qc/                # Quality control rules
│       └── admin/             # Admin management
├── src/main/resources/
│   ├── templates/             # Thymeleaf HTML templates
│   ├── static/                # CSS, JS, images
│   └── application.yml        # Configuration
├── src/test/java/             # Automated tests
├── ocr-service/               # Python OCR microservice
│   ├── main.py
│   └── requirements.txt
└── uploads/                   # Uploaded PDF storage
```

---

## Core Workflow

```
┌──────────────┐     ┌───────────────┐     ┌──────────────┐
│   Upload     │────►│  OCR Extract  │────►│  QC Rules    │
│   PDF        │     │  Fields       │     │  Validation  │
└──────────────┘     └───────────────┘     └──────────────┘
                                                  │
                                                  ▼
┌──────────────┐     ┌───────────────┐     ┌──────────────┐
│   Done       │◄────│  Approve /    │◄────│  Review      │
│              │     │  Revise       │     │  + Comment   │
└──────────────┘     └───────────────┘     └──────────────┘
```

---

## Key Features (Phase 1)

- **Secure Authentication** — JWT for API, session-based for web UI
- **PDF Upload** — Validates and stores appraisal documents
- **OCR Extraction** — Extracts borrower, property, value fields automatically
- **Quality Control** — 5 validation rules flag issues by severity
- **Review Workflow** — Approve or reject with required comments
- **Admin Panel** — Manage underwriter accounts
- **Audit Trail** — Track all status changes with timestamps

---

## Configuration

Create `application-dev.yml` in `src/main/resources/`:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/appraisal_dev
    username: postgres
    password: localdev
  jpa:
    hibernate:
      ddl-auto: validate

jwt:
  secret: ${JWT_SECRET:your-256-bit-secret-key-here}
  expiration: 900

ocr:
  service-url: http://localhost:5001

file:
  upload-dir: ./uploads
  max-size: 50MB
```

---

## Running Tests

```bash
# All tests
./mvnw test

# Specific test class
./mvnw test -Dtest=AppraisalServiceTest

# With coverage report
./mvnw test jacoco:report
# View: target/site/jacoco/index.html
```

---

## API Overview

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/auth/login` | POST | Authenticate and get JWT |
| `/api/v1/auth/me` | GET | Current user info |
| `/api/v1/appraisals/upload` | POST | Upload PDF |
| `/api/v1/appraisals` | GET | List appraisals |
| `/api/v1/appraisals/{id}` | GET | Get appraisal details |
| `/api/v1/appraisals/{id}/status` | POST | Change status |
| `/api/v1/admin/users` | GET | List users (Admin) |
| `/api/v1/admin/users` | POST | Create user (Admin) |

See [API_REFERENCE.md](./API_REFERENCE.md) for complete documentation.

---

## Related Documentation

| Document | Description |
|----------|-------------|
| [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md) | Full sprint plan with day-by-day tasks, data models, and verification criteria |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | System design, module interactions, and technology decisions |
| [API_REFERENCE.md](./API_REFERENCE.md) | Complete REST API specifications with examples |

---

## Support

For questions or issues, contact the development team.

**Project Status:** Phase 1 Development  
**Target Completion:** 7 days from sprint start
