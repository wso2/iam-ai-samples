# Hotel API

A FastAPI-based API for managing hotel details and user bookings.

## Prerequisites

- Python 3.8+
- pip (Python package manager)

## Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd agent_demo_hotel_api
   ```

2. **Create a virtual environment** (recommended)
   ```bash
   python -m venv venv
   
   # On Windows
   venv\Scripts\activate
   
   # On macOS/Linux
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

## Configuration

1. **Create environment file**
   ```bash
   cp .env.example .env
   ```

2. **Configure environment variables**
   
   Edit the `.env` file with your settings:
   ```env
   # JWT Configuration
   JWKS_URL=https://api.asgardeo.io/t/<org_name>/oauth2/jwks
   JWT_ISSUER=https://api.asgardeo.io/t/<org_name>/oauth2/token
   JWKS_CACHE_TTL=3600

   # CORS Configuration
   CORS_ORIGINS=http://localhost:3000,https://localhost:3000,http://localhost:3001
   CORS_CREDENTIALS=true
   CORS_METHODS=*
   CORS_HEADERS=*
   ```

   **Environment Variables:**
   
   **JWT Configuration:**
   - `JWKS_URL`: Direct URL to your JWKS endpoint (Required)
   - `JWT_ISSUER`: JWT issuer for token validation (Optional - only validates if provided)
   - `JWKS_CACHE_TTL`: Cache timeout for JWKS in seconds (Default: 3600)

   **CORS Configuration:**
   - `CORS_ORIGINS`: Comma-separated list of allowed origins (Default: http://localhost:3000,https://localhost:3000)
   - `CORS_CREDENTIALS`: Allow credentials in CORS requests (Default: true)
   - `CORS_METHODS`: Comma-separated list of allowed HTTP methods, or '*' for all (Default: *)
   - `CORS_HEADERS`: Comma-separated list of allowed headers, or '*' for all (Default: *)

## Running the API

Start the development server:

```bash
uvicorn app.main:app --reload --port 8001
```

The API will be available at: `http://localhost:8001`

### API Documentation

Once the server is running, you can access:
- **Interactive API docs (Swagger UI)**: http://localhost:8001/docs
- **Alternative API docs (ReDoc)**: http://localhost:8001/redoc
- **OpenAPI JSON**: http://localhost:8001/openapi.json

## Authentication

The API uses JWT Bearer token authentication. Include your JWT token in the Authorization header:

```
Authorization: Bearer <your-jwt-token>
```

### Required Token Claims

Your JWT token must include:
- `sub`: Subject (user identifier)
- `scope`: Space-separated list of scopes
- Token must be signed and verifiable using the configured JWKS

### Token Scopes

- `read_hotels`: View hotel listings
- `read_rooms`: View room details
- `read_bookings`: View booking information
- `create_bookings`: Create new bookings

## API Endpoints

### Hotels
- `GET /api/hotels` - List all hotels (requires `read_hotels` scope)
- `GET /api/hotels/{hotel_id}` - Get hotel details with rooms (requires `read_rooms` scope)


### Bookings
- `POST /api/bookings` - Create a new booking (requires `create_bookings` scope)
- `GET /api/bookings/{booking_id}` - Get booking details (requires `read_bookings` scope)

### Users
- `GET /api/users/{user_id}/bookings` - Get user's bookings (requires `read_bookings` scope)

## Example Usage

### List Hotels
```bash
curl -H "Authorization: Bearer <your-token>" \
     http://localhost:8001/api/hotels
```

### Create Booking
```bash
curl -X POST \
     -H "Authorization: Bearer <your-token>" \
     -H "Content-Type: application/json" \
     -d '{
       "hotel_id": 1,
       "room_id": 101,
       "check_in": "2024-03-01",
       "check_out": "2024-03-05"
     }' \
     http://localhost:8001/api/bookings
```

## Development

### Project Structure
```
agent_demo_hotel_api/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI application and endpoints
│   ├── dependencies.py     # JWT validation and JWKS client
│   └── schemas.py           # Pydantic models
├── requirements.txt         # Python dependencies
├── .env.example            # Environment configuration template
├── .env                    # Your environment configuration (create this)
├── Procfile                # Deployment configuration
└── README.md               # This file
```

### Adding New Dependencies

1. Add the package to `requirements.txt`
2. Install it: `pip install <package-name>`

### CORS Configuration

The API is configured to allow requests from:
- `http://localhost:3000`
- `https://localhost:3000`

Modify the CORS settings in `app/main.py` if needed.

## Security Features

- **JWT Signature Validation**: Tokens are validated using JWKS
- **Scope-based Authorization**: Different endpoints require specific scopes
- **Token Expiration**: Expired tokens are rejected
- **Issuer Validation**: Optional issuer validation
- **JWKS Caching**: Reduces external API calls with configurable TTL

## Troubleshooting

### Common Issues

1. **"JWKS_URL environment variable not set"**
   - Ensure your `.env` file exists and contains the `JWKS_URL` variable

2. **"Unable to fetch JWKS"**
   - Check your internet connection
   - Verify the JWKS URL is accessible
   - Check if your authorization server is running

3. **"Token validation failed"**
   - Ensure your JWT token is valid and not expired
   - Verify the token was signed by the correct authorization server
   - Check that the token includes required scopes

4. **Import Errors**
   - Make sure all dependencies are installed: `pip install -r requirements.txt`
   - Verify you're using Python 3.8 or higher

### Debug Mode

For development, you can enable debug logging by setting the log level in your environment or code.

## License

[Add your license information here]

## Contributing

[Add contributing guidelines here]
