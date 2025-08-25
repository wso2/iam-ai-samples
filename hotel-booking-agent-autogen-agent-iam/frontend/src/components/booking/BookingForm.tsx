import React, { useState } from 'react';
import { format, addDays, differenceInDays } from 'date-fns';
import { CalendarIcon, UserIcon } from '@heroicons/react/24/outline';
import { Room, BookingCreate } from '../../types';

interface BookingFormProps {
  room: Room;
  hotelId: number;
  hotelName: string;
  onSubmit: (bookingData: BookingCreate) => void;
  onCancel: () => void;
  isLoading?: boolean;
}

const BookingForm: React.FC<BookingFormProps> = ({
  room,
  hotelId,
  hotelName,
  onSubmit,
  onCancel,
  isLoading = false
}) => {
  const [checkIn, setCheckIn] = useState(format(new Date(), 'yyyy-MM-dd'));
  const [checkOut, setCheckOut] = useState(format(addDays(new Date(), 1), 'yyyy-MM-dd'));
  const [guestCount, setGuestCount] = useState(1);

  const calculateTotal = () => {
    const days = differenceInDays(new Date(checkOut), new Date(checkIn));
    return days > 0 ? days * room.base_price : 0;
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit({
      hotel_id: hotelId,
      room_id: room.id,
      check_in: checkIn,
      check_out: checkOut,
      guests: guestCount,
    });
  };

  const days = differenceInDays(new Date(checkOut), new Date(checkIn));
  const isValidDates = days > 0;

  return (
    <div className="card">
      <h3 className="text-xl font-semibold text-secondary-900 mb-6">
        Book Your Stay
      </h3>
      
      <div className="space-y-6">
        {/* Booking Summary */}
        <div className="bg-secondary-50 p-4 rounded-lg space-y-2">
          <div className="flex justify-between">
            <span className="text-secondary-600">Hotel:</span>
            <span className="font-medium">{hotelName}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-secondary-600">Room:</span>
            <span className="font-medium">
              {room.room_type}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-secondary-600">Price per night:</span>
            <span className="font-medium">${room.base_price.toLocaleString()}</span>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Check-in Date */}
          <div>
            <label className="block text-sm font-medium text-secondary-700 mb-2">
              Check-in Date
            </label>
            <div className="relative">
              <input
                type="date"
                value={checkIn}
                onChange={(e) => setCheckIn(e.target.value)}
                min={format(new Date(), 'yyyy-MM-dd')}
                className="input-field pl-10"
                required
              />
              <CalendarIcon className="absolute left-3 top-3 w-4 h-4 text-secondary-400" />
            </div>
          </div>

          {/* Check-out Date */}
          <div>
            <label className="block text-sm font-medium text-secondary-700 mb-2">
              Check-out Date
            </label>
            <div className="relative">
              <input
                type="date"
                value={checkOut}
                onChange={(e) => setCheckOut(e.target.value)}
                min={checkIn}
                className="input-field pl-10"
                required
              />
              <CalendarIcon className="absolute left-3 top-3 w-4 h-4 text-secondary-400" />
            </div>
          </div>

          {/* Guest Count */}
          <div>
            <label className="block text-sm font-medium text-secondary-700 mb-2">
              Number of Guests
            </label>
            <div className="relative">
              <select
                value={guestCount}
                onChange={(e) => setGuestCount(parseInt(e.target.value))}
                className="input-field pl-10"
                required
              >
                {Array.from({ length: room.max_occupancy }, (_, i) => (
                  <option key={i + 1} value={i + 1}>
                    {i + 1} Guest{i + 1 !== 1 ? 's' : ''}
                  </option>
                ))}
              </select>
              <UserIcon className="absolute left-3 top-3 w-4 h-4 text-secondary-400" />
            </div>
            <p className="text-sm text-secondary-500 mt-1">
              Maximum occupancy: {room.max_occupancy} guests
            </p>
          </div>

          {/* Total Calculation */}
          {isValidDates && (
            <div className="bg-primary-50 p-4 rounded-lg space-y-2">
              <div className="flex justify-between text-sm">
                <span>Duration:</span>
                <span>{days} night{days !== 1 ? 's' : ''}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span>Rate:</span>
                <span>${room.base_price.toLocaleString()} × {days}</span>
              </div>
              <div className="border-t border-primary-200 pt-2 flex justify-between font-semibold">
                <span>Total:</span>
                <span className="text-primary-600">{calculateTotal().toLocaleString()}</span>
              </div>
            </div>
          )}

          {!isValidDates && (
            <div className="text-red-600 text-sm">
              Check-out date must be after check-in date
            </div>
          )}

          {/* Action Buttons */}
          <div className="flex gap-3 pt-4">
            <button
              type="button"
              onClick={onCancel}
              className="btn-secondary flex-1"
              disabled={isLoading}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="btn-primary flex-1"
              disabled={!isValidDates || isLoading}
            >
              {isLoading ? 'Booking...' : 'Confirm Booking'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default BookingForm;
