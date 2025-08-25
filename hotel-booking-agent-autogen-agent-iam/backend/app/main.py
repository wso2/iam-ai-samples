import logging
import os
import uuid
import hashlib
import httpx
import asyncio
from fastapi import FastAPI, HTTPException, Security, APIRouter, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from datetime import date, datetime
from .schemas import *
from .dependencies import TokenData, validate_token
from data import (
    hotels_data, rooms_data, bookings_data, last_booking_id, last_assignment_id,
    reviews_data, last_review_id, users_data, staff_data
)
from .services import scim_service
from .services.jwt_client import jwt_client
from dotenv import load_dotenv

load_dotenv()

# Staff Management Agent service configuration
STAFF_MANAGEMENT_AGENT_URL = os.getenv('STAFF_MANAGEMENT_AGENT_URL', 'http://localhost:8002')
AGENT_WEBHOOK_TIMEOUT = int(os.getenv('AGENT_WEBHOOK_TIMEOUT', '10'))  # seconds

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

def log_request_details(request: Request, token_data: TokenData, extra_info: dict = None):
    """Enhanced logging function with structured information"""
    endpoint = request.url.path
    method = request.method
    sub = token_data.sub
    act = token_data.act.sub if token_data.act else "N/A"
    
    # Get client IP
    client_ip = request.client.host if request.client else 'N/A'
    
    # Get user agent
    user_agent = request.headers.get('user-agent', 'N/A')
    
    # Build log message
    log_data = {
        "method": method,
        "endpoint": endpoint,
        "client_ip": client_ip,
        "user_id": sub,
        "actor": act,
        "user_agent": user_agent[:100] + "..." if len(user_agent) > 100 else user_agent
    }
    
    # Add extra information if provided
    if extra_info:
        log_data.update(extra_info)
    
    # Create structured log message
    log_message = " | ".join([
        f"{method} {endpoint}",
        f"sub: {sub}",
        f"act: {act}",
    ])
    
    # Add extra info to message if provided
    if extra_info:
        extra_parts = []
        for key, value in extra_info.items():
            extra_parts.append(f"{key}: {value}")
        if extra_parts:
            log_message += " | " + " | ".join(extra_parts)
    
    logger.info(log_message)

def generate_confirmation_number() -> str:
    """Generate a unique confirmation number"""
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    random_part = str(uuid.uuid4())[:8].upper()
    return f"GRD-{timestamp[:8]}-{random_part}"

def anonymize_reviewer_name(user_id: str) -> str:
    """Generate anonymized reviewer name"""
    hash_obj = hashlib.md5(user_id.encode())
    return f"Guest{hash_obj.hexdigest()[:6].upper()}"

def convert_review_to_public(review: dict) -> dict:
    """Convert internal review to public review format"""
    public_review = review.copy()
    # Remove sensitive fields
    public_review.pop('booking_id', None)
    public_review.pop('user_id', None)
    # Add anonymized reviewer name
    public_review['reviewer_name'] = anonymize_reviewer_name(review['user_id'])
    return public_review

async def enrich_booking_with_user_agent_info(booking: dict) -> dict:
    """Enrich booking data with user and agent details from Asgardeo SCIM API"""
    enriched_booking = booking.copy()
    
    # Add user details
    user_info = None
    if booking.get('user_id'):
        # Try SCIM API first, fallback to local data
        scim_user = await scim_service.get_user_info(booking['user_id'])
        if scim_user:
            user_info = {
                "id": scim_user['id'],
                "email": scim_user['email'],
                "first_name": scim_user['first_name'],
                "last_name": scim_user['last_name'],
                "display_name": scim_user['display_name'],
                "source": scim_user['source']
            }
        elif booking['user_id'] in users_data:
            # Fallback to local data
            user_data = users_data[booking['user_id']]
            user_info = {
                "id": user_data['id'],
                "email": user_data['email'],
                "first_name": user_data['first_name'],
                "last_name": user_data['last_name'],
                "display_name": f"{user_data['first_name']} {user_data['last_name']}",
                "phone": user_data.get('phone'),
                "loyalty_tier": user_data.get('loyalty_tier'),
                "source": "local_data"
            }
    
    # Add agent details
    agent_info = None
    if booking.get('agent_id'):
        # Try SCIM API first, fallback to local data
        scim_agent = await scim_service.get_agent_info(booking['agent_id'])
        if scim_agent:
            agent_info = {
                "id": scim_agent['id'],
                "display_name": scim_agent['display_name'],
                "description": scim_agent['description'],
                "ai_model": scim_agent['ai_model'],
                "source": scim_agent['source']
            }
        elif booking['agent_id'] in users_data:
            # Fallback to local data (treating as user for backward compatibility)
            agent_data = users_data[booking['agent_id']]
            agent_info = {
                "id": agent_data['id'],
                "email": agent_data['email'],
                "first_name": agent_data['first_name'],
                "last_name": agent_data['last_name'],
                "display_name": f"{agent_data['first_name']} {agent_data['last_name']}",
                "phone": agent_data.get('phone'),
                "source": "local_data"
            }
    
    # Add enriched data to booking
    enriched_booking['user_info'] = user_info
    enriched_booking['agent_info'] = agent_info
    
    return enriched_booking

