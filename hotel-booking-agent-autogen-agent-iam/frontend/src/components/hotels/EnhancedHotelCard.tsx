import React from 'react';
import { Link } from 'react-router-dom';
import { 
  MapPinIcon, 
  EyeIcon
} from '@heroicons/react/24/outline';
import { Hotel } from '../../types';

interface EnhancedHotelCardProps {
  hotel: Hotel;
  searchPreferences?: {
    checkIn?: string;
    checkOut?: string;
    guests?: number;
  };
}

const EnhancedHotelCard: React.FC<EnhancedHotelCardProps> = ({ 
  hotel, 
  searchPreferences 
}) => {
  // Static images from home page - mapped to specific hotels for consistency
  const getHotelImage = () => {
    // Map specific hotels to specific images for consistency with home page
    const hotelImageMapping: { [key: string]: { src: string; alt: string } } = {
      'Gardeo Saman Villa': {
        src: "https://images.unsplash.com/photo-1566073771259-6a8506099945?ixlib=rb-4.0.3&auto=format&fit=crop&w=400&h=250",
        alt: "Gardeo Saman Villa"
      },
      'Gardeo Colombo Seven': {
        src: "https://images.unsplash.com/photo-1578683010236-d716f9a3f461?ixlib=rb-4.0.3&auto=format&fit=crop&w=400&h=250", 
        alt: "Gardeo Colombo Seven"
      },
      'Gardeo Kandy Hills': {
        src: "https://images.unsplash.com/photo-1571003123894-1f0594d2b5d9?ixlib=rb-4.0.3&auto=format&fit=crop&w=400&h=250",
        alt: "Gardeo Kandy Hills"
      },
      'Gardeo Beach Resort Galle': {
        src: "https://images.unsplash.com/photo-1582719508461-905c673771fd?ixlib=rb-4.0.3&auto=format&fit=crop&w=400&h=250",
        alt: "Gardeo Beach Resort Galle"
      }
    };

    // Additional fallback images for other hotels
    const fallbackImages = [
      {
        src: "https://images.unsplash.com/photo-1551882547-ff40c63fe5fa?ixlib=rb-4.0.3&auto=format&fit=crop&w=400&h=250",
        alt: "Boutique Hotel"
      },
      {
        src: "https://images.unsplash.com/photo-1596394516093-501ba68a0ba6?ixlib=rb-4.0.3&auto=format&fit=crop&w=400&h=250",
        alt: "Garden Hotel"
      },
      {
        src: "https://images.unsplash.com/photo-1564501049412-61c2a3083791?ixlib=rb-4.0.3&auto=format&fit=crop&w=400&h=250",
        alt: "Mountain Resort"
      },
      {
        src: "https://images.unsplash.com/photo-1520250497591-112f2f40a3f4?ixlib=rb-4.0.3&auto=format&fit=crop&w=400&h=250",
        alt: "City Hotel"
      }
    ];

    // Return mapped image if exists, otherwise use fallback based on hotel ID
    if (hotelImageMapping[hotel.name]) {
      return hotelImageMapping[hotel.name];
    }

    // Use hotel ID to get consistent fallback image
    const imageIndex = hotel.id % fallbackImages.length;
    return fallbackImages[imageIndex];
  };

  const hotelImage = getHotelImage();

  const buildViewLink = () => {
    const params = new URLSearchParams();
    if (searchPreferences?.checkIn) params.set('checkIn', searchPreferences.checkIn);
    if (searchPreferences?.checkOut) params.set('checkOut', searchPreferences.checkOut);
    if (searchPreferences?.guests) params.set('guests', searchPreferences.guests.toString());
    
    return `/hotels/${hotel.id}${params.toString() ? `?${params.toString()}` : ''}`;
  };

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden hover:shadow-lg transition-all duration-300 group">
      {/* Image Section */}
      <div className="relative">
        <img 
          src={hotelImage.src}
          alt={hotelImage.alt}
          className="w-full h-48 object-cover"
          loading="lazy"
        />
      </div>

      {/* Content Section */}
      <div className="p-4 space-y-3">
        {/* Header */}
        <div className="space-y-1">
          <h3 className="font-bold text-lg mb-2 group-hover:text-blue-600 transition-colors line-clamp-1">
            {hotel.name}
          </h3>
          
          <div className="flex items-center gap-1 text-gray-600 mb-2">
            <MapPinIcon className="w-4 h-4 flex-shrink-0" />
            <span className="text-sm">{hotel.address.city}, {hotel.address.country}</span>
          </div>
        </div>

        {/* Description */}
        <p className="text-gray-700 text-sm line-clamp-2 leading-relaxed">
          {hotel.description}
        </p>

        {/* Rating and Price Row */}
        <div className="flex items-center justify-between">
          <div className="flex items-center">
            <span className="bg-blue-600 text-white px-2 py-1 rounded text-sm font-bold mr-2">
              {hotel.rating}
            </span>
            <span className="text-sm text-gray-600">
              {hotel.rating >= 4.8 ? 'Outstanding' : 
               hotel.rating >= 4.5 ? 'Excellent' : 
               hotel.rating >= 4.0 ? 'Very Good' : 'Good'}
            </span>
          </div>
          <div className="text-right">
            <span className="text-lg font-bold">
              ${Math.round(hotel.price_range.min).toLocaleString()}
            </span>
            <p className="text-sm text-gray-600">per night</p>
          </div>
        </div>

        {/* Amenities */}
        <div className="space-y-2">
          <div className="flex flex-wrap gap-2">
            {hotel.amenities.slice(0, 3).map((amenity, index) => (
              <span
                key={index}
                className="px-2 py-1 bg-blue-50 text-blue-700 text-xs font-medium rounded border border-blue-200"
              >
                {amenity}
              </span>
            ))}
          </div>
        </div>

        {/* Action Button */}
        <div className="pt-2">
          <Link
            to={buildViewLink()}
            className="w-full bg-blue-600 hover:bg-blue-700 text-white py-2 px-4 rounded-lg font-medium transition-colors text-center flex items-center justify-center gap-2 group"
          >
            <EyeIcon className="w-4 h-4" />
            View Details & Book
          </Link>
        </div>
      </div>
    </div>
  );
};

export default EnhancedHotelCard;
