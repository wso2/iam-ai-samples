import React, { useState } from 'react';
import { 
  UserIcon, 
  CurrencyDollarIcon,
  CheckCircleIcon,
  XCircleIcon,
  InformationCircleIcon
} from '@heroicons/react/24/outline';
import { RoomBasic } from '../../types';
import { differenceInDays } from 'date-fns';

interface EnhancedRoomCardProps {
  room: RoomBasic;
  onSelect: (room: RoomBasic) => void;
  isSelected?: boolean;
  checkIn?: string;
  checkOut?: string;
  className?: string;
}

const EnhancedRoomCard: React.FC<EnhancedRoomCardProps> = ({ 
  room, 
  onSelect, 
  isSelected = false,
  checkIn,
  checkOut,
  className = ''
}) => {
  const [showDetails, setShowDetails] = useState(false);

  const calculateTotal = () => {
    if (!checkIn || !checkOut) return room.price_per_night;
    const days = differenceInDays(new Date(checkOut), new Date(checkIn));
    return days > 0 ? days * room.price_per_night : room.price_per_night;
  };

  const calculateDays = () => {
    if (!checkIn || !checkOut) return 1;
    const days = differenceInDays(new Date(checkOut), new Date(checkIn));
    return days > 0 ? days : 1;
  };

  const getRoomTypeDetails = (roomType: string) => {
    const details = {
      'standard': {
        features: ['Free WiFi', 'Air Conditioning', 'Safe'],
        description: 'Comfortable accommodation with essential amenities'
      },
      'deluxe': {
        features: ['Free WiFi', 'Air Conditioning', 'Mini Bar', 'Safe', 'Garden View'],
        description: 'Spacious room with modern amenities and beautiful views'
      },
      'super_deluxe': {
        features: ['Free WiFi', 'Air Conditioning', 'Mini Bar', 'Safe', 'Bathtub', 'Sea/City View'],
        description: 'Luxury accommodation with premium amenities and stunning views'
      },
      'studio': {
        features: ['Free WiFi', 'Kitchen', 'Washing Machine', 'Air Conditioning', 'Safe'],
        description: 'Apartment-style accommodation with kitchen facilities'
      }
    };
    
    return details[roomType as keyof typeof details] || {
      features: ['Free WiFi', 'Air Conditioning'],
      description: 'Comfortable accommodation with modern amenities'
    };
  };

  const roomDetails = getRoomTypeDetails(room.room_type);

  return (
    <div 
      className={`
        bg-white rounded-xl border-2 transition-all duration-300 overflow-hidden
        ${isSelected 
          ? 'border-primary-500 shadow-lg bg-primary-50' 
          : 'border-secondary-200 hover:border-secondary-300 hover:shadow-md'
        }
        ${!room.is_available ? 'opacity-60' : 'cursor-pointer'}
        ${className}
      `}
      onClick={() => room.is_available && onSelect(room)}
    >
      {/* Room Header */}
      <div className="p-6 border-b border-secondary-200">
        <div className="flex justify-between items-start mb-4">
          <div className="flex-1">
            <div className="flex items-center gap-3 mb-2">
              <h3 className="text-xl font-bold text-secondary-900">
                Room {room.room_number}
              </h3>
              <span className={`
                px-3 py-1 rounded-full text-xs font-medium
                ${room.is_available 
                  ? 'bg-green-100 text-green-800' 
                  : 'bg-red-100 text-red-800'
                }
              `}>
                {room.is_available ? 'Available' : 'Booked'}
              </span>
            </div>
            
            <p className="text-primary-600 font-semibold text-lg capitalize mb-1">
              {room.room_type.replace('_', ' ')} Room
            </p>
            
            <p className="text-secondary-600 text-sm mb-3">
              {roomDetails.description}
            </p>

            <div className="flex items-center gap-4 text-sm text-secondary-600">
              <div className="flex items-center gap-1">
                <UserIcon className="w-4 h-4" />
                <span>Up to {room.occupancy} guests</span>
              </div>
            </div>
          </div>

          <div className="text-right ml-4">
            <div className="flex items-center justify-end gap-1 mb-1">
              <CurrencyDollarIcon className="w-5 h-5 text-secondary-500" />
              <span className="text-2xl font-bold text-secondary-900">
                {room.price_per_night}
              </span>
            </div>
            <p className="text-sm text-secondary-500">per night</p>
            
            {checkIn && checkOut && calculateDays() > 1 && (
              <div className="mt-2 pt-2 border-t border-secondary-200">
                <p className="text-sm text-secondary-600">
                  {calculateDays()} nights: <span className="font-semibold">${calculateTotal()}</span>
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Room Features */}
        <div className="space-y-3">
          <button
            onClick={(e) => {
              e.stopPropagation();
              setShowDetails(!showDetails);
            }}
            className="flex items-center gap-2 text-sm text-primary-600 hover:text-primary-700"
          >
            <InformationCircleIcon className="w-4 h-4" />
            {showDetails ? 'Hide Details' : 'View Amenities'}
          </button>

          {showDetails && (
            <div className="grid grid-cols-2 gap-3 pt-3 border-t border-secondary-200">
              {roomDetails.features.map((feature, index) => (
                <div key={index} className="flex items-center gap-2 text-sm">
                  <CheckCircleIcon className="w-4 h-4 text-green-600 flex-shrink-0" />
                  <span className="text-secondary-700">{feature}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Selection Indicator */}
      {isSelected && (
        <div className="px-6 py-4 bg-primary-100 border-t border-primary-200">
          <div className="flex items-center gap-2 text-primary-800">
            <CheckCircleIcon className="w-5 h-5" />
            <span className="font-medium">Selected for booking</span>
          </div>
        </div>
      )}

      {/* Unavailable Overlay */}
      {!room.is_available && (
        <div className="px-6 py-4 bg-red-50 border-t border-red-200">
          <div className="flex items-center gap-2 text-red-800">
            <XCircleIcon className="w-5 h-5" />
            <span className="font-medium">Currently unavailable</span>
          </div>
        </div>
      )}
    </div>
  );
};

export default EnhancedRoomCard;