async def invoke_staff_management_agent(booking_id: int, user_id: str, hotel_id: int, priority: str = "normal") -> None:
    """Invoke staff management agent for contact person assignment"""
    try:
        # Get JWT token for invoking the agent
        access_token = await jwt_client.get_access_token("invoke")
        if not access_token:
            logger.error(f"Failed to get access token for webhook call - booking {booking_id}")
            return
        
        payload = {
            "event_type": "booking.auto_assign_requested",
            "booking_id": booking_id,
            "user_id": user_id,
            "hotel_id": hotel_id,
            "priority": priority,
            "timestamp": datetime.now().isoformat(),
            "source": "hotel_api"
        }
        
        url = f"{STAFF_MANAGEMENT_AGENT_URL}/v1/invoke"
        
        async with httpx.AsyncClient(timeout=AGENT_WEBHOOK_TIMEOUT) as client:
            response = await client.post(
                url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {access_token}"
                }
            )
            response.raise_for_status()

            logger.info(f"Invoked the staff management agent for booking {booking_id}")
            
    except httpx.TimeoutException:
        logger.error(f"Timeout for booking {booking_id} - staff management agent service may be unavailable")
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error for booking {booking_id}: {e.response.status_code} - {e.response.text}")
    except Exception as e:
        logger.error(f"Failed to invoke staff management agent for booking {booking_id}: {str(e)}")

app = FastAPI(
    title="Hotel API",
    description="API for managing hotel bookings, reviews, and user interactions.",
    version="2.1.0"
)
api_router = APIRouter(prefix="/api")

# CORS Configuration
def get_cors_origins():
    """Get CORS origins from environment variable"""
    cors_origins = os.getenv('CORS_ORIGINS', 'http://localhost:3000,https://localhost:3000')
    return [origin.strip() for origin in cors_origins.split(',')]

def get_cors_methods():
    """Get CORS methods from environment variable"""
    cors_methods = os.getenv('CORS_METHODS', '*')
    if cors_methods == '*':
        return ["*"]
    return [method.strip() for method in cors_methods.split(',')]

def get_cors_headers():
    """Get CORS headers from environment variable"""
    cors_headers = os.getenv('CORS_HEADERS', '*')
    if cors_headers == '*':
        return ["*"]
    return [header.strip() for header in cors_headers.split(',')]

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=os.getenv('CORS_CREDENTIALS', 'true').lower() == 'true',
    allow_methods=get_cors_methods(),
    allow_headers=get_cors_headers(),
)

# === Hotel Endpoints ===
@api_router.get("/hotels", response_model=HotelsResponse)
async def get_hotels(
    request: Request,
    city: Optional[str] = Query(None),
    brand: Optional[str] = Query(None),
    amenities: Optional[List[str]] = Query(None),
    limit: int = Query(20, le=100),
    offset: int = Query(0, ge=0)
):
    """Browse all hotels with filtering options - Public endpoint"""
    logger.info(f"GET /api/hotels - filters: city={city}, brand={brand}")
    
    filtered_hotels = []
    for hotel_id, hotel_data in hotels_data.items():
        # Apply filters
        if city and city.lower() not in hotel_data['address']['city'].lower():
            continue
        if brand and hotel_data['brand'] != brand:
            continue
        if amenities:
            hotel_amenities = [a.lower() for a in hotel_data['amenities']]
            if not all(amenity.lower() in hotel_amenities for amenity in amenities):
                continue
        
        # Remove images from hotel data before creating Hotel object
        hotel_data_clean = hotel_data.copy()
        hotel_data_clean.pop('images', None)
        filtered_hotels.append(Hotel(**hotel_data_clean))
    
    # Apply pagination
    total = len(filtered_hotels)
    paginated_hotels = filtered_hotels[offset:offset + limit]
    
    return HotelsResponse(hotels=paginated_hotels, total=total)

