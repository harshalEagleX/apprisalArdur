# System Architecture

This document provides a detailed technical overview of the Ardur Appraisal Management System architecture, including component design, data flow, and integration patterns.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Component Design](#component-design)
3. [Data Flow Patterns](#data-flow-patterns)
4. [Security Architecture](#security-architecture)
5. [Integration Patterns](#integration-patterns)
6. [Scalability Considerations](#scalability-considerations)

---

## Architecture Overview

The system follows a **modular monolith** architecture for the Java backend with a separate Python microservice for OCR processing. This approach balances simplicity with clear separation of concerns.

### High-Level View

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           CLIENTS                                        │
│  ┌─────────────────────┐  ┌─────────────────────┐                       │
│  │    Web Browser      │  │    API Consumer     │                       │
│  │  (Thymeleaf Pages)  │  │   (REST/JSON)       │                       │
│  └──────────┬──────────┘  └──────────┬──────────┘                       │
└─────────────┼────────────────────────┼──────────────────────────────────┘
              │                        │
              │  HTTP(S)               │  HTTP(S) + JWT
              ▼                        ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     JAVA BACKEND (Spring Boot 3)                         │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────┐     │
│  │                    Presentation Layer                          │     │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │     │
│  │  │ Web          │  │ REST API     │  │ Error        │         │     │
│  │  │ Controllers  │  │ Controllers  │  │ Handlers     │         │     │
│  │  └──────────────┘  └──────────────┘  └──────────────┘         │     │
│  └────────────────────────────────────────────────────────────────┘     │
│                                │                                         │
│  ┌────────────────────────────────────────────────────────────────┐     │
│  │                     Service Layer                               │     │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │     │
│  │  │ Auth     │  │ Appraisal│  │ QC       │  │ Admin    │       │     │
│  │  │ Service  │  │ Service  │  │ Service  │  │ Service  │       │     │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘       │     │
│  └────────────────────────────────────────────────────────────────┘     │
│                                │                                         │
│  ┌────────────────────────────────────────────────────────────────┐     │
│  │                   Infrastructure Layer                          │     │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │     │
│  │  │ JPA      │  │ File     │  │ OCR      │  │ JWT      │       │     │
│  │  │ Repos    │  │ Storage  │  │ Client   │  │ Provider │       │     │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘       │     │
│  └────────────────────────────────────────────────────────────────┘     │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
              │                                    │
              │ JDBC                               │ HTTP
              ▼                                    ▼
┌──────────────────────────────┐    ┌──────────────────────────────┐
│        PostgreSQL            │    │     Python OCR Service       │
│                              │    │        (FastAPI)             │
│  ┌────┐ ┌────┐ ┌────┐       │    │  ┌────────┐ ┌────────┐       │
│  │usr │ │app │ │qc  │       │    │  │PDF     │ │Tesseract│       │
│  │    │ │    │ │    │       │    │  │Parser  │ │Engine  │       │
│  └────┘ └────┘ └────┘       │    │  └────────┘ └────────┘       │
│                              │    │                              │
└──────────────────────────────┘    └──────────────────────────────┘
```

### Design Principles

1. **Layered Architecture** — Clear separation between presentation, business logic, and data access
2. **Dependency Injection** — All components wired via Spring's IoC container
3. **Single Responsibility** — Each service handles one domain area
4. **Fail-Safe Defaults** — Graceful degradation when OCR service is unavailable
5. **Stateless APIs** — JWT-based authentication, no server-side session for API calls

---

## Component Design

### Authentication Module (`auth/`)

Handles user identity and access control.

| Class | Responsibility |
|-------|----------------|
| `AuthController` | Login, logout, token refresh endpoints |
| `AuthService` | Credential validation, JWT generation |
| `JwtService` | Token creation, parsing, validation |
| `UserDetailsServiceImpl` | Spring Security user loading |
| `JwtAuthenticationFilter` | Intercepts requests, validates tokens |

**Key Design Decisions:**
- Hybrid auth: Sessions for web pages, JWT for API
- Access tokens expire in 15 minutes (security vs convenience trade-off)
- Refresh tokens last 7 days, can be revoked
- BCrypt with cost factor 12 for password hashing

### Appraisal Module (`appraisal/`)

Core business logic for appraisal document processing.

| Class | Responsibility |
|-------|----------------|
| `AppraisalController` | CRUD endpoints, file upload |
| `AppraisalService` | Business logic orchestration |
| `FileStorageService` | Save/retrieve PDF files |
| `AppraisalRepository` | Database operations |
| `AppraisalMapper` | Entity ↔ DTO conversions |

**Upload Flow:**
1. Validate file type (must be PDF)
2. Validate file size (≤ 50MB)
3. Generate unique filename: `{year}/{month}/{uuid}.pdf`
4. Save file to disk
5. Create `Appraisal` entity with PENDING status
6. Trigger OCR processing asynchronously (Phase 1: synchronous)

### OCR Integration Module (`ocr/`)

Communicates with the Python OCR microservice.

| Class | Responsibility |
|-------|----------------|
| `OcrClient` | HTTP calls to Python service |
| `OcrResponseParser` | Map JSON response to domain objects |
| `OcrRetryService` | Handle failures, implement retry logic |

**Error Handling Strategy:**
- If OCR service times out (> 30s): Mark as `OCR_PENDING`, allow manual retry
- If OCR service returns error: Log details, mark as `OCR_FAILED`
- If connection refused: Queue for background retry (Phase 1: manual retry only)

### QC Rules Engine (`qc/`)

Validates extracted data against business rules.

| Class | Responsibility |
|-------|----------------|
| `QcService` | Orchestrates rule execution |
| `Rule` (interface) | Contract for individual rules |
| `MissingValueRule` | Check required fields present |
| `ValueRangeRule` | Validate numeric ranges |
| `ConsistencyRule` | Cross-field validation |

**Rule Execution Pattern:**
```java
public interface Rule {
    Optional<QcIssue> evaluate(Appraisal appraisal, OcrResult ocr);
}

// Each rule returns Optional.empty() if passed, or QcIssue if failed
```

**Phase 1 Rules:**

| Rule | Check | Severity |
|------|-------|----------|
| RULE-001 | Appraised value > 0 | HIGH |
| RULE-002 | Borrower name present | MEDIUM |
| RULE-003 | Property address complete | MEDIUM |
| RULE-004 | Sale price when "for sale" | LOW |
| RULE-005 | OCR confidence ≥ 0.70 | LOW |

### Admin Module (`admin/`)

User management for administrators.

| Class | Responsibility |
|-------|----------------|
| `AdminController` | User CRUD endpoints |
| `AdminService` | User creation, role changes |
| `UserRepository` | Database operations |

**Security:**
- All endpoints require `ROLE_ADMIN`
- Cannot delete yourself
- Cannot demote the last admin

---

## Data Flow Patterns

### PDF Upload to Review

```
User                    Controller           Service              External
 │                          │                    │                    │
 │─── POST /upload ────────►│                    │                    │
 │    (multipart)           │                    │                    │
 │                          │─── validate() ────►│                    │
 │                          │                    │                    │
 │                          │                    │─── saveFile() ────►│ Disk
 │                          │                    │◄────── path ───────│
 │                          │                    │                    │
 │                          │                    │─── create() ──────►│ DB
 │                          │                    │◄───── entity ──────│
 │                          │                    │                    │
 │                          │                    │─ POST /ocr ───────►│ Python
 │                          │                    │◄─── JSON ──────────│
 │                          │                    │                    │
 │                          │                    │─── runRules() ────►│ (internal)
 │                          │                    │                    │
 │                          │                    │─── saveAll() ─────►│ DB
 │                          │◄── 201 Created ────│                    │
 │◄── Redirect to detail ───│                    │                    │
```

### Status Change

```
User                    Controller           Service              
 │                          │                    │                   
 │─ POST /status ──────────►│                    │                   
 │  { APPROVED, comment }   │                    │                   
 │                          │─ changeStatus() ──►│                   
 │                          │                    │─── validate ──────►
 │                          │                    │    transition      
 │                          │                    │                    
 │                          │                    │─── create ────────►
 │                          │                    │    ReviewAction    
 │                          │                    │                    
 │                          │                    │─── update ────────►
 │                          │                    │    Appraisal       
 │                          │◄─── 200 OK ────────│                   
 │◄─── Updated entity ──────│                    │                   
```

---

## Security Architecture

### Authentication Flow

```
                                 ┌─────────────────┐
                                 │   Login Form    │
                                 │  or API POST    │
                                 └────────┬────────┘
                                          │
                                          ▼
                              ┌───────────────────────┐
                              │  AuthenticationManager│
                              │  (Spring Security)    │
                              └───────────┬───────────┘
                                          │
                          ┌───────────────┴───────────────┐
                          │                               │
                          ▼                               ▼
               ┌─────────────────────┐       ┌─────────────────────┐
               │   Web Session       │       │   JWT Token         │
               │   (Thymeleaf)       │       │   (REST API)        │
               └─────────────────────┘       └─────────────────────┘
```

### Authorization Matrix Implementation

```java
@Configuration
@EnableMethodSecurity
public class SecurityConfig {
    
    @Bean
    public SecurityFilterChain apiSecurityChain(HttpSecurity http) {
        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/v1/auth/**").permitAll()
                .requestMatchers("/api/v1/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .addFilterBefore(jwtFilter, UsernamePasswordAuthFilter.class)
            .build();
    }
}
```

### Password Security

- **Hashing:** BCrypt with cost factor 12 (~250ms hash time)
- **Requirements:** 8+ chars, upper, lower, digit, special
- **Storage:** Only hashed passwords stored; never log passwords

### JWT Security

- **Algorithm:** HS256 (HMAC with SHA-256)
- **Secret:** 256-bit key from environment variable
- **Claims:** userId, email, role, issuedAt, expiration
- **Validation:** Signature, expiration, issuer checked on every request

---

## Integration Patterns

### OCR Service Integration

**Interface Contract:**

```
┌─────────────────────────────────────────────────────────────┐
│                    OCR Service Contract                      │
├─────────────────────────────────────────────────────────────┤
│ Endpoint: POST /ocr/appraisal                                │
│ Input:    multipart/form-data with 'file' field (PDF)       │
│ Output:   application/json                                   │
│ Timeout:  30 seconds                                         │
├─────────────────────────────────────────────────────────────┤
│ Success Response:                                            │
│ {                                                            │
│   "success": true,                                           │
│   "confidenceScore": 0.85,                                   │
│   "extractedFields": { ... },                                │
│   "checkboxes": { ... }                                      │
│ }                                                            │
├─────────────────────────────────────────────────────────────┤
│ Error Response:                                              │
│ {                                                            │
│   "success": false,                                          │
│   "error": "ERROR_CODE",                                     │
│   "message": "Human readable description"                    │
│ }                                                            │
└─────────────────────────────────────────────────────────────┘
```

**Client Implementation:**

```java
@Service
public class OcrClient {
    private final WebClient webClient;
    
    public OcrResult processAppraisal(Path pdfPath) {
        return webClient.post()
            .uri("/ocr/appraisal")
            .contentType(MULTIPART_FORM_DATA)
            .body(fromResource(new FileSystemResource(pdfPath)))
            .retrieve()
            .onStatus(HttpStatus::isError, this::handleError)
            .bodyToMono(OcrResponse.class)
            .timeout(Duration.ofSeconds(30))
            .map(this::toOcrResult)
            .block();
    }
}
```

---

## Scalability Considerations

### Phase 1 Constraints (Acceptable for MVP)

| Component | Current Limit | Impact |
|-----------|---------------|--------|
| File Storage | Local disk | Single server only |
| Sessions | In-memory | Lost on restart |
| OCR Processing | Synchronous | Blocks upload request |
| Database | Single instance | No read replicas |

### Phase 2+ Migrations

| Component | Current | Future | Migration Path |
|-----------|---------|--------|----------------|
| Files | Local | S3/GCS | Add StorageAdapter interface |
| Sessions | Memory | Redis | Configure Spring Session |
| OCR | Sync | Async | Add message queue (RabbitMQ/SQS) |
| Database | Single | Replicas | Use read-replica for list queries |

### Horizontal Scaling Blueprint

```
                    ┌──────────────────┐
                    │   Load Balancer  │
                    └────────┬─────────┘
                             │
            ┌────────────────┼────────────────┐
            │                │                │
     ┌──────▼─────┐   ┌──────▼─────┐   ┌──────▼─────┐
     │  Backend   │   │  Backend   │   │  Backend   │
     │  Instance  │   │  Instance  │   │  Instance  │
     └──────┬─────┘   └──────┬─────┘   └──────┬─────┘
            │                │                │
            └────────────────┼────────────────┘
                             │
            ┌────────────────┼────────────────┐
            │                │                │
     ┌──────▼─────┐   ┌──────▼─────┐   ┌──────▼─────┐
     │   Redis    │   │  Postgres  │   │     S3     │
     │  (Session) │   │ (Primary)  │   │  (Files)   │
     └────────────┘   └────────────┘   └────────────┘
```

---

## Technology Rationale Recap

| Choice | Why This | Why Not Alternatives |
|--------|----------|---------------------|
| Spring Boot 3 | Mature, well-documented, team expertise | Quarkus/Micronaut: learning curve |
| Thymeleaf | No separate frontend build, fast iteration | React: takes longer to set up |
| PostgreSQL | JSONB for OCR results, robust, free | MySQL: weaker JSON support |
| Python + FastAPI | Best OCR libs, fast to write | Node: Tesseract binding issues |
| JWT | Stateless API auth, standard | OAuth2: overkill for internal app |
| Local file storage | Simple for Phase 1 | S3: adds complexity early |

---

*For implementation details, see [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md)*
