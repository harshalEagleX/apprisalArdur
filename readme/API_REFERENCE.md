# API Reference

Complete REST API documentation for the Ardur Appraisal Management System.

**Base URL:** `http://localhost:8080/api/v1`  
**Content-Type:** `application/json` (unless otherwise noted)  
**Authentication:** Bearer token in `Authorization` header

---

## Table of Contents

1. [Authentication](#authentication)
2. [Appraisals](#appraisals)
3. [Admin](#admin)
4. [Error Responses](#error-responses)

---

## Authentication

### Login

Authenticate with email and password to receive JWT tokens.

```
POST /auth/login
```

**Request Body:**
```json
{
  "email": "underwriter@example.com",
  "password": "SecurePass123!"
}
```

**Success Response (200):**
```json
{
  "accessToken": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refreshToken": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "tokenType": "Bearer",
  "expiresIn": 900,
  "user": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "email": "underwriter@example.com",
    "firstName": "Jane",
    "lastName": "Smith",
    "role": "UNDERWRITER"
  }
}
```

**Error Response (401):**
```json
{
  "error": "INVALID_CREDENTIALS",
  "message": "Email or password is incorrect",
  "timestamp": "2025-12-10T10:30:00Z"
}
```

---

### Current User

Get information about the authenticated user.

```
GET /auth/me
Authorization: Bearer <accessToken>
```

**Success Response (200):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "underwriter@example.com",
  "firstName": "Jane",
  "lastName": "Smith",
  "role": "UNDERWRITER",
  "isActive": true,
  "createdAt": "2025-11-15T10:00:00Z"
}
```

---

### Refresh Token

Get a new access token using a refresh token.

```
POST /auth/refresh
```

**Request Body:**
```json
{
  "refreshToken": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Success Response (200):**
```json
{
  "accessToken": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "tokenType": "Bearer",
  "expiresIn": 900
}
```

---

## Appraisals

### Upload Appraisal

Upload a new appraisal PDF document for processing.

```
POST /appraisals/upload
Authorization: Bearer <accessToken>
Content-Type: multipart/form-data
```

**Form Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| file | File | Yes | PDF file, max 50MB |
| loanNumber | String | No | Loan reference number |

**cURL Example:**
```bash
curl -X POST http://localhost:8080/api/v1/appraisals/upload \
  -H "Authorization: Bearer eyJhbGci..." \
  -F "file=@/path/to/appraisal.pdf" \
  -F "loanNumber=LN-2025-12345"
```

**Success Response (201):**
```json
{
  "id": "660e8400-e29b-41d4-a716-446655440001",
  "status": "PENDING",
  "originalFilename": "AppraisalReport_1234.pdf",
  "loanNumber": "LN-2025-12345",
  "assignedTo": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "email": "underwriter@example.com"
  },
  "ocrStatus": "PROCESSING",
  "createdAt": "2025-12-10T14:35:00Z",
  "message": "Appraisal uploaded successfully. OCR processing initiated."
}
```

**Error Response (400):**
```json
{
  "error": "INVALID_FILE_TYPE",
  "message": "Only PDF files are accepted. Received: image/jpeg",
  "timestamp": "2025-12-10T14:35:00Z"
}
```

---

### List Appraisals

Get a paginated list of appraisals with optional filtering.

```
GET /appraisals
Authorization: Bearer <accessToken>
```

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| status | String | (all) | Filter: PENDING, APPROVED, NEEDS_REVISION |
| page | Integer | 0 | Page number (zero-indexed) |
| size | Integer | 20 | Items per page (max 100) |
| sortBy | String | createdAt | Sort field: createdAt, borrowerName, appraisedValue |
| sortDir | String | desc | Sort direction: asc, desc |

**Example Request:**
```
GET /appraisals?status=PENDING&page=0&size=10&sortBy=createdAt&sortDir=desc
```

**Success Response (200):**
```json
{
  "content": [
    {
      "id": "660e8400-e29b-41d4-a716-446655440001",
      "borrowerName": "John Doe",
      "propertyAddress": "123 Main Street, Anytown, NY 12345",
      "appraisedValue": 450000.00,
      "status": "PENDING",
      "formType": "1004",
      "loanNumber": "LN-2025-12345",
      "qcIssueCount": 2,
      "qcHighSeverityCount": 0,
      "assignedTo": {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "email": "underwriter@example.com",
        "firstName": "Jane"
      },
      "createdAt": "2025-12-10T14:35:00Z",
      "updatedAt": "2025-12-10T14:36:00Z"
    }
  ],
  "page": 0,
  "size": 10,
  "totalElements": 45,
  "totalPages": 5,
  "first": true,
  "last": false
}
```

---

### Get Appraisal Details

Get complete information for a specific appraisal, including OCR results and QC issues.

```
GET /appraisals/{id}
Authorization: Bearer <accessToken>
```

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| id | UUID | Appraisal ID |

**Success Response (200):**
```json
{
  "id": "660e8400-e29b-41d4-a716-446655440001",
  "originalFilename": "AppraisalReport_1234.pdf",
  "fileUrl": "/api/v1/appraisals/660e8400-e29b-41d4-a716-446655440001/file",
  "borrowerName": "John Doe",
  "coBorrowerName": null,
  "propertyAddress": "123 Main Street, Anytown, NY 12345",
  "city": "Anytown",
  "state": "NY",
  "zipCode": "12345",
  "appraisedValue": 450000.00,
  "salePrice": 440000.00,
  "loanNumber": "LN-2025-12345",
  "formType": "1004",
  "status": "PENDING",
  "assignedTo": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "email": "underwriter@example.com",
    "firstName": "Jane",
    "lastName": "Smith"
  },
  "ocrResult": {
    "id": "770e8400-e29b-41d4-a716-446655440000",
    "processingStatus": "COMPLETED",
    "confidenceScore": 0.87,
    "extractedFields": {
      "borrowerName": "John Doe",
      "propertyAddress": "123 Main Street, Anytown, NY 12345",
      "appraisedValue": 450000,
      "effectiveDate": "2025-12-01",
      "lenderName": "ABC Mortgage Corp",
      "appraiserName": "Licensed Appraiser Inc."
    },
    "checkboxes": {
      "isInFloodZone": false,
      "isForSale": false,
      "hasPoolOrSpa": true,
      "isCondoOrPUD": false
    },
    "warnings": [
      "Low confidence on 'appraiserLicenseNumber' field (0.65)"
    ],
    "createdAt": "2025-12-10T14:36:00Z"
  },
  "qcIssues": [
    {
      "id": "880e8400-e29b-41d4-a716-446655440001",
      "ruleCode": "RULE-003",
      "severity": "MEDIUM",
      "fieldName": "propertyAddress",
      "message": "Property address does not include ZIP+4 code",
      "isResolved": false,
      "createdAt": "2025-12-10T14:36:00Z"
    },
    {
      "id": "880e8400-e29b-41d4-a716-446655440002",
      "ruleCode": "RULE-005",
      "severity": "LOW",
      "fieldName": null,
      "message": "OCR confidence below 90% threshold - recommend manual verification",
      "isResolved": false,
      "createdAt": "2025-12-10T14:36:00Z"
    }
  ],
  "reviewHistory": [
    {
      "id": "990e8400-e29b-41d4-a716-446655440001",
      "user": {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "email": "underwriter@example.com",
        "firstName": "Jane"
      },
      "oldStatus": null,
      "newStatus": "PENDING",
      "comment": "Initial upload",
      "createdAt": "2025-12-10T14:35:00Z"
    }
  ],
  "createdAt": "2025-12-10T14:35:00Z",
  "updatedAt": "2025-12-10T14:36:00Z"
}
```

**Error Response (404):**
```json
{
  "error": "NOT_FOUND",
  "message": "Appraisal not found with id: 660e8400-e29b-41d4-a716-446655440001",
  "timestamp": "2025-12-10T14:40:00Z"
}
```

---

### Download Appraisal PDF

Download the original PDF file.

```
GET /appraisals/{id}/file
Authorization: Bearer <accessToken>
```

**Response:** Binary PDF file

**Headers:**
```
Content-Type: application/pdf
Content-Disposition: attachment; filename="AppraisalReport_1234.pdf"
```

---

### Change Appraisal Status

Update the status of an appraisal with a required comment.

```
POST /appraisals/{id}/status
Authorization: Bearer <accessToken>
```

**Request Body:**
```json
{
  "status": "APPROVED",
  "comment": "All fields verified against loan documentation. Value is consistent with comparable sales in the area. QC issues reviewed and determined acceptable."
}
```

**Valid Status Transitions:**

| From | To | Allowed |
|------|-----|---------|
| PENDING | APPROVED | ✓ |
| PENDING | NEEDS_REVISION | ✓ |
| APPROVED | PENDING | ✗ |
| APPROVED | NEEDS_REVISION | ✗ |
| NEEDS_REVISION | PENDING | ✗ |
| NEEDS_REVISION | APPROVED | ✗ |

**Success Response (200):**
```json
{
  "id": "660e8400-e29b-41d4-a716-446655440001",
  "status": "APPROVED",
  "previousStatus": "PENDING",
  "updatedAt": "2025-12-10T15:00:00Z",
  "reviewAction": {
    "id": "990e8400-e29b-41d4-a716-446655440002",
    "oldStatus": "PENDING",
    "newStatus": "APPROVED",
    "comment": "All fields verified against loan documentation...",
    "user": {
      "email": "underwriter@example.com",
      "firstName": "Jane"
    },
    "createdAt": "2025-12-10T15:00:00Z"
  }
}
```

**Error Response (400 - Invalid Transition):**
```json
{
  "error": "INVALID_STATUS_TRANSITION",
  "message": "Cannot transition from APPROVED to PENDING. Approved appraisals are final.",
  "timestamp": "2025-12-10T15:00:00Z"
}
```

**Error Response (400 - Missing Comment):**
```json
{
  "error": "VALIDATION_ERROR",
  "message": "Comment is required when changing status",
  "field": "comment",
  "timestamp": "2025-12-10T15:00:00Z"
}
```

---

### Retry OCR Processing

Manually trigger OCR processing for an appraisal that failed or was not processed.

```
POST /appraisals/{id}/process
Authorization: Bearer <accessToken>
```

**Success Response (200):**
```json
{
  "id": "660e8400-e29b-41d4-a716-446655440001",
  "ocrStatus": "COMPLETED",
  "message": "OCR processing completed successfully",
  "extractedFields": {
    "borrowerName": "John Doe",
    "propertyAddress": "123 Main Street, Anytown, NY 12345",
    "appraisedValue": 450000
  }
}
```

**Error Response (503 - OCR Service Unavailable):**
```json
{
  "error": "OCR_SERVICE_UNAVAILABLE",
  "message": "OCR service is currently unavailable. Please try again later.",
  "timestamp": "2025-12-10T15:00:00Z"
}
```

---

## Admin

> **Note:** All admin endpoints require `ROLE_ADMIN`. Underwriters will receive 403 Forbidden.

### List Users

Get all users in the system.

```
GET /admin/users
Authorization: Bearer <accessToken>
```

**Success Response (200):**
```json
{
  "content": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "email": "admin@example.com",
      "firstName": "Admin",
      "lastName": "User",
      "role": "ADMIN",
      "isActive": true,
      "appraisalCount": 0,
      "createdAt": "2025-11-01T10:00:00Z",
      "lastLoginAt": "2025-12-10T09:00:00Z"
    },
    {
      "id": "550e8400-e29b-41d4-a716-446655440010",
      "email": "underwriter@example.com",
      "firstName": "Jane",
      "lastName": "Smith",
      "role": "UNDERWRITER",
      "isActive": true,
      "appraisalCount": 23,
      "createdAt": "2025-11-15T10:00:00Z",
      "lastLoginAt": "2025-12-10T08:30:00Z"
    }
  ],
  "totalElements": 2
}
```

---

### Create User

Create a new user account.

```
POST /admin/users
Authorization: Bearer <accessToken>
```

**Request Body:**
```json
{
  "email": "new.underwriter@example.com",
  "firstName": "New",
  "lastName": "User",
  "role": "UNDERWRITER",
  "temporaryPassword": "TempPass123!"
}
```

**Success Response (201):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440020",
  "email": "new.underwriter@example.com",
  "firstName": "New",
  "lastName": "User",
  "role": "UNDERWRITER",
  "isActive": true,
  "createdAt": "2025-12-10T16:00:00Z",
  "message": "User created successfully. User must change password on first login."
}
```

**Error Response (400 - Duplicate Email):**
```json
{
  "error": "DUPLICATE_EMAIL",
  "message": "User with email 'new.underwriter@example.com' already exists",
  "timestamp": "2025-12-10T16:00:00Z"
}
```

---

### Update User Role

Change a user's role.

```
PATCH /admin/users/{id}/role
Authorization: Bearer <accessToken>
```

**Request Body:**
```json
{
  "role": "ADMIN"
}
```

**Success Response (200):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440010",
  "email": "underwriter@example.com",
  "role": "ADMIN",
  "previousRole": "UNDERWRITER",
  "updatedAt": "2025-12-10T16:30:00Z"
}
```

---

### Deactivate User

Soft-delete a user (preserves audit trail, prevents login).

```
DELETE /admin/users/{id}
Authorization: Bearer <accessToken>
```

**Success Response (200):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440010",
  "email": "underwriter@example.com",
  "isActive": false,
  "message": "User deactivated successfully"
}
```

**Error Response (400 - Self-Delete):**
```json
{
  "error": "CANNOT_DEACTIVATE_SELF",
  "message": "You cannot deactivate your own account",
  "timestamp": "2025-12-10T16:30:00Z"
}
```

---

## Error Responses

All error responses follow this structure:

```json
{
  "error": "ERROR_CODE",
  "message": "Human-readable description",
  "field": "fieldName",
  "timestamp": "2025-12-10T10:30:00Z"
}
```

### HTTP Status Codes

| Code | Meaning | When Used |
|------|---------|-----------|
| 200 | OK | Successful GET, PUT, PATCH, DELETE |
| 201 | Created | Successful POST (resource created) |
| 400 | Bad Request | Validation errors, invalid input |
| 401 | Unauthorized | Missing or invalid authentication |
| 403 | Forbidden | Authenticated but not authorized |
| 404 | Not Found | Resource doesn't exist |
| 413 | Payload Too Large | File exceeds 50MB limit |
| 415 | Unsupported Media Type | Wrong file type |
| 500 | Internal Server Error | Unexpected server error |
| 503 | Service Unavailable | OCR service down |

### Common Error Codes

| Code | Description |
|------|-------------|
| INVALID_CREDENTIALS | Wrong email or password |
| TOKEN_EXPIRED | JWT access token has expired |
| TOKEN_INVALID | JWT is malformed or tampered |
| VALIDATION_ERROR | Request body failed validation |
| NOT_FOUND | Requested resource doesn't exist |
| ACCESS_DENIED | User lacks required permission |
| INVALID_FILE_TYPE | Uploaded file is not a PDF |
| FILE_TOO_LARGE | File exceeds size limit |
| INVALID_STATUS_TRANSITION | Status change not allowed |
| OCR_SERVICE_UNAVAILABLE | Python OCR service is down |
| DUPLICATE_EMAIL | Email already registered |

---

## Rate Limiting

Phase 1 does not implement rate limiting. Future phases may add:

- 100 requests per minute per user
- 10 file uploads per minute per user
- 429 Too Many Requests response when exceeded

---

*For architecture details, see [ARCHITECTURE.md](./ARCHITECTURE.md)*  
*For implementation timeline, see [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md)*