@api_router.post("/hotels/search", response_model=dict)
async def search_hotels(
    request: Request,
    search_request: HotelSearchRequest
):
    """Search hotels with availability - Public endpoint"""
    logger.info(f"POST /api/hotels/search - location: {search_request.location}")
    
    # Filter hotels by location
    available_hotels = []
    for hotel_id, hotel_data in hotels_data.items():
        if search_request.location.lower() in hotel_data['address']['city'].lower():
            # Get available rooms for this hotel
            hotel_rooms = rooms_data.get(hotel_id, {})
            available_rooms = []
            
            for room_id, room_data in hotel_rooms.items():
                if room_data['max_occupancy'] >= search_request.guests:
                    # Check room availability for dates
                    is_available = True
                    for booking in bookings_data.values():
                        if (booking['hotel_id'] == hotel_id and 
                            booking['room_id'] == room_id and
                            booking['status'] == 'confirmed' and
                            not (search_request.check_out <= booking['check_in'] or 
                                 search_request.check_in >= booking['check_out'])):
                            is_available = False
                            break
                    
                    if is_available:
                        room_with_availability = room_data.copy()
                        room_with_availability.pop('images', None)  # Remove images
                        room_with_availability['available'] = True
                        room_with_availability['price_per_night'] = room_data['base_price']
                        available_rooms.append(room_with_availability)
            
            if available_rooms:
                hotel_with_rooms = hotel_data.copy()
                hotel_with_rooms.pop('images', None)  # Remove images
                hotel_with_rooms['available_rooms'] = available_rooms
                hotel_with_rooms['lowest_rate'] = min(room['base_price'] for room in available_rooms)
                available_hotels.append(hotel_with_rooms)
    
    search_id = str(uuid.uuid4())
    return {
        "hotels": available_hotels,
        "search_id": search_id
    }

@api_router.get("/hotels/{hotel_id}", response_model=Hotel)
async def get_hotel(
    request: Request,
    hotel_id: int
):
    """Get hotel details with rooms - Public endpoint"""
    logger.info(f"GET /api/hotels/{hotel_id}")
    
    if hotel_id not in hotels_data:
        raise HTTPException(status_code=404, detail="Hotel not found")
    
    hotel_data_copy = hotels_data[hotel_id].copy()
    
    # Add rooms to hotel data (remove images from both hotel and rooms)
    hotel_rooms = []
    for room_id, room_data in rooms_data.get(hotel_id, {}).items():
        room_data_clean = room_data.copy()
        room_data_clean.pop('images', None)  # Remove images from room data
        hotel_rooms.append(Room(**room_data_clean))
    
    hotel_data_copy['rooms'] = hotel_rooms
    hotel_data_copy.pop('images', None)  # Remove images from hotel data
    
    return Hotel(**hotel_data_copy)

@api_router.get("/hotels/{hotel_id}/reviews", response_model=ReviewsResponse)
async def get_hotel_reviews(
    request: Request,
    hotel_id: int,
    limit: int = Query(10, le=50),
    rating: Optional[float] = Query(None, ge=1, le=5)
):
    """Get hotel reviews (privacy-safe) - Public endpoint"""
    logger.info(f"GET /api/hotels/{hotel_id}/reviews - limit: {limit}, rating: {rating}")
    
    if hotel_id not in hotels_data:
        raise HTTPException(status_code=404, detail="Hotel not found")
    
    # Filter reviews for this hotel
    hotel_reviews = []
    for review_id, review_data in reviews_data.items():
        if (review_data['hotel_id'] == hotel_id and 
            review_data['review_type'] == 'hotel'):
            if rating is None or review_data['rating'] >= rating:
                public_review = convert_review_to_public(review_data)
                hotel_reviews.append(PublicReview(**public_review))
    
    # Sort by creation date (newest first)
    hotel_reviews.sort(key=lambda x: x.created_at, reverse=True)
    
    # Apply limit
    limited_reviews = hotel_reviews[:limit]
    
    # Calculate summary
    if hotel_reviews:
        avg_rating = sum(r.rating for r in hotel_reviews) / len(hotel_reviews)
        summary = {
            "average_rating": round(avg_rating, 2),
            "total_reviews": len(hotel_reviews)
        }
    else:
        summary = {"average_rating": 0, "total_reviews": 0}
    
    return ReviewsResponse(
        reviews=limited_reviews,
        total=len(hotel_reviews),
        summary=summary
    )

