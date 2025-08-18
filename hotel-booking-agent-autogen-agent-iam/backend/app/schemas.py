from pydantic import BaseModel, Field
from datetime import date, datetime
from typing import Dict, List, Optional, Union
from enum import Enum

# === Enums ===
class BrandEnum(str, Enum):
    luxury = "luxury"
    premium = "premium"
    select = "select"
    garden_inn = "garden_inn"
    homewood = "homewood"

class BookingStatusEnum(str, Enum):
    confirmed = "confirmed"
    cancelled = "cancelled"
    completed = "completed"

class CreatedByEnum(str, Enum):
    user = "user"
    agent = "agent"

class ReviewTypeEnum(str, Enum):
    hotel = "hotel"
    staff = "staff"

class StaffRoleEnum(str, Enum):
    concierge = "concierge"
    butler = "butler"
    front_desk = "front_desk"
    housekeeping = "housekeeping"

class LoyaltyTierEnum(str, Enum):
    member = "member"
    silver = "silver"
    gold = "gold"
    diamond = "diamond"

# === Core Schemas ===
class Address(BaseModel):
    street: str
    city: str
    state: str
    country: str
    postal_code: str

class PriceRange(BaseModel):
    min: float
    max: float

class Hotel(BaseModel):
    id: int
    name: str
    brand: BrandEnum
    description: str
    address: Address
    rating: float
    amenities: List[str]
    images: Optional[List[str]] = None
    price_range: PriceRange
    rooms: Optional[List['Room']] = None

class Room(BaseModel):
    id: int
    hotel_id: int
    room_type: str
    bed_type: str
    max_occupancy: int
    size_sqft: int
    amenities: List[str]
    images: Optional[List[str]] = None
    base_price: float

class StaffAssignment(BaseModel):
    id: int
    booking_id: int
    staff_id: int
    staff_name: str
    role: str
    assignment_type: str
    assigned_at: datetime
    assigned_by: str
    assignment_reason: str

class Booking(BaseModel):
    id: int
    confirmation_number: str
    user_id: str
    hotel_id: int
    hotel_name: str
    room_id: int
    room_type: str
    check_in: date
    check_out: date
    guests: int
    total_amount: float
    status: BookingStatusEnum
    special_requests: List[str] = []
    created_at: datetime
    created_by: CreatedByEnum
    agent_id: Optional[str] = None
    assigned_staff: List[StaffAssignment] = []

class ReviewAspects(BaseModel):
    cleanliness: Optional[float] = None
    service: Optional[float] = None
    location: Optional[float] = None
    value: Optional[float] = None
    professionalism: Optional[float] = None
    responsiveness: Optional[float] = None

class Review(BaseModel):
    id: int
    booking_id: Optional[int] = None
    user_id: str
    hotel_id: int
    staff_id: Optional[int] = None
    review_type: ReviewTypeEnum
    rating: float = Field(ge=1, le=5)
    title: str
    comment: str
    aspects: ReviewAspects
    would_recommend: bool
    created_at: datetime

class PublicReview(BaseModel):
    id: int
    hotel_id: int
    review_type: ReviewTypeEnum
    rating: float = Field(ge=1, le=5)
    title: str
    comment: str
    aspects: ReviewAspects
    would_recommend: bool
    created_at: datetime
    reviewer_name: str = "Anonymous Guest"

class UserPreferences(BaseModel):
    room_type: str
    amenities: List[str]
    budget_range: PriceRange

class User(BaseModel):
    id: str
    email: str
    first_name: str
    last_name: str
    phone: str
    loyalty_tier: LoyaltyTierEnum
    preferences: UserPreferences

class StaffAvailability(BaseModel):
    is_available: bool
    current_assignments: int

class Staff(BaseModel):
    id: int
    first_name: str
    last_name: str
    role: StaffRoleEnum
    hotel_id: int
    specialties: List[str]
    languages: List[str]
    average_rating: float
    total_reviews: int
    availability: StaffAvailability

# === Request/Response Models ===
class HotelSearchRequest(BaseModel):
    location: str
    check_in: date
    check_out: date
    guests: int = 1
    rooms: int = 1
    brand: Optional[str] = None
    amenities: Optional[List[str]] = None
    price_range: Optional[PriceRange] = None

class BookingCreate(BaseModel):
    user_id: Optional[str] = None
    hotel_id: int
    room_id: int
    check_in: date
    check_out: date
    guests: int
    special_requests: Optional[List[str]] = []

class ReviewCreate(BaseModel):
    booking_id: int
    review_type: ReviewTypeEnum = ReviewTypeEnum.hotel
    hotel_id: int
    staff_id: Optional[int] = None
    rating: float = Field(ge=1, le=5)
    title: str
    comment: str
    aspects: Optional[ReviewAspects] = None
    would_recommend: bool

# === Response Models ===
class HotelsResponse(BaseModel):
    hotels: List[Hotel]
    total: int

class ReviewsResponse(BaseModel):
    reviews: List[PublicReview]
    total: int
    summary: Optional[Dict] = None

class BookingsResponse(BaseModel):
    bookings: List[Booking]
    total: int

class StaffReviewsResponse(BaseModel):
    reviews: List[PublicReview]
    staff_summary: Dict
    total: int

class Error(BaseModel):
    error: str
    message: str
    code: int

# === Admin Schemas ===
class BookingUpdate(BaseModel):
    contact_person_id: Optional[int] = None
    assignment_reason: Optional[str] = None

class AvailableStaff(BaseModel):
    id: int
    first_name: str
    last_name: str
    role: StaffRoleEnum
    hotel_id: int
    current_assignments: int
    is_available: bool

class AvailableStaffResponse(BaseModel):
    staff: List[AvailableStaff]
    total: int
