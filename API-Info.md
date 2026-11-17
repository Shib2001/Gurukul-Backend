# API Info

This document records the backend API contract. Add future API groups as new
sections in this file.

## Authentication API

### Overview

- **Base URL (local):** `http://127.0.0.1:8000`
- **Base path:** `/api/v1/auth`
- **Content type:** `application/json`
- **Path parameters:** None for the current auth endpoints.
- **Query parameters:** None for the current auth endpoints.
- **Auth module:** `src/gurukul_be/api/v1/auth.py`
- **Request and response schemas:** `src/gurukul_be/schemas/auth.py`
- **Business logic:** `src/gurukul_be/services/auth.py` and
  `src/gurukul_be/services/password_reset.py`
- **Database models:** `src/gurukul_be/models/identity.py`
- **Email delivery:** `src/gurukul_be/integrations/email.py`

The API router is mounted under `/api/v1` by `src/gurukul_be/main.py`. Successful
responses use this common envelope:

```json
{
  "status_code": 200,
  "message": "OK",
  "data": {}
}
```

Errors use this shape:

```json
{
  "status_code": 422,
  "message": "Unprocessable Entity",
  "detail": "Request validation failed",
  "errors": [
    {
      "field": "password",
      "message": "String should have at least 8 characters",
      "code": "string_too_short"
    }
  ]
}
```

Validation errors return HTTP `422`. Other documented error codes are listed
with the endpoints below. The error envelope is implemented in
`src/gurukul_be/main.py`.

### Shared response shapes

#### Student

```json
{
  "id": "UUID",
  "roll_number": "GUR-26-000042",
  "display_name": "A Student",
  "email": "student@example.com",
  "date_of_birth": "2010-05-12",
  "grade_level": "10",
  "phone_number": "+919876543210",
  "liked_subjects": ["Mathematics", "Science"]
}
```

`date_of_birth`, `grade_level`, and `phone_number` can be `null`. The student
response never includes a password or password hash.

#### Authentication data

```json
{
  "access_token": "<short-lived JWT>",
  "refresh_token": "<opaque refresh token>",
  "token_type": "bearer",
  "student": {}
}
```

Use the access token on protected endpoints as:

```text
Authorization: Bearer <access_token>
```

Access tokens last 30 minutes. Refresh tokens last 30 days and are rotated when
used. The current response does not include token-expiration fields.

### Endpoints

#### 1. Register

- **Method and path:** `POST /api/v1/auth/register`
- **Purpose:** Create a pending student account and profile, assign a roll
  number, save a password hash, and start email verification.
- **API module:** `api/v1/auth.py` (`register`)
- **Service:** `services/auth.py` (`register_student`)
- **Request body:**

```json
{
  "display_name": "A Student",
  "date_of_birth": "2010-05-12",
  "grade_level": 10,
  "liked_subjects": ["Mathematics", "Science"],
  "phone_number": "+91 9876543210",
  "email": "student@example.com",
  "password": "<password, 8 to 128 characters>"
}
```

- `display_name`: required, 1-120 characters; repeated whitespace is collapsed.
- `date_of_birth`: required ISO date and must be in the past.
- `grade_level`: required integer from 1 through 10.
- `liked_subjects`: required list of 1-20 unique subjects; each subject must
  contain 1-50 characters.
- `phone_number`: required; 7-15 digits, optionally prefixed with `+`;
  spaces and other formatting characters are removed.
- `email`: required valid email address.
- `password`: required, 8-128 characters; it is hashed before storage.
- **Path/query parameters:** None.
- **Success:** HTTP `202 Accepted`.
- **Response data:**

```json
{
  "message": "Registration submitted. Check your email for the verification code.",
  "email": "student@example.com",
  "roll_number": "GUR-26-000042"
}
```

In development, if `EMAIL_VERIFICATION_RETURN_CODE_IN_RESPONSE=true`, the
response also includes `verification_code`. Otherwise the code is sent by
email. The code expires after 10 minutes. A duplicate email returns `409
Conflict`. If email delivery is required but not configured, registration
returns `503 Service Unavailable`.

#### 2. Verify email

- **Method and path:** `POST /api/v1/auth/verify-email`
- **Purpose:** Activate a pending student account and return authentication
  tokens.
- **API module:** `api/v1/auth.py` (`verify_email`)
- **Service:** `services/auth.py` (`verify_student_email`)
- **Request body:**