# === Booking Endpoints ===
@api_router.post("/bookings", response_model=Booking)
async def create_booking(
    request: Request,
    booking_request: BookingCreate,
    token_data: TokenData = Security(validate_token, scopes=["create_bookings"])
):
    """Create a new booking"""
    log_request_details(request, token_data, {"booking": f"hotel_{booking_request.hotel_id}_room_{booking_request.room_id}"})
    
    global last_booking_id
    
    # Validate dates
    today = date.today()
    if booking_request.check_in < today:
        raise HTTPException(status_code=400, detail="Check-in date cannot be in the past")
    
    if booking_request.check_out <= booking_request.check_in:
        raise HTTPException(status_code=400, detail="Check-out date must be after check-in date")
    
    # Validate hotel and room exist
    if booking_request.hotel_id not in hotels_data:
        raise HTTPException(status_code=404, detail="Hotel not found")
    
    hotel_rooms = rooms_data.get(booking_request.hotel_id, {})
    if booking_request.room_id not in hotel_rooms:
        raise HTTPException(status_code=404, detail="Room not found in this hotel")
    
    room_data = hotel_rooms[booking_request.room_id]
    hotel_data = hotels_data[booking_request.hotel_id]
    
    # Validate occupancy
    if booking_request.guests > room_data['max_occupancy']:
        raise HTTPException(
            status_code=400,
            detail=f"Room can accommodate maximum {room_data['max_occupancy']} guests"
        )
    
    # Check room availability
    for booking in bookings_data.values():
        if (booking['hotel_id'] == booking_request.hotel_id and 
            booking['room_id'] == booking_request.room_id and
            booking['status'] == 'confirmed' and
            not (booking_request.check_out <= booking['check_in'] or 
                 booking_request.check_in >= booking['check_out'])):
            raise HTTPException(
                status_code=400,
                detail=f"Room is not available for the selected dates"
            )
    
    # Calculate total amount
    days = (booking_request.check_out - booking_request.check_in).days
    total_amount = room_data['base_price'] * days
    
    # Create booking
    last_booking_id += 1
    
    # Determine user and agent from OAuth token claims
    # If user_id is provided in request, use it; otherwise use token sub (the actual user)
    user_id = booking_request.user_id or token_data.sub
    
    # Check if there's an agent (act claim) making the booking
    agent_id = None
    created_by = "user"
    
    # Debug logging for token claims
    logger.info(f"Token claims - sub: {token_data.sub}, act: {token_data.act}")
    if token_data.act:
        logger.info(f"Act claim details - type: {type(token_data.act)}, value: {token_data.act}")
        if hasattr(token_data.act, 'sub'):
            logger.info(f"Act.sub: {token_data.act.sub}")
    
    # More robust check for agent presence
    if (token_data.act and 
        hasattr(token_data.act, 'sub') and 
        token_data.act.sub and 
        token_data.act.sub.strip()):
        # Agent is making the booking (act.sub is the agent)
        agent_id = token_data.act.sub
        created_by = "agent"
        # In this case, token_data.sub is the actual user, user_id from request is also the user
        user_id = booking_request.user_id or token_data.sub
        logger.info(f"Agent booking detected - agent_id: {agent_id}, user_id: {user_id}")
    else:
        # Direct user booking (no agent involved)
        agent_id = None
        created_by = "user"
        user_id = token_data.sub  # The user making their own booking
        logger.info(f"User booking detected - user_id: {user_id}")
    
    logger.info(f"Final booking values - created_by: {created_by}, user_id: {user_id}, agent_id: {agent_id}")
    
    new_booking = {
        "id": last_booking_id,
        "confirmation_number": generate_confirmation_number(),
        "user_id": user_id,
        "hotel_id": booking_request.hotel_id,
        "hotel_name": hotel_data["name"],
        "room_id": booking_request.room_id,
        "room_type": room_data["room_type"],
        "check_in": booking_request.check_in,
        "check_out": booking_request.check_out,
        "guests": booking_request.guests,
        "total_amount": total_amount,
        "status": "confirmed",
        "special_requests": booking_request.special_requests or [],
        "created_at": datetime.now(),
        "created_by": created_by,
        "agent_id": agent_id,
        "assigned_staff": []
    }
    
    bookings_data[last_booking_id] = new_booking
    
    # Fire webhook for automatic contact person assignment (async, don't wait)
    # Use priority based on guest count and created_by
    priority = "high" if booking_request.guests >= 3 or created_by == "agent" else "normal"
    
    # Fire webhook in background - don't block the booking response
    asyncio.create_task(invoke_staff_management_agent(
        booking_id=last_booking_id,
        user_id=user_id,
        hotel_id=booking_request.hotel_id,
        priority=priority
    ))
    
    logger.info(f"Booking {last_booking_id} created successfully, auto-assign webhook queued")
    
    return Booking(**new_booking)

