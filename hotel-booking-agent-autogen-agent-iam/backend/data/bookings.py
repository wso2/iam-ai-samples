"""
Booking data store with sample booking records
"""
from datetime import date, datetime
import uuid

bookings_data = {}

# Counter for generating new booking IDs
last_booking_id = 0

# Counter for generating new staff assignment IDs
last_assignment_id = 0

# bookings_data = {
#     1: {
#         "id": 1,
#         "confirmation_number": "GRD-2024-001",
#         "user_id": "6dcec033-8117-49bb-8363-3c519bcdbb73",
#         "hotel_id": 1,
#         "hotel_name": "Gardeo Saman Villa",
#         "room_id": 1,
#         "room_type": "standard", 
#         "check_in": date(2024, 3, 15),
#         "check_out": date(2024, 3, 18),
#         "guests": 2,
#         "total_amount": 209.97,
#         "status": "confirmed",
#         "special_requests": ["Late check-in", "Extra pillows"],
#         "created_at": datetime(2024, 2, 15, 14, 30, 0),
#         "created_by": "user",
#         "agent_id": None,
#         "assigned_staff": []
#     },
#     2: {
#         "id": 2,
#         "confirmation_number": "GRD-2024-002",
#         "user_id": "8b2f1c45-9876-5432-abcd-ef1234567890",
#         "hotel_id": 2,
#         "hotel_name": "Gardeo Colombo Seven",
#         "room_id": 6,
#         "room_type": "studio",
#         "check_in": date(2024, 4, 10),
#         "check_out": date(2024, 4, 15),
#         "guests": 4,
#         "total_amount": 1499.95,
#         "status": "confirmed",
#         "special_requests": ["Airport transfer", "Breakfast included"],
#         "created_at": datetime(2024, 3, 10, 10, 15, 0),
#         "created_by": "agent",
#         "agent_id": "agent-456",
#         "assigned_staff": [
#             {
#                 "id": 1,
#                 "booking_id": 2,
#                 "staff_id": 1,
#                 "staff_name": "Priya Silva",
#                 "role": "concierge",
#                 "assignment_type": "primary_contact",
#                 "assigned_at": datetime(2024, 3, 10, 11, 0, 0),
#                 "assigned_by": "admin_agent",
#                 "assignment_reason": "VIP guest services"
#             }
#         ]
#     },
#     3: {
#         "id": 3,
#         "confirmation_number": "GRD-2024-003",
#         "user_id": "6dcec033-8117-49bb-8363-3c519bcdbb73",
#         "hotel_id": 3,
#         "hotel_name": "Gardeo Kandy Hills",
#         "room_id": 7,
#         "room_type": "deluxe",
#         "check_in": date(2024, 2, 20),
#         "check_out": date(2024, 2, 23),
#         "guests": 2,
#         "total_amount": 539.97,
#         "status": "completed",
#         "special_requests": ["Mountain view room", "Cultural tour booking"],
#         "created_at": datetime(2024, 1, 25, 16, 45, 0),
#         "created_by": "user",
#         "agent_id": None,
#         "assigned_staff": []
#     },
#     4: {
#         "id": 4,
#         "confirmation_number": "GRD-2024-004",
#         "user_id": "c3d4e5f6-7890-1234-5678-9abcdef01234",
#         "hotel_id": 4,
#         "hotel_name": "Gardeo Beach Resort Galle",
#         "room_id": 10,
#         "room_type": "super_deluxe",
#         "check_in": date(2024, 5, 1),
#         "check_out": date(2024, 5, 7),
#         "guests": 3,
#         "total_amount": 1797.00,
#         "status": "confirmed",
#         "special_requests": ["Beach access", "Spa treatment booking", "Honeymoon setup"],
#         "created_at": datetime(2024, 4, 1, 9, 20, 0),
#         "created_by": "agent",
#         "agent_id": "agent-789",
#         "assigned_staff": [
#             {
#                 "id": 2,
#                 "booking_id": 4,
#                 "staff_id": 3,
#                 "staff_name": "Ruwan Perera",
#                 "role": "butler",
#                 "assignment_type": "butler_service",
#                 "assigned_at": datetime(2024, 4, 1, 10, 0, 0),
#                 "assigned_by": "admin_agent", 
#                 "assignment_reason": "Honeymoon special service"
#             }
#         ]
#     }
# }
