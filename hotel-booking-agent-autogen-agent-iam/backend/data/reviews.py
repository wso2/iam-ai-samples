"""
Review data store with comprehensive review information
"""
from datetime import datetime

reviews_data = {
    1: {
        "id": 1,
        "booking_id": 3, 
        "user_id": "6dcec033-8117-49bb-8363-3c519bcdbb73",
        "hotel_id": 3,
        "staff_id": None,
        "review_type": "hotel",
        "rating": 4.5,
        "title": "Beautiful mountain retreat",
        "comment": "The location was absolutely stunning with breathtaking mountain views. The heritage architecture combined with modern amenities made for a perfect stay. The cultural tours were well organized and the staff was very knowledgeable about local history.",
        "aspects": {
            "cleanliness": 4.0,
            "service": 4.5,
            "location": 5.0,
            "value": 4.0,
            "professionalism": None,
            "responsiveness": None
        },
        "would_recommend": True,
        "created_at": datetime(2024, 2, 25, 10, 30, 0)
    },
    2: {
        "id": 2,
        "booking_id": 1,
        "user_id": "6dcec033-8117-49bb-8363-3c519bcdbb73", 
        "hotel_id": 1,
        "staff_id": None,
        "review_type": "hotel",
        "rating": 4.2,
        "title": "Relaxing beachside experience",
        "comment": "The infinity pool and spa facilities were exceptional. The restaurant served delicious local cuisine. Room was clean and comfortable with all necessary amenities. Only minor issue was the WiFi connectivity in some areas.",
        "aspects": {
            "cleanliness": 4.5,
            "service": 4.0,
            "location": 5.0,
            "value": 3.5,
            "professionalism": None,
            "responsiveness": None
        },
        "would_recommend": True,
        "created_at": datetime(2024, 3, 20, 14, 15, 0)
    },
    3: {
        "id": 3,
        "booking_id": 2,
        "user_id": "8b2f1c45-9876-5432-abcd-ef1234567890",
        "hotel_id": 2,
        "staff_id": 1,
        "review_type": "staff",
        "rating": 5.0,
        "title": "Outstanding concierge service",
        "comment": "Priya went above and beyond to ensure our stay was perfect. She arranged all our city tours, restaurant reservations, and even helped with some last-minute shopping recommendations. Her knowledge of Colombo was impressive and her service was truly professional.",
        "aspects": {
            "cleanliness": None,
            "service": None,
            "location": None,
            "value": None,
            "professionalism": 5.0,
            "responsiveness": 5.0
        },
        "would_recommend": True,
        "created_at": datetime(2024, 4, 17, 11, 45, 0)
    },
    4: {
        "id": 4,
        "booking_id": 4,
        "user_id": "c3d4e5f6-7890-1234-5678-9abcdef01234",
        "hotel_id": 4,
        "staff_id": None,
        "review_type": "hotel",
        "rating": 4.8,
        "title": "Perfect honeymoon destination",
        "comment": "Everything was absolutely perfect for our honeymoon. The ocean views from our room were spectacular, the private beach access was amazing, and the spa treatments were world-class. The colonial architecture adds such character to the property. Highly recommend for couples!",
        "aspects": {
            "cleanliness": 5.0,
            "service": 4.5,
            "location": 5.0,
            "value": 4.5,
            "professionalism": None,
            "responsiveness": None
        },
        "would_recommend": True,
        "created_at": datetime(2024, 5, 10, 16, 20, 0)
    },
    5: {
        "id": 5,
        "booking_id": 4,
        "user_id": "c3d4e5f6-7890-1234-5678-9abcdef01234",
        "hotel_id": 4,
        "staff_id": 3,
        "review_type": "staff", 
        "rating": 4.7,
        "title": "Exceptional butler service",
        "comment": "Ruwan provided exceptional butler service throughout our stay. He anticipated our needs, arranged romantic dinners, and ensured our room was always perfectly maintained. His attention to detail and genuine care made our honeymoon even more special.",
        "aspects": {
            "cleanliness": None,
            "service": None,
            "location": None,
            "value": None,
            "professionalism": 4.5,
            "responsiveness": 5.0
        },
        "would_recommend": True,
        "created_at": datetime(2024, 5, 10, 16, 30, 0)
    },
    6: {
        "id": 6,
        "booking_id": None,  # Review without booking (general feedback)
        "user_id": "a1b2c3d4-5678-9012-3456-789abcdef012",
        "hotel_id": 2,
        "staff_id": None,
        "review_type": "hotel",
        "rating": 3.8,
        "title": "Good location, average service",
        "comment": "The hotel is well-located in the heart of Colombo with easy access to shopping and business districts. Rooms are modern and clean. However, the service could be improved - staff seemed overwhelmed during peak hours. The rooftop bar is definitely a highlight.",
        "aspects": {
            "cleanliness": 4.0,
            "service": 3.0,
            "location": 5.0,
            "value": 3.5,
            "professionalism": None,
            "responsiveness": None
        },
        "would_recommend": True,
        "created_at": datetime(2024, 4, 5, 13, 10, 0)
    }
}

# Counter for generating new review IDs
last_review_id = 6