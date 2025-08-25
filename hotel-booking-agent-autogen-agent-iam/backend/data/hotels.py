"""
Hotel data store with comprehensive hotel information
"""
from datetime import datetime

hotels_data = {
    1: {
        "id": 1,
        "name": "Gardeo Saman Villa",
        "brand": "luxury",
        "description": "Enjoy a luxurious stay at Gardeo Saman Villas in your suite, and indulge in a delicious breakfast and your choice of lunch or dinner from our daily set menus served at the restaurant. Access exquisite facilities, including the infinity pool, Sahana Spa, gymnasium and library, as you unwind in paradise.",
        "address": {
            "street": "Beach Road",
            "city": "Bentota",
            "state": "Southern Province",
            "country": "Sri Lanka",
            "postal_code": "80500"
        },
        "rating": 4.5,
        "amenities": ["Infinity Pool", "Sahana Spa", "Gymnasium", "Library", "Restaurant", "Room Service", "Free WiFi", "Parking"],
        "images": [
            "https://example.com/saman-villa/exterior.jpg",
            "https://example.com/saman-villa/pool.jpg",
            "https://example.com/saman-villa/spa.jpg"
        ],
        "price_range": {
            "min": 69.99,
            "max": 149.50
        }
    },
    2: {
        "id": 2,
        "name": "Gardeo Colombo Seven",
        "brand": "premium",
        "description": "Gardeo Colombo Seven is located in the heart of Colombo, the commercial capital of Sri Lanka and offers the discerning traveler contemporary accommodation and modern design aesthetic. Rising over the city landscape, the property boasts stunning views, a rooftop bar and pool, main restaurant, gym and spa services, as well as conference facilities.",
        "address": {
            "street": "Ward Place",
            "city": "Colombo",
            "state": "Western Province", 
            "country": "Sri Lanka",
            "postal_code": "00700"
        },
        "rating": 4.9,
        "amenities": ["Rooftop Pool", "Spa", "Gym", "Conference Facilities", "Restaurant", "Rooftop Bar", "Free WiFi", "Business Center"],
        "images": [
            "https://example.com/colombo-seven/exterior.jpg",
            "https://example.com/colombo-seven/rooftop.jpg",
            "https://example.com/colombo-seven/rooms.jpg"
        ],
        "price_range": {
            "min": 89.99,
            "max": 299.99
        }
    },
    3: {
        "id": 3,
        "name": "Gardeo Kandy Hills",
        "brand": "select",
        "description": "Set amidst the misty hills of Kandy, Gardeo Kandy Hills offers breathtaking views of the surrounding mountains. This heritage property combines traditional Sri Lankan architecture with modern luxury, featuring an infinity pool overlooking the valley, authentic local cuisine, and a wellness center.",
        "address": {
            "street": "Temple Road",
            "city": "Kandy",
            "state": "Central Province",
            "country": "Sri Lanka", 
            "postal_code": "20000"
        },
        "rating": 4.7,
        "amenities": ["Infinity Pool", "Wellness Center", "Heritage Restaurant", "Tea Lounge", "Mountain Biking", "Cultural Tours", "Free WiFi"],
        "images": [
            "https://example.com/kandy-hills/exterior.jpg",
            "https://example.com/kandy-hills/pool.jpg",
            "https://example.com/kandy-hills/mountains.jpg"
        ],
        "price_range": {
            "min": 179.99,
            "max": 259.99
        }
    },
    4: {
        "id": 4,
        "name": "Gardeo Beach Resort Galle",
        "brand": "luxury",
        "description": "Located along the historic Galle coast, Gardeo Beach Resort offers direct beach access and stunning views of the Indian Ocean. The resort features colonial-era architecture, beachfront dining, water sports facilities, and a luxury spa.",
        "address": {
            "street": "Fort Road",
            "city": "Galle",
            "state": "Southern Province",
            "country": "Sri Lanka",
            "postal_code": "80000"
        },
        "rating": 4.8,
        "amenities": ["Private Beach", "Water Sports", "Beachfront Dining", "Luxury Spa", "Infinity Pool", "Kids Club", "Free WiFi", "Tennis Court"],
        "images": [
            "https://example.com/galle-beach/exterior.jpg",
            "https://example.com/galle-beach/beach.jpg",
            "https://example.com/galle-beach/spa.jpg"
        ],
        "price_range": {
            "min": 199.99,
            "max": 299.50
        }
    }
}