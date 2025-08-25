import React, { useEffect, useState } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { Star, MapPin, Wifi, Car, Coffee, Dumbbell, ArrowLeft, Bed } from 'lucide-react';
import { EnhancedHeader } from '../components/layout/EnhancedHeader';
import LoadingSpinner from '../components/common/LoadingSpinner';
import { hotelAPI } from '../services/api';
import { Hotel, Room, Review } from '../types';
import { useAuthContext } from '@asgardeo/auth-react';
import { useSearch } from '../contexts/SearchContext';
import { getSriLankaDate, formatDateForInput } from '../utils/dateUtils';

interface HotelDetails extends Hotel {
  rooms: Room[];
}

export function EnhancedHotelDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const hotelId = parseInt(id!);
  const { state } = useAuthContext();
  const { searchParams, updateSearchParams } = useSearch(); // Use SearchContext

  const [hotel, setHotel] = useState<HotelDetails | null>(null);
  const [reviews, setReviews] = useState<Review[]>([]);
  const [loading, setLoading] = useState(true);
  const [bookingLoading, setBookingLoading] = useState(false);

  // Static images mapping - same as hotel cards for consistency
  const getHotelImages = (hotelName: string, hotelId: number) => {
    const hotelImageMapping: { [key: string]: string[] } = {
      'Gardeo Saman Villa': [
        'https://images.unsplash.com/photo-1566073771259-6a8506099945?ixlib=rb-4.0.3&auto=format&fit=crop&w=600&h=400',
        'https://images.unsplash.com/photo-1571896349842-33c89424de2d?ixlib=rb-4.0.3&auto=format&fit=crop&w=400&h=300',
        'https://images.unsplash.com/photo-1582719478250-c89cae4dc85b?ixlib=rb-4.0.3&auto=format&fit=crop&w=400&h=300'
      ],
      'Gardeo Colombo Seven': [
        'https://images.unsplash.com/photo-1578683010236-d716f9a3f461?ixlib=rb-4.0.3&auto=format&fit=crop&w=600&h=400',
        'https://images.unsplash.com/photo-1571896349842-33c89424de2d?ixlib=rb-4.0.3&auto=format&fit=crop&w=400&h=300',
        'https://images.unsplash.com/photo-1582719478250-c89cae4dc85b?ixlib=rb-4.0.3&auto=format&fit=crop&w=400&h=300'
      ],
      'Gardeo Kandy Hills': [
        'https://images.unsplash.com/photo-1571003123894-1f0594d2b5d9?ixlib=rb-4.0.3&auto=format&fit=crop&w=600&h=400',
        'https://images.unsplash.com/photo-1520250497591-112f2f40a3f4?ixlib=rb-4.0.3&auto=format&fit=crop&w=400&h=300',
        'https://images.unsplash.com/photo-1564501049412-61c2a3083791?ixlib=rb-4.0.3&auto=format&fit=crop&w=400&h=300'
      ],
      'Gardeo Beach Resort Galle': [
        'https://images.unsplash.com/photo-1582719508461-905c673771fd?ixlib=rb-4.0.3&auto=format&fit=crop&w=600&h=400',
        'https://images.unsplash.com/photo-1559827260-dc66d52bef19?ixlib=rb-4.0.3&auto=format&fit=crop&w=400&h=300',
        'https://images.unsplash.com/photo-1571896349842-33c89424de2d?ixlib=rb-4.0.3&auto=format&fit=crop&w=400&h=300'
      ]
    };

    // Fallback images for other hotels
    const fallbackImages = [
      [
        'https://images.unsplash.com/photo-1551882547-ff40c63fe5fa?ixlib=rb-4.0.3&auto=format&fit=crop&w=600&h=400',
        'https://images.unsplash.com/photo-1578683010236-d716f9a3f461?ixlib=rb-4.0.3&auto=format&fit=crop&w=400&h=300',
        'https://images.unsplash.com/photo-1571003123894-1f0594d2b5d9?ixlib=rb-4.0.3&auto=format&fit=crop&w=400&h=300'
      ],
      [
        'https://images.unsplash.com/photo-1596394516093-501ba68a0ba6?ixlib=rb-4.0.3&auto=format&fit=crop&w=600&h=400',
        'https://images.unsplash.com/photo-1564501049412-61c2a3083791?ixlib=rb-4.0.3&auto=format&fit=crop&w=400&h=300',
        'https://images.unsplash.com/photo-1520250497591-112f2f40a3f4?ixlib=rb-4.0.3&auto=format&fit=crop&w=400&h=300'
      ]
    ];

    // Return mapped images if exists, otherwise use fallback
    if (hotelImageMapping[hotelName]) {
      return hotelImageMapping[hotelName];
    }

    // Use hotel ID to get consistent fallback images
    const imageIndex = hotelId % fallbackImages.length;
    return fallbackImages[imageIndex];
  };

  // Read URL parameters and update SearchContext
  useEffect(() => {
    const urlParams = new URLSearchParams(location.search);
    const checkIn = urlParams.get('checkIn');
    const checkOut = urlParams.get('checkOut');
    const guests = urlParams.get('guests');

    if (checkIn || checkOut || guests) {
      const updates: any = {};
      if (checkIn) updates.check_in = checkIn;
      if (checkOut) updates.check_out = checkOut;
      if (guests) updates.guests = parseInt(guests);

      updateSearchParams(updates);
    }
  }, [location.search, updateSearchParams]);

  useEffect(() => {
    const fetchHotelData = async () => {
      try {
        const [hotelResponse, reviewsResponse] = await Promise.all([
          hotelAPI.getHotel(hotelId),
          hotelAPI.getHotelReviews(hotelId, { limit: 5 }),
        ]);

        const hotelData = hotelResponse.data;
        // Ensure images are set using our static image mapping
        const staticImages = getHotelImages(hotelData.name, hotelData.id);
        
        setHotel({
          ...hotelData,
          images: staticImages, // Use static images instead of API images
          rooms: hotelData.rooms || []
        });
        setReviews(reviewsResponse.data.reviews || []);
      } catch (error) {
        console.error('Failed to fetch hotel data:', error);
        // Fallback data similar to Gardeo Hotel's fallback
        const fallbackImages = getHotelImages('Gardeo Resort & Spa', hotelId);
        setHotel({
          id: hotelId,
          name: 'Gardeo Resort & Spa',
          brand: 'luxury',
          description: 'Experience luxury and tranquility at Gardeo Resort & Spa, nestled in the heart of Kandy\'s cultural landscape. Our resort offers world-class amenities, stunning views of the surrounding hills, and exceptional service that will make your stay unforgettable.',
          address: {
            street: 'Temple Road',
            city: 'Kandy',
            state: 'Central Province',
            country: 'Sri Lanka',
            postal_code: '20000'
          },
          rating: 4.7,
          amenities: [
            'Free WiFi',
            'Swimming Pool',
            'Spa & Wellness',
            'Restaurant',
            'Gym',
            'Free Parking',
            'Room Service',
            '24/7 Reception',
          ],
          images: fallbackImages, // Use static images
          price_range: {
            min: 15500,
            max: 35600
          },
          rooms: [
            {
              id: 1,
              hotel_id: hotelId,
              room_type: 'Deluxe Garden View',
              bed_type: 'King Bed',
              max_occupancy: 2,
              size_sqft: 450,
              amenities: ['King Bed', 'Garden View', 'Air Conditioning', 'Mini Bar', 'WiFi'],
              images: ['https://images.unsplash.com/photo-1611892440504-42a792e24d32?ixlib=rb-4.0.3&auto=format&fit=crop&w=300&h=200'],
              base_price: 15500,
            },
            {
              id: 2,
              hotel_id: hotelId,
              room_type: 'Premium Pool View',
              bed_type: 'Queen Bed + Sofa Bed',
              max_occupancy: 3,
              size_sqft: 550,
              amenities: ['Queen Bed + Sofa Bed', 'Pool View', 'Balcony', 'Air Conditioning', 'Mini Bar', 'WiFi'],
              images: ['https://images.unsplash.com/photo-1611892440504-42a792e24d32?ixlib=rb-4.0.3&auto=format&fit=crop&w=300&h=200'],
              base_price: 22800,
            },
            {
              id: 3,
              hotel_id: hotelId,
              room_type: 'Executive Suite',
              bed_type: 'King Bed',
              max_occupancy: 4,
              size_sqft: 750,
              amenities: [
                'King Bed',
                'Separate Living Area',
                'City View',
                'Kitchenette',
                'WiFi',
                'Complimentary Breakfast',
              ],
              images: ['https://images.unsplash.com/photo-1611892440504-42a792e24d32?ixlib=rb-4.0.3&auto=format&fit=crop&w=300&h=200'],
              base_price: 35600,
            },
          ],
        });
        setReviews([
          {
            id: 1,
            hotel_id: hotelId,
            review_type: 'hotel',
            rating: 4.5,
            title: 'Exceptional stay!',
            comment: 'Beautiful resort with amazing staff. The spa was incredible and the food was delicious. Highly recommend!',
            aspects: {
              cleanliness: 5.0,
              service: 4.5,
              location: 5.0,
              value: 4.0
            },
            would_recommend: true,
            created_at: '2024-01-15T10:30:00Z',
            reviewer_name: 'Guest123'
          },
          {
            id: 2,
            hotel_id: hotelId,
            review_type: 'hotel',
            rating: 4.2,
            title: 'Great location and service',
            comment: 'Perfect location in Kandy with easy access to attractions. Staff was very helpful and rooms were clean.',
            aspects: {
              cleanliness: 4.5,
              service: 4.0,
              location: 5.0,
              value: 3.5
            },
            would_recommend: true,
            created_at: '2024-01-10T14:20:00Z',
            reviewer_name: 'Guest456'
          },
        ]);
      } finally {
        setLoading(false);
      }
    };

    if (hotelId) {
      fetchHotelData();
    }
  }, [hotelId]);

  const handleBookRoom = async (room: Room) => {
    if (!state.isAuthenticated) {
      alert('Please sign in to make a booking');
      return;
    }

    setBookingLoading(true);

    try {
      // Use SearchContext first, then fallback to Sri Lanka current date
      const today = getSriLankaDate();
      const tomorrow = new Date(today);
      tomorrow.setDate(tomorrow.getDate() + 1);

      // Debug: Log current search parameters
      console.log('Current search parameters from context:', searchParams);

      const bookingData = {
        hotel_id: hotelId,
        room_id: room.id,
        check_in: searchParams?.check_in || formatDateForInput(today),
        check_out: searchParams?.check_out || formatDateForInput(tomorrow),
        guests: searchParams?.guests || 2,
      };

      console.log('Booking data being sent:', bookingData);

      const response = await hotelAPI.createBooking(bookingData);
      const booking = response.data;

      // Store booking info and redirect to confirmation
      sessionStorage.setItem('bookingConfirmation', JSON.stringify(booking));
      navigate('/booking-confirmation');
    } catch (error) {
      console.error('Booking failed:', error);
      alert('Booking failed. Please try again or contact support.');
    } finally {
      setBookingLoading(false);
    }
  };

  const getAmenityIcon = (amenity: string) => {
    const lower = amenity.toLowerCase();
    if (lower.includes('wifi')) return <Wifi className="w-4 h-4" />;
    if (lower.includes('parking')) return <Car className="w-4 h-4" />;
    if (lower.includes('restaurant') || lower.includes('breakfast')) return <Coffee className="w-4 h-4" />;
    if (lower.includes('gym') || lower.includes('fitness')) return <Dumbbell className="w-4 h-4" />;
    if (lower.includes('bed')) return <Bed className="w-4 h-4" />;
    return null;
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-white">
        <EnhancedHeader />
        <div className="container mx-auto px-4 py-8">
          <div className="flex justify-center">
            <LoadingSpinner size="lg" />
          </div>
          <div className="text-center mt-4">Loading hotel details...</div>
        </div>
      </div>
    );
  }

  if (!hotel) {
    return (
      <div className="min-h-screen bg-white">
        <EnhancedHeader />
        <div className="container mx-auto px-4 py-8">
          <div className="text-center">
            <h1 className="text-2xl font-bold mb-4">Hotel not found</h1>
            <button
              onClick={() => navigate('/')}
              className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-2 rounded-lg font-medium transition-colors"
            >
              Back to Home
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-white">
      <EnhancedHeader />

      <div className="container mx-auto px-4 py-8">
        {/* Back Button */}
        <button
          onClick={() => navigate(-1)}
          className="flex items-center gap-2 mb-6 text-gray-600 hover:text-gray-900 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back
        </button>

        {/* Hotel Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold mb-2">{hotel.name}</h1>
          <div className="flex items-center text-gray-600 mb-4">
            <MapPin className="w-5 h-5 mr-2" />
            <span>{hotel.address.city}, {hotel.address.country}</span>
          </div>

          <div className="flex items-center gap-4 mb-6">
            <div className="flex items-center gap-2">
              <div className="bg-blue-600 text-white px-3 py-1 rounded font-bold">{hotel.rating}</div>
              <div className="flex items-center">
                {[...Array(5)].map((_, i) => (
                  <Star
                    key={i}
                    className={`w-5 h-5 ${
                      i < Math.floor(hotel.rating) ? 'text-yellow-400 fill-current' : 'text-gray-300'
                    }`}
                  />
                ))}
              </div>
            </div>
          </div>

          {/* Hotel Images */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
            <div className="md:col-span-2">
              <img
                src={(hotel.images && hotel.images.length > 0) ? hotel.images[0] : 'https://images.unsplash.com/photo-1566073771259-6a8506099945?ixlib=rb-4.0.3&auto=format&fit=crop&w=600&h=400'}
                alt={hotel.name}
                className="w-full h-80 object-cover rounded-lg"
                onError={(e) => {
                  (e.target as HTMLImageElement).src = 'https://images.unsplash.com/photo-1566073771259-6a8506099945?ixlib=rb-4.0.3&auto=format&fit=crop&w=600&h=400';
                }}
              />
            </div>
            <div className="grid grid-cols-2 md:grid-cols-1 gap-4">
              {/* Always show at least 2 additional images */}
              {[1, 2].map((index) => {
                const imageSrc = (hotel.images && hotel.images.length > index) 
                  ? hotel.images[index] 
                  : `https://images.unsplash.com/photo-${index === 1 ? '1578683010236-d716f9a3f461' : '1571003123894-1f0594d2b5d9'}?ixlib=rb-4.0.3&auto=format&fit=crop&w=400&h=300`;
                
                return (
                  <img
                    key={index}
                    src={imageSrc}
                    alt={`${hotel.name} ${index + 1}`}
                    className="w-full h-36 object-cover rounded-lg"
                    onError={(e) => {
                      (e.target as HTMLImageElement).src = `https://images.unsplash.com/photo-${index === 1 ? '1578683010236-d716f9a3f461' : '1571003123894-1f0594d2b5d9'}?ixlib=rb-4.0.3&auto=format&fit=crop&w=400&h=300`;
                    }}
                  />
                );
              })}
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Main Content */}
          <div className="lg:col-span-2">
            {/* Description */}
            <div className="bg-white border border-gray-200 rounded-lg p-6 mb-8">
              <h2 className="text-xl font-bold mb-4">About this hotel</h2>
              <p className="text-gray-700 leading-relaxed">{hotel.description}</p>
            </div>

            {/* Amenities */}
            <div className="bg-white border border-gray-200 rounded-lg p-6 mb-8">
              <h2 className="text-xl font-bold mb-4">Amenities</h2>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                {hotel.amenities?.map((amenity) => (
                  <div key={amenity} className="flex items-center gap-2">
                    {getAmenityIcon(amenity)}
                    <span className="text-sm">{amenity}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Reviews */}
            {reviews.length > 0 && (
              <div className="bg-white border border-gray-200 rounded-lg p-6">
                <h2 className="text-xl font-bold mb-4">Recent Reviews</h2>
                <div className="space-y-4">
                  {reviews.map((review) => (
                    <div key={review.id} className="border-b pb-4 last:border-b-0">
                      <div className="flex items-center gap-2 mb-2">
                        <div className="bg-blue-600 text-white px-2 py-1 rounded text-sm font-bold">
                          {review.rating}
                        </div>
                        <h4 className="font-semibold">{review.title}</h4>
                      </div>
                      <p className="text-gray-700 text-sm mb-2">{review.comment}</p>
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-gray-500">
                          {new Date(review.created_at).toLocaleDateString()}
                        </span>
                        <span className="text-xs text-gray-500">
                          by {review.reviewer_name}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Sidebar - Available Rooms */}
          <div>
            <div className="bg-white border border-gray-200 rounded-lg p-6 sticky top-4">
              <h2 className="text-xl font-bold mb-4">Available Rooms</h2>
              <div className="space-y-4">
                {hotel.rooms?.map((room) => (
                  <div key={room.id} className="border rounded-lg overflow-hidden">
                    {/* Room Image */}
                    <div className="w-full h-40">
                      <img
                        src={room.images?.[0] || 'https://images.unsplash.com/photo-1611892440504-42a792e24d32?ixlib=rb-4.0.3&auto=format&fit=crop&w=300&h=200'}
                        alt={room.room_type}
                        className="w-full h-full object-cover"
                        onError={(e) => {
                          (e.target as HTMLImageElement).src = 'https://images.unsplash.com/photo-1611892440504-42a792e24d32?ixlib=rb-4.0.3&auto=format&fit=crop&w=300&h=200';
                        }}
                      />
                    </div>
                    
                    <div className="p-4">
                      <h3 className="font-semibold mb-2">{room.room_type}</h3>
                      <p className="text-sm text-gray-600 mb-2">
                        {room.bed_type} • Up to {room.max_occupancy} guests • {room.size_sqft} sq ft
                      </p>

                    {/* Room Amenities */}
                    {room.amenities && room.amenities.length > 0 && (
                      <div className="flex flex-wrap gap-1 mb-3">
                        {room.amenities.slice(0, 3).map((amenity) => (
                          <div key={amenity} className="bg-gray-100 px-2 py-1 rounded text-xs flex items-center gap-1">
                            {getAmenityIcon(amenity)}
                            {amenity}
                          </div>
                        ))}
                        {room.amenities.length > 3 && (
                          <div className="bg-gray-100 px-2 py-1 rounded text-xs border border-gray-300">
                            +{room.amenities.length - 3} more
                          </div>
                        )}
                      </div>
                    )}

                      <div className="flex justify-between items-center">
                        <div>
                          <span className="text-lg font-bold">${room.base_price.toLocaleString()}</span>
                          <span className="text-sm text-gray-600 block">per night</span>
                        </div>
                        <button
                          onClick={() => handleBookRoom(room)}
                          disabled={bookingLoading}
                          className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          {bookingLoading ? 'Booking...' : 'Book Now'}
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