@api_router.get("/bookings/{booking_id}")
async def get_booking(
    request: Request,
    booking_id: int,
    token_data: TokenData = Security(validate_token, scopes=["read_bookings"])
):
    """Get booking details"""
    log_request_details(request, token_data, {"booking_id": booking_id})
    
    if booking_id not in bookings_data:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    booking = bookings_data[booking_id]
    
    # Enrich booking with user and agent information
    enriched_booking = await enrich_booking_with_user_agent_info(booking)
    return enriched_booking

@api_router.post("/bookings/{booking_id}/cancel", response_model=Booking)
async def cancel_booking(
    request: Request,
    booking_id: int,
    reason: Optional[dict] = None,
    token_data: TokenData = Security(validate_token, scopes=["cancel_bookings"])
):
    """Cancel a booking"""
    log_request_details(request, token_data, {"booking_id": booking_id, "action": "cancel"})
    
    if booking_id not in bookings_data:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    booking = bookings_data[booking_id]
    
    if booking['status'] != 'confirmed':
        raise HTTPException(status_code=400, detail="Only confirmed bookings can be cancelled")
    
    # Update booking status
    booking['status'] = 'cancelled'
    
    return Booking(**booking)

# === User Booking Endpoints ===
@api_router.get("/users/{user_id}/bookings")
async def get_user_bookings(
    request: Request,
    user_id: str,
    status: Optional[BookingStatusEnum] = Query(None),
    limit: int = Query(10, le=50),
    token_data: TokenData = Security(validate_token, scopes=["read_bookings"])
):
    """Get user's bookings"""
    log_request_details(request, token_data, {"user_id": user_id})
    

    user_bookings = []
    for booking in bookings_data.values():
        if booking['user_id'] == user_id:
            if status is None or booking['status'] == status.value:
                # Enrich booking with user and agent information
                enriched_booking = await enrich_booking_with_user_agent_info(booking)
                user_bookings.append(enriched_booking)
    
    # Sort by creation date (newest first)
    user_bookings.sort(key=lambda x: x['created_at'], reverse=True)
    
    # Apply limit
    limited_bookings = user_bookings[:limit]
    
    return {"bookings": limited_bookings, "total": len(user_bookings)}

@api_router.get("/users/{user_id}/bookings/{booking_id}")
async def get_user_booking(
    request: Request,
    user_id: str,
    booking_id: int,
    token_data: TokenData = Security(validate_token, scopes=["read_bookings"])
):
    """Get specific user booking"""
    log_request_details(request, token_data, {"user_id": user_id, "booking_id": booking_id})
    
    if booking_id not in bookings_data:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    booking = bookings_data[booking_id]
    
    # Check if booking belongs to user and user has access
    if booking['user_id'] != user_id:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    # Enrich booking with user and agent information
    enriched_booking = await enrich_booking_with_user_agent_info(booking)
    return enriched_booking

