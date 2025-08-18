"""
Room data store with detailed room information
"""

rooms_data = {
    1: {  # Hotel 1 - Gardeo Saman Villa
        1: {
            "id": 1,
            "hotel_id": 1,
            "room_type": "standard",
            "bed_type": "King",
            "max_occupancy": 2,
            "size_sqft": 350,
            "amenities": ["Air Conditioning", "Free WiFi", "Safe", "Mini Fridge", "Coffee Maker"],
            "base_price": 69.99
        },
        2: {
            "id": 2,
            "hotel_id": 1,
            "room_type": "deluxe",
            "bed_type": "King",
            "max_occupancy": 2,
            "size_sqft": 450,
            "amenities": ["Air Conditioning", "Mini Bar", "Free WiFi", "Safe", "Garden View", "Balcony"],
            "base_price": 99.99
        },
        3: {
            "id": 3,
            "hotel_id": 1,
            "room_type": "super_deluxe",
            "bed_type": "King",
            "max_occupancy": 3,
            "size_sqft": 550,
            "amenities": ["Air Conditioning", "Mini Bar", "Free WiFi", "Safe", "Bathtub", "Sea View", "Premium Linens"],
            "base_price": 149.50
        }
    },
    2: {  # Hotel 2 - Gardeo Colombo Seven
        4: {
            "id": 4,
            "hotel_id": 2,
            "room_type": "standard",
            "bed_type": "Queen",
            "max_occupancy": 2,
            "size_sqft": 300,
            "amenities": ["Air Conditioning", "Free WiFi", "Work Desk", "City View"],
            "base_price": 89.99
        },
        5: {
            "id": 5,
            "hotel_id": 2,
            "room_type": "super_deluxe",
            "bed_type": "King",
            "max_occupancy": 3,
            "size_sqft": 500,
            "amenities": ["Air Conditioning", "Mini Bar", "Free WiFi", "Safe", "Bathtub", "City View", "Premium Amenities"],
            "base_price": 199.50
        },
        6: {
            "id": 6,
            "hotel_id": 2,
            "room_type": "studio",
            "bed_type": "King",
            "max_occupancy": 4,
            "size_sqft": 650,
            "amenities": ["Air Conditioning", "Kitchen", "Free WiFi", "Safe", "Washing Machine", "City View", "Living Area"],
            "base_price": 299.99
        }
    },
    3: {  # Hotel 3 - Gardeo Kandy Hills
        7: {
            "id": 7,
            "hotel_id": 3,
            "room_type": "deluxe",
            "bed_type": "King",
            "max_occupancy": 2,
            "size_sqft": 400,
            "amenities": ["Air Conditioning", "Mini Bar", "Free WiFi", "Safe", "Mountain View", "Traditional Decor"],
            "base_price": 179.99
        },
        8: {
            "id": 8,
            "hotel_id": 3,
            "room_type": "studio",
            "bed_type": "King",
            "max_occupancy": 4,
            "size_sqft": 600,
            "amenities": ["Air Conditioning", "Kitchen", "Free WiFi", "Safe", "Washing Machine", "Valley View", "Seating Area"],
            "base_price": 259.99
        }
    },
    4: {  # Hotel 4 - Gardeo Beach Resort Galle
        9: {
            "id": 9,
            "hotel_id": 4,
            "room_type": "deluxe",
            "bed_type": "King",
            "max_occupancy": 2,
            "size_sqft": 450,
            "amenities": ["Air Conditioning", "Mini Bar", "Free WiFi", "Safe", "Ocean View", "Beach Access"],
            "base_price": 199.99
        },
        10: {
            "id": 10,
            "hotel_id": 4,
            "room_type": "super_deluxe", 
            "bed_type": "King",
            "max_occupancy": 3,
            "size_sqft": 600,
            "amenities": ["Air Conditioning", "Mini Bar", "Free WiFi", "Safe", "Bathtub", "Ocean View", "Private Balcony", "Beach Access"],
            "base_price": 299.50
        }
    }
}
