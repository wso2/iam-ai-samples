"""
Staff data store with staff member information
"""

staff_data = {
    1: {
        "id": 1,
        "first_name": "Priya",
        "last_name": "Silva",
        "role": "concierge",
        "hotel_id": 2,
        "specialties": ["City Tours", "Restaurant Reservations", "Transportation", "Local Attractions"],
        "languages": ["English", "Sinhala", "Tamil", "Hindi"],
        "average_rating": 4.8,
        "total_reviews": 15,
        "availability": {
            "is_available": True,
            "current_assignments": 2
        }
    },
    2: {
        "id": 2,
        "first_name": "Kumara",
        "last_name": "Fernando",
        "role": "front_desk",
        "hotel_id": 1,
        "specialties": ["Check-in/Check-out", "Guest Services", "Problem Resolution"],
        "languages": ["English", "Sinhala", "German"],
        "average_rating": 4.5,
        "total_reviews": 8,
        "availability": {
            "is_available": True,
            "current_assignments": 1
        }
    },
    3: {
        "id": 3,
        "first_name": "Ruwan",
        "last_name": "Perera",
        "role": "butler",
        "hotel_id": 4,
        "specialties": ["Personal Service", "Room Management", "Special Occasions", "VIP Services"],
        "languages": ["English", "Sinhala", "French"],
        "average_rating": 4.9,
        "total_reviews": 12,
        "availability": {
            "is_available": True,
            "current_assignments": 1
        }
    },
    4: {
        "id": 4,
        "first_name": "Nalini",
        "last_name": "Rajapakse",
        "role": "housekeeping",
        "hotel_id": 3,
        "specialties": ["Room Cleaning", "Maintenance", "Guest Requests"],
        "languages": ["English", "Sinhala"],
        "average_rating": 4.3,
        "total_reviews": 6,
        "availability": {
            "is_available": True,
            "current_assignments": 3
        }
    },
    5: {
        "id": 5,
        "first_name": "Chaminda",
        "last_name": "Wickramasinghe", 
        "role": "concierge",
        "hotel_id": 3,
        "specialties": ["Cultural Tours", "Heritage Sites", "Adventure Activities", "Local Culture"],
        "languages": ["English", "Sinhala", "Japanese"],
        "average_rating": 4.7,
        "total_reviews": 10,
        "availability": {
            "is_available": True,
            "current_assignments": 1
        }
    }
}