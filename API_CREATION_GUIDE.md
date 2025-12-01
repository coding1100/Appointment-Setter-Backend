# Step-by-Step Guide: Creating POST API with Optional Email and Phone Number

## Overview
This guide explains how to create a POST API endpoint that accepts `email` and `phone_number` as optional fields, but requires at least one to be provided.

## ✅ What Has Been Created

### 1. **Schema File** (`app/api/v1/schemas/contact.py`)
   - Created `ContactCreate` schema with:
     - `email`: Optional EmailStr field
     - `phone_number`: Optional string field
     - Validation to ensure at least one field is provided
     - Phone number format validation

### 2. **Router File** (`app/api/v1/routers/contacts.py`)
   - Created POST endpoint at `/api/v1/contacts`
   - Handles contact/lead submissions
   - Returns proper HTTP status codes

### 3. **API Registration** (`app/api/v1/api.py`)
   - Registered the contacts router in the main API router

## 📋 API Endpoint Details

### Endpoint
```
POST /api/v1/contacts
```

### Request Body
```json
{
  "email": "user@example.com",        // Optional
  "phone_number": "+1234567890"        // Optional
}
```

**Note**: At least one of `email` or `phone_number` must be provided.

### Valid Request Examples

✅ **With email only:**
```json
{
  "email": "user@example.com"
}
```

✅ **With phone only:**
```json
{
  "phone_number": "+1234567890"
}
```

✅ **With both:**
```json
{
  "email": "user@example.com",
  "phone_number": "+1234567890"
}
```

❌ **Invalid (neither provided):**
```json
{}
```
This will return a 400 error: "At least one of 'email' or 'phone_number' must be provided"

### Response
```json
{
  "id": "uuid-here",
  "email": "user@example.com",
  "phone_number": "+1234567890",
  "created_at": "2024-01-01T12:00:00"
}
```

## 🚀 How to Use the API

### 1. Start the Server
```bash
# Activate virtual environment
venv\Scripts\activate  # Windows
# or
source venv/bin/activate  # Linux/Mac

# Start the server
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 2. Access API Documentation
Once the server is running, visit:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### 3. Test the API

#### Using cURL:
```bash
# With email only
curl -X POST "http://localhost:8000/api/v1/contacts" \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com"}'

# With phone only
curl -X POST "http://localhost:8000/api/v1/contacts" \
  -H "Content-Type: application/json" \
  -d '{"phone_number": "+1234567890"}'

# With both
curl -X POST "http://localhost:8000/api/v1/contacts" \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "phone_number": "+1234567890"}'
```

#### Using JavaScript (Frontend):
```javascript
// Example: Using fetch API
async function submitContact(email, phoneNumber) {
  const response = await fetch('http://localhost:8000/api/v1/contacts', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      email: email || undefined,  // Only include if provided
      phone_number: phoneNumber || undefined
    })
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to submit contact');
  }

  return await response.json();
}

// Usage examples:
// submitContact('user@example.com', null);
// submitContact(null, '+1234567890');
// submitContact('user@example.com', '+1234567890');
```

#### Using React Example:
```jsx
import { useState } from 'react';

function ContactForm() {
  const [email, setEmail] = useState('');
  const [phoneNumber, setPhoneNumber] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    // Validate at least one field is provided
    if (!email && !phoneNumber) {
      setError('Please provide either email or phone number');
      return;
    }

    setLoading(true);
    setError('');

    try {
      const response = await fetch('http://localhost:8000/api/v1/contacts', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          ...(email && { email }),
          ...(phoneNumber && { phone_number: phoneNumber }),
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to submit');
      }

      const data = await response.json();
      console.log('Contact submitted:', data);
      // Reset form or show success message
      setEmail('');
      setPhoneNumber('');
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      <div>
        <label>Email (optional):</label>
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
      </div>
      <div>
        <label>Phone Number (optional):</label>
        <input
          type="tel"
          value={phoneNumber}
          onChange={(e) => setPhoneNumber(e.target.value)}
        />
      </div>
      {error && <div style={{ color: 'red' }}>{error}</div>}
      <button type="submit" disabled={loading}>
        {loading ? 'Submitting...' : 'Submit'}
      </button>
    </form>
  );
}
```

## 🔧 Next Steps (Optional Enhancements)

### 1. **Save to Database**
Currently, the endpoint returns the contact data but doesn't save it. To save to Firebase Firestore:

1. Create a service file: `app/api/v1/services/contact.py`
2. Add Firebase save logic
3. Update the router to use the service

### 2. **Add Authentication** (if needed)
If you want to protect this endpoint, add authentication:

```python
from app.api.v1.routers.auth import get_current_user_from_token

@router.post("", response_model=ContactResponse)
async def create_contact(
    contact_data: ContactCreate,
    current_user: Dict = Depends(get_current_user_from_token)
):
    # ... existing code
```

### 3. **Add Rate Limiting**
To prevent abuse, consider adding rate limiting middleware.

## 📁 File Structure

```
app/
├── api/
│   └── v1/
│       ├── api.py                    # ✅ Updated - registered contacts router
│       ├── routers/
│       │   └── contacts.py            # ✅ Created - new router
│       └── schemas/
│           └── contact.py             # ✅ Created - new schema
```

## ✅ Validation Rules

1. **Email**: Must be a valid email format (validated by Pydantic's EmailStr)
2. **Phone Number**: 
   - Can contain formatting characters: `-`, ` `, `(`, `)`, `+`
   - Must be 10-15 digits after removing formatting
3. **At Least One Required**: Either email or phone_number (or both) must be provided

## 🐛 Troubleshooting

### Issue: "email-validator is not installed"
**Solution**: Install the package:
```bash
pip install email-validator
```
Or it should already be in your `requirements.txt` as `email-validator`.

### Issue: Validation error "At least one of 'email' or 'phone_number' must be provided"
**Solution**: Make sure you're sending at least one field in the request body.

### Issue: Phone number validation fails
**Solution**: Ensure phone number is 10-15 digits (formatting characters are allowed but will be stripped for validation).

## 📝 Summary

You now have a fully functional POST API endpoint at `/api/v1/contacts` that:
- ✅ Accepts optional `email` and `phone_number` fields
- ✅ Requires at least one field to be provided
- ✅ Validates email format
- ✅ Validates phone number format
- ✅ Returns proper HTTP status codes
- ✅ Is ready to integrate with your frontend

The API is accessible at: `POST http://localhost:8000/api/v1/contacts`