```json
{
  "identifier": "student@example.com",
  "code": "123456"
}
```

- `identifier`: required email address or student roll number.
- `code`: required six-digit verification code.
- **Path/query parameters:** None.
- **Success:** HTTP `200 OK`; response data is the shared Authentication data.
- **Errors:** `400 Bad Request` for an invalid, expired, used, or locked code.
  A code expires after 10 minutes and allows at most five failed attempts.

#### 3. Resend email verification code

- **Method and path:** `POST /api/v1/auth/verify-email/resend`
- **Purpose:** Request another verification code for a pending account.
- **API module:** `api/v1/auth.py` (`resend_verification_email`)
- **Service:** `services/auth.py` (`resend_email_verification_code`)
- **Request body:**

```json
{
  "identifier": "student@example.com"
}
```

- `identifier`: required email address or student roll number.
- **Path/query parameters:** None.
- **Success:** HTTP `202 Accepted` with a generic message. A code is included
  only when development code-return mode is enabled.
- **Limits:** At least 60 seconds between sends; at most three requests per
  hour. The generic response avoids revealing whether an account exists.
- **Error:** `503 Service Unavailable` if email delivery is required but not
  configured.

#### 4. Login

- **Method and path:** `POST /api/v1/auth/login`
- **Purpose:** Authenticate an active student and return access and refresh
  tokens.
- **API module:** `api/v1/auth.py` (`login`)
- **Service:** `services/auth.py` (`login_student`)
- **Request body:**

```json
{
  "identifier": "student@example.com",
  "password": "<password>"
}
```

- `identifier`: required email, student roll number, or display name.
- `password`: required, 1-128 characters.
- **Path/query parameters:** None.
- **Success:** HTTP `200 OK`; response data is the shared Authentication data.
- **Errors:** `401 Unauthorized` for invalid credentials or an ambiguous
  display name. `403 Forbidden` when the account still needs email
  verification.

#### 5. Refresh tokens

- **Method and path:** `POST /api/v1/auth/refresh`
- **Purpose:** Exchange a valid refresh token for a new access token and a
  rotated refresh token.
- **API module:** `api/v1/auth.py` (`refresh`)
- **Service:** `services/auth.py` (`refresh_student_tokens`)
- **Request body:**

```json
{
  "refresh_token": "<refresh token>"
}
```

- `refresh_token`: required, 32-128 characters.
- **Path/query parameters:** None.
- **Success:** HTTP `200 OK`; response data is the shared Authentication data.
- **Error:** `401 Unauthorized` for an invalid, expired, revoked, or previously
  used refresh token. Refresh-token reuse revokes the user's active sessions.

#### 6. Logout

- **Method and path:** `POST /api/v1/auth/logout`
- **Purpose:** Revoke the submitted refresh token. The current access token
  remains valid until it expires.
- **API module:** `api/v1/auth.py` (`logout`)
- **Service:** `services/auth.py` (`logout_student`)
- **Request body:**

```json
{
  "refresh_token": "<refresh token>"
}
```

- `refresh_token`: required, 32-128 characters.
- **Path/query parameters:** None.
- **Success:** HTTP `200 OK`.

```json
{
  "message": "You have been signed out."
}
```

#### 7. Get current student

- **Method and path:** `GET /api/v1/auth/me`
- **Purpose:** Return the student associated with the access token.
- **API module:** `api/v1/auth.py` (`get_me`)
- **Service:** `services/auth.py` (`get_student_by_id`, `_student_response`)
- **Request body:** None.
- **Path/query parameters:** None.
- **Required header:** `Authorization: Bearer <access_token>`.
- **Success:** HTTP `200 OK`; response data is the shared Student object.
- **Error:** `401 Unauthorized` if the access token is missing, invalid,
  expired, revoked, or belongs to an inactive account.

#### 8. Update current student profile

- **Method and path:** `PATCH /api/v1/auth/me`
- **Purpose:** Update one or more profile fields for the authenticated student.
- **API module:** `api/v1/auth.py` (`update_me`)
- **Schema:** `schemas/auth.py` (`UpdateProfileRequest`)
- **Service:** `services/auth.py` (`update_student_profile`)
- **Required header:** `Authorization: Bearer <access_token>`.
- **Request body:** At least one of the following fields is required. Unknown
  fields are rejected.

