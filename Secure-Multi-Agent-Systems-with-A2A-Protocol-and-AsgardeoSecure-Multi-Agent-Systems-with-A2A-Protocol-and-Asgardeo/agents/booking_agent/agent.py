"""
Booking Agent - A2A Server with Token Validation.
Returns mock booking data after validating access token.
"""

import logging
from typing import Optional, Dict, Any, AsyncIterable, List
from jose import jwt
import json

logger = logging.getLogger(__name__)


# Mock booking data
MOCK_FLIGHTS = [
    {
        "flight_id": "FL001",
        "airline": "British Airways",
        "from": "New York (JFK)",
        "to": "London (LHR)",
        "departure": "2024-12-15 08:00",
        "arrival": "2024-12-15 20:00",
        "price": 650.00,
        "class": "Economy"
    },
    {
        "flight_id": "FL002",
        "airline": "Virgin Atlantic",
        "from": "New York (JFK)",
        "to": "London (LHR)",
        "departure": "2024-12-15 10:30",
        "arrival": "2024-12-15 22:30",
        "price": 720.00,
        "class": "Economy"
    },
    {
        "flight_id": "FL003",
        "airline": "United Airlines",
        "from": "New York (JFK)",
        "to": "London (LHR)",
        "departure": "2024-12-15 14:00",
        "arrival": "2024-12-16 02:00",
        "price": 580.00,
        "class": "Economy"
    }
]

MOCK_HOTELS = [
    {
        "hotel_id": "HT001",
        "name": "The Ritz London",
        "location": "Piccadilly, London",
        "rating": 5,
        "price_per_night": 450.00,
        "amenities": ["Spa", "Restaurant", "WiFi", "Gym"]
    },
    {
        "hotel_id": "HT002",
        "name": "Premier Inn London City",
        "location": "Tower Hill, London",
        "rating": 3,
        "price_per_night": 120.00,
        "amenities": ["WiFi", "Breakfast"]
    }
]


class BookingAgent:
    """
    Booking Agent - validates tokens and returns mock data.
    No Asgardeo app, just validates incoming tokens.
    """
    
    SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]
    REQUIRED_SCOPES = ["booking:read", "booking:write"]
    
    def __init__(self, config: dict):
        self.config = config
        self.issuer = config.get('token_validation', {}).get(
            'issuer', 'https://api.asgardeo.io/t/a2abasic/oauth2/token'
        )
        logger.info("Booking Agent initialized")
        logger.info(f"  Required scopes: {self.REQUIRED_SCOPES}")
    
    def validate_token(self, token: str) -> Dict[str, Any]:
        """
        Validate access token and check scopes.
        Returns decoded claims if valid.
        """
        if not token:
            return {"valid": False, "error": "No token provided"}
        
        try:
            # Decode without verification for scope checking
            # In production, verify signature with Asgardeo JWKS
            claims = jwt.get_unverified_claims(token)
            
            # Check issuer
            if claims.get('iss') != self.issuer:
                logger.warning(f"Invalid issuer: {claims.get('iss')}")
                # Don't fail for now, just warn
            
            # Check scopes
            token_scopes = claims.get('scope', '').split()
            has_read = 'booking:read' in token_scopes
            has_write = 'booking:write' in token_scopes
            
            if not (has_read or has_write):
                # Check for any booking-related scope
                has_booking = any('booking' in s.lower() for s in token_scopes)
                if not has_booking:
                    logger.warning(f"Missing booking scopes. Token has: {token_scopes}")
            
            return {
                "valid": True,
                "claims": claims,
                "sub": claims.get('sub'),
                "scopes": token_scopes
            }
            
        except Exception as e:
            logger.error(f"Token validation error: {e}")
            return {"valid": False, "error": str(e)}
    
    def search_flights(self, destination: str) -> List[Dict]:
        """Search mock flights."""
        # Simple filter - in real app would query DB
        flights = [f for f in MOCK_FLIGHTS if destination.lower() in f['to'].lower()]
        return flights if flights else MOCK_FLIGHTS
    
    def search_hotels(self, location: str) -> List[Dict]:
        """Search mock hotels."""
        hotels = [h for h in MOCK_HOTELS if location.lower() in h['location'].lower()]
        return hotels if hotels else MOCK_HOTELS
    
    async def process_booking_request(
        self, 
        query: str, 
        token: Optional[str] = None
    ) -> str:
        """
        Process booking request.
        Validates token and returns mock data.
        """
        logger.info(f"Processing: {query[:50]}...")
        
        # Validate token
        if token:
            validation = self.validate_token(token)
            if validation.get('valid'):
                logger.info(f"Token valid for user: {validation.get('sub')}")
            else:
                logger.warning(f"Token validation: {validation.get('error')}")
        else:
            logger.warning("No token provided - proceeding anyway for demo")
        
        # Parse query and return appropriate data
        query_lower = query.lower()
        
        if 'flight' in query_lower:
            # Extract destination
            destination = "London"  # Default
            if 'to' in query_lower:
                parts = query_lower.split('to')
                if len(parts) > 1:
                    destination = parts[1].strip().split()[0].title()
            
            flights = self.search_flights(destination)
            
            response = f"🛫 **Available Flights to {destination}:**\n\n"
            for f in flights:
                response += f"**{f['airline']}** - {f['flight_id']}\n"
                response += f"  {f['from']} → {f['to']}\n"
                response += f"  Departure: {f['departure']}\n"
                response += f"  Price: ${f['price']:.2f} ({f['class']})\n\n"
            
            return response
        
        elif 'hotel' in query_lower:
            location = "London"
            hotels = self.search_hotels(location)
            
            response = f"🏨 **Available Hotels in {location}:**\n\n"
            for h in hotels:
                stars = "⭐" * h['rating']
                response += f"**{h['name']}** {stars}\n"
                response += f"  Location: {h['location']}\n"
                response += f"  Price: ${h['price_per_night']:.2f}/night\n"
                response += f"  Amenities: {', '.join(h['amenities'])}\n\n"
            
            return response
        
        else:
            # General travel query
            return (
                "🌍 **Travel Booking Assistant**\n\n"
                "I can help you with:\n"
                "- ✈️ Flight bookings\n"
                "- 🏨 Hotel reservations\n\n"
                "Try: 'Find flights to London' or 'Search hotels in London'"
            )
    
    async def stream(
        self, 
        query: str, 
        token: Optional[str] = None
    ) -> AsyncIterable[Dict[str, Any]]:
        """Stream response."""




        
        response = await self.process_booking_request(query, token)
        yield {"content": response}