# === Review Endpoints ===
@api_router.get("/reviews", response_model=ReviewsResponse)
async def get_reviews(
    request: Request,
    hotel_id: Optional[int] = Query(None),
    rating: Optional[float] = Query(None, ge=1, le=5),
    limit: int = Query(20, le=100),
    offset: int = Query(0, ge=0)
):
    """Get all reviews with privacy protection - Public endpoint"""
    logger.info(f"GET /api/reviews - filters: hotel_id={hotel_id}, rating={rating}")
    
    filtered_reviews = []
    for review_data in reviews_data.values():
        # Apply filters
        if hotel_id and review_data['hotel_id'] != hotel_id:
            continue
        if rating and review_data['rating'] < rating:
            continue
        
        public_review = convert_review_to_public(review_data)
        filtered_reviews.append(PublicReview(**public_review))
    
    # Sort by creation date (newest first)
    filtered_reviews.sort(key=lambda x: x.created_at, reverse=True)
    
    # Apply pagination
    total = len(filtered_reviews)
    paginated_reviews = filtered_reviews[offset:offset + limit]
    
    # Calculate summary
    if filtered_reviews:
        avg_rating = sum(r.rating for r in filtered_reviews) / len(filtered_reviews)
        rating_counts = {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0}
        for review in filtered_reviews:
            rating_counts[str(int(review.rating))] += 1
        
        summary = {
            "average_rating": round(avg_rating, 2),
            "total_by_rating": rating_counts
        }
    else:
        summary = {"average_rating": 0, "total_by_rating": {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0}}
    
    return ReviewsResponse(
        reviews=paginated_reviews,
        total=total,
        summary=summary
    )

@api_router.post("/reviews", response_model=Review)
async def create_review(
    request: Request,
    review_request: ReviewCreate,
    token_data: TokenData = Security(validate_token, scopes=["create_bookings"])
):
    """Create a review"""
    log_request_details(request, token_data, {"review_type": review_request.review_type})
    
    global last_review_id
    
    # Validate booking exists
    if review_request.booking_id not in bookings_data:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    booking = bookings_data[review_request.booking_id]
    
    # Validate hotel_id matches booking
    if review_request.hotel_id != booking['hotel_id']:
        raise HTTPException(status_code=400, detail="Hotel ID does not match booking")
    
    # Validate staff_id if reviewing staff
    if review_request.review_type == ReviewTypeEnum.staff:
        if not review_request.staff_id:
            raise HTTPException(status_code=400, detail="staff_id is required for staff reviews")
        if review_request.staff_id not in staff_data:
            raise HTTPException(status_code=404, detail="Staff member not found")
    
    # Create review
    last_review_id += 1
    
    new_review = {
        "id": last_review_id,
        "booking_id": review_request.booking_id,
        "user_id": token_data.sub,
        "hotel_id": review_request.hotel_id,
        "staff_id": review_request.staff_id,
        "review_type": review_request.review_type.value,
        "rating": review_request.rating,
        "title": review_request.title,
        "comment": review_request.comment,
        "aspects": review_request.aspects.dict() if review_request.aspects else {},
        "would_recommend": review_request.would_recommend,
        "created_at": datetime.now()
    }
    
    reviews_data[last_review_id] = new_review
    
    return Review(**new_review)

@api_router.get("/reviews/{review_id}", response_model=PublicReview)
async def get_review(
    request: Request,
    review_id: int
):
    """Get review details (privacy-safe) - Public endpoint"""
    logger.info(f"GET /api/reviews/{review_id}")
    
    if review_id not in reviews_data:
        raise HTTPException(status_code=404, detail="Review not found")
    
    review_data = reviews_data[review_id]
    public_review = convert_review_to_public(review_data)
    
    return PublicReview(**public_review)

# === Admin Endpoints ===

@api_router.get("/admin/bookings/{booking_id}")
async def get_booking_admin(
    request: Request,
    booking_id: int,
    token_data: TokenData = Security(validate_token, scopes=["admin_read_bookings"])
):
    """Get booking details"""
    log_request_details(request, token_data, {"booking_id": booking_id})
    
    if booking_id not in bookings_data:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    booking = bookings_data[booking_id]
    
    return booking