```json
{
  "display_name": "A Student",
  "date_of_birth": "2010-05-12",
  "grade_level": 10,
  "liked_subjects": ["Mathematics", "Science"],
  "phone_number": "+91 9876543210"
}
```

- `display_name`: optional, 1-120 characters.
- `date_of_birth`: optional ISO date in the past.
- `grade_level`: optional integer from 1 through 10.
- `liked_subjects`: optional list of 1-20 unique subjects, each 1-50 characters.
- `phone_number`: optional number with 7-15 digits after formatting is removed.
- **Path/query parameters:** None.
- **Success:** HTTP `200 OK`; response data is the updated Student object.
- **Error:** `401 Unauthorized` for invalid access token; `422 Unprocessable
Entity` for an empty or invalid update.

#### 9. Request password reset

- **Method and path:** `POST /api/v1/auth/password-reset/request`
- **Purpose:** Start password recovery by sending a one-time code to the
  registered email address.
- **API module:** `api/v1/auth.py` (`request_password_reset`)
- **Service:** `services/password_reset.py`
- **Request body:**

```json
{
  "identifier": "student@example.com"
}
```

- `identifier`: required email address or student roll number.
- **Path/query parameters:** None.
- **Success:** HTTP `202 Accepted` with a generic message, whether or not the
  account exists. In development, if `PASSWORD_RESET_RETURN_CODE_IN_RESPONSE=true`,
  the response also includes `otp_code` instead of sending email.
- **Limits:** Code expires after 10 minutes; at least 60 seconds between
  requests; at most three requests per hour.
- **Error:** `503 Service Unavailable` if email delivery is required but not
  configured.

#### 10. Verify password-reset code

- **Method and path:** `POST /api/v1/auth/password-reset/verify`
- **Purpose:** Check the one-time code and issue a short-lived reset token.
- **API module:** `api/v1/auth.py` (`verify_password_reset`)
- **Service:** `services/password_reset.py`
- **Request body:**

```json
{
  "identifier": "student@example.com",
  "code": "123456"
}
```

- `identifier`: required email address or student roll number.
- `code`: required six-digit code.
- **Path/query parameters:** None.
- **Success:** HTTP `200 OK`.

```json
{
  "reset_token": "<short-lived reset token>",
  "expires_in_seconds": 900
}
```

- **Error:** `400 Bad Request` for an invalid, expired, consumed, or locked
  code. At most five incorrect attempts are allowed.

#### 11. Confirm password reset

- **Method and path:** `POST /api/v1/auth/password-reset/confirm`
- **Purpose:** Set a new password using the reset token. Existing access tokens
  are invalidated.
- **API module:** `api/v1/auth.py` (`confirm_password_reset`)
- **Service:** `services/password_reset.py` (`reset_student_password`)
- **Request body:**

```json
{
  "reset_token": "<reset token from the verify step>",
  "new_password": "<new password, 8 to 128 characters>"
}
```

- `reset_token`: required, 32-128 characters; expires 15 minutes after code
  verification.
- `new_password`: required, 8-128 characters.
- **Path/query parameters:** None.
- **Success:** HTTP `200 OK`.

```json
{
  "message": "Your password has been reset. Please sign in with your new password."
}
```

- **Error:** `400 Bad Request` for an invalid, expired, or already-used token.

### Auth flow summaries

#### New account

1. `POST /register` creates a pending account and sends or returns a verification
   code, depending on configuration.
2. `POST /verify-email` verifies the code and returns authentication tokens.
3. Use the access token as a Bearer token for `/me` endpoints.

#### Returning account

1. `POST /login` returns access and refresh tokens.
2. When the access token expires, `POST /refresh` exchanges the refresh token
   for new tokens.
3. `POST /logout` revokes the refresh token.

#### Forgot password

1. `POST /password-reset/request` requests a one-time code.
2. `POST /password-reset/verify` exchanges the code for a reset token.
3. `POST /password-reset/confirm` uses that token to set a new password.

### Notes

- Passwords are hashed before being stored. Never send or store a plain-text
  password in a response.
- Verification and reset codes are stored as hashes, expire, and have attempt
  and resend limits.
- Development-only code-return settings must remain disabled in production.
- Configure SMTP settings for email delivery. Do not put SMTP credentials or
  session secrets in this document.
- The authentication route definitions and schemas are the source of truth;
  update this document when their contract changes.
