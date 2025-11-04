# دليل APIs - وحدة الموارد البشرية

**Base URL:** `/hr/api/`  
**Authentication:** Token Required  
**Format:** JSON

---

## Endpoints

### 1. Employees

#### List & Create
```http
GET  /hr/api/employees/
POST /hr/api/employees/
```

**Filters:**
- `status` - active, on_leave, terminated
- `department` - Department ID
- `employment_type` - full_time, part_time, contract

**Search:** `first_name_ar`, `last_name_ar`, `employee_number`

**Example:**
```bash
GET /hr/api/employees/?status=active&department=1
```

#### Retrieve, Update, Delete
```http
GET    /hr/api/employees/{id}/
PUT    /hr/api/employees/{id}/
PATCH  /hr/api/employees/{id}/
DELETE /hr/api/employees/{id}/
```

#### Custom Actions
```http
POST /hr/api/employees/{id}/terminate/
GET  /hr/api/employees/{id}/summary/
```

---

### 2. Departments

```http
GET    /hr/api/departments/
POST   /hr/api/departments/
GET    /hr/api/departments/{id}/
PUT    /hr/api/departments/{id}/
DELETE /hr/api/departments/{id}/
```

**Filters:** `is_active`, `parent`

---

### 3. Attendance

```http
GET  /hr/api/attendance/
POST /hr/api/attendance/
GET  /hr/api/attendance/{id}/
```

#### Check In/Out
```http
POST /hr/api/attendance/check_in/
POST /hr/api/attendance/check_out/
```

**Request Body (Check In):**
```json
{
  "employee_id": 1,
  "shift_id": 1
}
```

**Request Body (Check Out):**
```json
{
  "employee_id": 1
}
```

#### Monthly Stats
```http
GET /hr/api/attendance/monthly_stats/?employee_id=1&month=2025-11
```

**Filters:** `employee`, `date`, `status`, `shift`

---

### 4. Leaves

```http
GET    /hr/api/leaves/
POST   /hr/api/leaves/
GET    /hr/api/leaves/{id}/
PUT    /hr/api/leaves/{id}/
DELETE /hr/api/leaves/{id}/
```

#### Approve/Reject
```http
POST /hr/api/leaves/{id}/approve/
POST /hr/api/leaves/{id}/reject/
```

**Request Body (Approve):**
```json
{
  "review_notes": "معتمدة"
}
```

**Filters:** `status`, `employee`, `leave_type`, `start_date`

---

### 5. Payroll

```http
GET  /hr/api/payroll/
POST /hr/api/payroll/
GET  /hr/api/payroll/{id}/
```

#### Process Monthly
```http
POST /hr/api/payroll/process_monthly/
```

**Request Body:**
```json
{
  "month": "2025-11",
  "department_id": null
}
```

#### Approve
```http
POST /hr/api/payroll/{id}/approve/
```

**Filters:** `status`, `month`, `employee`, `payment_method`

---

### 6. Leave Types

```http
GET    /hr/api/leave-types/
POST   /hr/api/leave-types/
GET    /hr/api/leave-types/{id}/
PUT    /hr/api/leave-types/{id}/
DELETE /hr/api/leave-types/{id}/
```

---

### 7. Leave Balances

```http
GET    /hr/api/leave-balances/
POST   /hr/api/leave-balances/
GET    /hr/api/leave-balances/{id}/
PUT    /hr/api/leave-balances/{id}/
```

**Filters:** `employee`, `leave_type`, `year`

---

### 8. Salaries

```http
GET    /hr/api/salaries/
POST   /hr/api/salaries/
GET    /hr/api/salaries/{id}/
PUT    /hr/api/salaries/{id}/
```

**Filters:** `employee`, `is_active`

---

### 9. Advances

```http
GET    /hr/api/advances/
POST   /hr/api/advances/
GET    /hr/api/advances/{id}/
PUT    /hr/api/advances/{id}/
```

#### Approve
```http
POST /hr/api/advances/{id}/approve/
```

**Filters:** `employee`, `status`, `deducted`

---

### 10. Job Titles

```http
GET    /hr/api/job-titles/
POST   /hr/api/job-titles/
GET    /hr/api/job-titles/{id}/
PUT    /hr/api/job-titles/{id}/
DELETE /hr/api/job-titles/{id}/
```

---

### 11. Shifts

```http
GET    /hr/api/shifts/
POST   /hr/api/shifts/
GET    /hr/api/shifts/{id}/
PUT    /hr/api/shifts/{id}/
DELETE /hr/api/shifts/{id}/
```

---

## Permissions

| Endpoint | Permission |
|----------|-----------|
| Employees (List/Read) | IsAuthenticated |
| Employees (Create/Update) | IsHRStaff |
| Employees (Delete) | IsHRManager |
| Attendance (Own) | IsAuthenticated |
| Attendance (All) | IsHRStaff |
| Leaves (Request) | IsAuthenticated |
| Leaves (Approve) | CanApproveLeave |
| Payroll (View Own) | IsAuthenticated |
| Payroll (Process) | CanProcessPayroll |
| Departments (Manage) | CanManageDepartment |

---

## Response Format

### Success (200/201)
```json
{
  "id": 1,
  "field1": "value1",
  "field2": "value2"
}
```

### Error (400/403/404)
```json
{
  "error": "Error message",
  "details": {}
}
```

### List Response
```json
{
  "count": 100,
  "next": "http://api/hr/api/employees/?page=2",
  "previous": null,
  "results": [...]
}
```

---

## Examples

### Create Employee
```bash
curl -X POST http://localhost:8000/hr/api/employees/ \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "employee_number": "EMP001",
    "first_name_ar": "أحمد",
    "last_name_ar": "محمد",
    "department": 1,
    "job_title": 1,
    "hire_date": "2025-01-01"
  }'
```

### Check In
```bash
curl -X POST http://localhost:8000/hr/api/attendance/check_in/ \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "employee_id": 1,
    "shift_id": 1
  }'
```

### Approve Leave
```bash
curl -X POST http://localhost:8000/hr/api/leaves/1/approve/ \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "review_notes": "معتمدة"
  }'
```

### Process Payroll
```bash
curl -X POST http://localhost:8000/hr/api/payroll/process_monthly/ \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "month": "2025-11"
  }'
```

---

**آخر تحديث:** 2025-11-03