@api_router.patch("/admin/bookings/{booking_id}", response_model=Booking)
async def update_booking_admin(
    booking_id: int,
    booking_update: BookingUpdate,
    request: Request,
    token_data: TokenData = Security(validate_token, scopes=["admin_update_bookings"])
):
    """Update booking (assign/remove contact person) - Admin endpoint"""
    global last_assignment_id
    
    # Enhanced logging
    log_request_details(request, token_data, {
        "booking_id": booking_id,
        "update_data": booking_update.dict(exclude_none=True)
    })
    
    # Check if booking exists
    if booking_id not in bookings_data:
        logger.warning(f"Booking {booking_id} not found for admin update")
        raise HTTPException(status_code=404, detail="Booking not found")
    
    booking = bookings_data[booking_id]
    
    # Validate staff member if contact_person_id is provided
    if booking_update.contact_person_id is not None:
        if booking_update.contact_person_id not in staff_data:
            logger.warning(f"Staff member {booking_update.contact_person_id} not found")
            raise HTTPException(status_code=400, detail="Staff member not found")
        
        staff_member = staff_data[booking_update.contact_person_id]
        
        # Check if staff is available
        if not staff_member["availability"]["is_available"]:
            logger.warning(f"Staff member {booking_update.contact_person_id} is not available")
            raise HTTPException(status_code=400, detail="Staff member is not available")
        
        # Remove existing primary contact if any
        booking["assigned_staff"] = [
            assignment for assignment in booking["assigned_staff"] 
            if assignment["assignment_type"] != "primary_contact"
        ]
        
        # Add new assignment
        last_assignment_id += 1
        new_assignment = {
            "id": last_assignment_id,
            "booking_id": booking_id,
            "staff_id": booking_update.contact_person_id,
            "staff_name": f"{staff_member['first_name']} {staff_member['last_name']}",
            "role": staff_member["role"],
            "assignment_type": "primary_contact",
            "assigned_at": datetime.now(),
            "assigned_by": "admin_agent",
            "assignment_reason": booking_update.assignment_reason or "Admin assignment"
        }
        
        booking["assigned_staff"].append(new_assignment)
        
        # Update staff availability
        staff_member["availability"]["current_assignments"] += 1
        
        logger.info(f"Assigned staff {booking_update.contact_person_id} to booking {booking_id}")
        
    elif booking_update.contact_person_id is None:
        # Remove primary contact
        removed_assignments = [
            assignment for assignment in booking["assigned_staff"] 
            if assignment["assignment_type"] == "primary_contact"
        ]
        
        booking["assigned_staff"] = [
            assignment for assignment in booking["assigned_staff"] 
            if assignment["assignment_type"] != "primary_contact"
        ]
        
        # Update staff availability for removed assignments
        for assignment in removed_assignments:
            if assignment["staff_id"] in staff_data:
                staff_data[assignment["staff_id"]]["availability"]["current_assignments"] -= 1
        
        logger.info(f"Removed primary contact from booking {booking_id}")
    
    # Return enriched booking
    enriched_booking = await enrich_booking_with_user_agent_info(booking)
    return Booking(**enriched_booking)

@api_router.get("/admin/staff/available", response_model=AvailableStaffResponse)
async def get_available_contact_persons(
    request: Request,
    hotel_id: Optional[int] = Query(None, description="Filter by hotel ID"),
    token_data: TokenData = Security(validate_token, scopes=["admin_read_staff"])
):
    """Get available contact persons - Admin endpoint"""
    
    # Enhanced logging
    log_request_details(request, token_data, {
        "hotel_id": hotel_id
    })
    
    # Filter available staff
    available_staff = []
    
    for staff_id, staff_member in staff_data.items():
        # Apply hotel filter if provided
        if hotel_id is not None and staff_member["hotel_id"] != hotel_id:
            continue
        
        # Only include available staff with roles suitable for contact person duties
        suitable_roles = ["concierge", "butler", "front_desk"]
        if (staff_member["availability"]["is_available"] and 
            staff_member["role"] in suitable_roles and
            staff_member["availability"]["current_assignments"] < 5):  # Max 5 assignments
            
            available_staff.append(AvailableStaff(
                id=staff_member["id"],
                first_name=staff_member["first_name"],
                last_name=staff_member["last_name"],
                role=staff_member["role"],
                hotel_id=staff_member["hotel_id"],
                current_assignments=staff_member["availability"]["current_assignments"],
                is_available=staff_member["availability"]["is_available"]
            ))
    
    logger.info(f"Found {len(available_staff)} available staff members" + 
                (f" for hotel {hotel_id}" if hotel_id else ""))
    
    return AvailableStaffResponse(
        staff=available_staff,
        total=len(available_staff)
    )

# Include the router in the main app
app.include_router(api_router)

@app.get("/")
async def root():
    """Health check endpoint"""
    return {"message": "Hotel API is running", "version": "2.1.0"}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.get("/cache/stats")
async def get_cache_stats():
    """Get cache statistics for monitoring"""
    return {
        "scim_cache": scim_service.get_cache_stats(),
        "jwt_tokens": jwt_client.get_token_stats(),
        "timestamp": datetime.now().isoformat()
    }
