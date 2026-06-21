# OnboardHub API Documentation

## Base URL
Development: http://localhost:8000/api/
Production: https://api.onboardhub.com/api/

## Authentication
All API requests require authentication via Django session or token.

### Login
POST /auth/login/
Body: { "email": "user@company.com", "password": "password" }
Response: { "id": 1, "token": "abc123xyz" }

## Endpoints

### Employees
GET /employees/ - List all employees (paginated)
GET /employees/{id}/ - Get employee details
POST /employees/ - Create new employee
PUT /employees/{id}/ - Update employee

### Onboarding Plans
GET /onboarding-plans/ - List 30/60/90 plans
GET /onboarding-plans/{id}/ - Get plan details
POST /onboarding-plans/ - Create new plan
POST /onboarding-plans/{id}/milestone-complete/ - Mark milestone done

### Chat & Messaging
GET /messages/ - List conversations
GET /messages/{user_id}/ - Get conversation with user
POST /messages/{user_id}/send/ - Send message

### Analytics
GET /analytics/summary/ - Overall metrics
GET /analytics/employees/ - Per-employee stats
GET /analytics/export/?format=csv - Export to CSV

### Settings
GET /settings/portal/ - Portal configuration
POST /settings/portal/ - Update portal settings
GET /settings/zoom/ - Zoom configuration
POST /settings/zoom/ - Update Zoom settings
POST /settings/zoom/test/ - Test Zoom connection

## Error Responses
400 Bad Request, 401 Unauthorized, 403 Forbidden, 404 Not Found, 500 Server Error

## Rate Limiting
1000 requests/hour per user

## Pagination
- page: page number (default: 1)
- per_page: items per page (default: 20, max: 100)
