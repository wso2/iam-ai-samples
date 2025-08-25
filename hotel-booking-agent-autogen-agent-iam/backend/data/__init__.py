"""
Data package initialization
"""

from .hotels import hotels_data
from .rooms import rooms_data
from .bookings import bookings_data, last_booking_id, last_assignment_id
from .reviews import reviews_data, last_review_id
from .users import users_data
from .staff import staff_data

__all__ = [
    'hotels_data',
    'rooms_data', 
    'bookings_data',
    'last_booking_id',
    'last_assignment_id',
    'reviews_data',
    'last_review_id',
    'users_data',
    'staff_data'
]
