import React, { useState } from 'react';
import { format, differenceInDays, parseISO } from 'date-fns';
import { 
  CalendarIcon, 
  UserIcon, 
  CreditCardIcon, 
  EnvelopeIcon,
  PhoneIcon,
  DocumentTextIcon
} from '@heroicons/react/24/outline';
import { RoomBasic, BookingCreate } from '../../types';
import { useSearch } from '../../contexts/SearchContext';

interface EnhancedBookingFormProps {
  room: RoomBasic;
  hotelId: number;
  hotelName: string;
  onSubmit: (bookingData: BookingCreate) => void;
  onCancel: () => void;
  isLoading?: boolean;
  initialCheckIn?: string;
  initialCheckOut?: string;
}

const EnhancedBookingForm: React.FC<EnhancedBookingFormProps> = ({
  room,
  hotelId,
  hotelName,
  onSubmit,
  onCancel,
  isLoading = false,
  initialCheckIn,
  initialCheckOut
}) => {
  const { searchParams } = useSearch();
  const [checkIn, setCheckIn] = useState(initialCheckIn || searchParams.check_in);
  const [checkOut, setCheckOut] = useState(initialCheckOut || searchParams.check_out);
  const [guestCount, setGuestCount] = useState(1);
  const [guestDetails, setGuestDetails] = useState({
    firstName: '',
    lastName: '',
    email: '',
    phone: '',
    specialRequests: ''
  });
  const [step, setStep] = useState(1);

  const calculateBookingDetails = () => {
    const days = differenceInDays(new Date(checkOut), new Date(checkIn));
    const validDays = days > 0 ? days : 1;
    const subtotal = validDays * room.price_per_night;
    const taxes = subtotal * 0.12; // 12% taxes
    const total = subtotal + taxes;
    
    return { days: validDays, subtotal, taxes, total };
  };

  const { days, subtotal, taxes, total } = calculateBookingDetails();
  const isValidDates = days > 0;

  const handleNext = () => {
    if (step === 1 && isValidDates) {
      setStep(2);
    }
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

  return (
    <div className="bg-white rounded-xl shadow-lg border border-secondary-200 overflow-hidden">
      {/* Header */}
      <div className="bg-gradient-to-r from-primary-600 to-primary-700 px-6 py-4 text-white">
        <h3 className="text-xl font-bold">Complete Your Booking</h3>
        <p className="text-primary-100 text-sm">Step {step} of 2</p>
      </div>

      <div className="p-6 space-y-6">
        {/* Booking Summary */}
        <div className="bg-secondary-50 rounded-lg p-4 space-y-3">
          <h4 className="font-semibold text-secondary-900">Booking Summary</h4>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="text-secondary-600">Hotel:</span>
              <p className="font-medium">{hotelName}</p>
            </div>
            <div>
              <span className="text-secondary-600">Room:</span>
              <p className="font-medium">
                {room.room_number} - {room.room_type.replace('_', ' ')}
              </p>
            </div>
            <div>
              <span className="text-secondary-600">Guests:</span>
              <p className="font-medium">Up to {room.occupancy}</p>
            </div>
            <div>
              <span className="text-secondary-600">Rate:</span>
              <p className="font-medium">${room.price_per_night}/night</p>
            </div>
          </div>
        </div>

        {step === 1 && (
          <div className="space-y-6">
            {/* Date Selection */}
            <div className="space-y-4">
              <h4 className="font-semibold text-secondary-900">Select Your Dates</h4>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-secondary-700 mb-2">
                    Check-in Date
                  </label>
                  <div className="relative">
                    <CalendarIcon className="absolute left-3 top-3 w-4 h-4 text-secondary-400" />
                    <input
                      type="date"
                      value={checkIn}
                      onChange={(e) => setCheckIn(e.target.value)}
                      min={format(new Date(), 'yyyy-MM-dd')}
                      className="input-field pl-10"
                      required
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-secondary-700 mb-2">
                    Check-out Date
                  </label>
                  <div className="relative">
                    <CalendarIcon className="absolute left-3 top-3 w-4 h-4 text-secondary-400" />
                    <input
                      type="date"
                      value={checkOut}
                      onChange={(e) => setCheckOut(e.target.value)}
                      min={checkIn}
                      className="input-field pl-10"
                      required
                    />
                  </div>
                </div>
              </div>

              {/* Guest Count */}
              <div>
                <label className="block text-sm font-medium text-secondary-700 mb-2">
                  Number of Guests
                </label>
                <div className="relative">
                  <UserIcon className="absolute left-3 top-3 w-4 h-4 text-secondary-400" />
                  <select
                    value={guestCount}
                    onChange={(e) => setGuestCount(parseInt(e.target.value))}
                    className="input-field pl-10"
                    required
                  >
                    {Array.from({ length: room.occupancy }, (_, i) => (
                      <option key={i + 1} value={i + 1}>
                        {i + 1} Guest{i + 1 !== 1 ? 's' : ''}
                      </option>
                    ))}
                  </select>
                </div>
                <p className="text-sm text-secondary-500 mt-1">
                  Maximum occupancy: {room.occupancy} guests
                </p>
              </div>

              {!isValidDates && (
                <div className="text-red-600 text-sm bg-red-50 p-3 rounded-lg border border-red-200">
                  Check-out date must be after check-in date
                </div>
              )}
            </div>

            {/* Price Breakdown */}
            {isValidDates && (
              <div className="bg-primary-50 rounded-lg p-4 space-y-3">
                <h4 className="font-semibold text-primary-900">Price Breakdown</h4>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span>${room.price_per_night} × {days} night{days !== 1 ? 's' : ''}</span>
                    <span>${subtotal.toFixed(2)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Taxes & fees</span>
                    <span>${taxes.toFixed(2)}</span>
                  </div>
                  <div className="border-t border-primary-200 pt-2 flex justify-between font-semibold text-lg">
                    <span>Total</span>
                    <span className="text-primary-600">${total.toFixed(2)}</span>
                  </div>
                </div>
              </div>
            )}

            <div className="flex gap-3">
              <button
                type="button"
                onClick={onCancel}
                className="btn-secondary flex-1"
                disabled={isLoading}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleNext}
                className="btn-primary flex-1"
                disabled={!isValidDates || isLoading}
              >
                Next: Guest Details
              </button>
            </div>
          </div>
        )}

        {step === 2 && (
          <form onSubmit={handleSubmit} className="space-y-6">
            <div className="space-y-4">
              <h4 className="font-semibold text-secondary-900">Guest Information</h4>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-secondary-700 mb-2">
                    First Name
                  </label>
                  <div className="relative">
                    <UserIcon className="absolute left-3 top-3 w-4 h-4 text-secondary-400" />
                    <input
                      type="text"
                      value={guestDetails.firstName}
                      onChange={(e) => setGuestDetails(prev => ({ ...prev, firstName: e.target.value }))}
                      className="input-field pl-10"
                      placeholder="John"
                      required
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-secondary-700 mb-2">
                    Last Name
                  </label>
                  <div className="relative">
                    <UserIcon className="absolute left-3 top-3 w-4 h-4 text-secondary-400" />
                    <input
                      type="text"
                      value={guestDetails.lastName}
                      onChange={(e) => setGuestDetails(prev => ({ ...prev, lastName: e.target.value }))}
                      className="input-field pl-10"
                      placeholder="Doe"
                      required
                    />
                  </div>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-secondary-700 mb-2">
                  Email Address
                </label>
                <div className="relative">
                  <EnvelopeIcon className="absolute left-3 top-3 w-4 h-4 text-secondary-400" />
                  <input
                    type="email"
                    value={guestDetails.email}
                    onChange={(e) => setGuestDetails(prev => ({ ...prev, email: e.target.value }))}
                    className="input-field pl-10"
                    placeholder="john.doe@example.com"
                    required
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-secondary-700 mb-2">
                  Phone Number
                </label>
                <div className="relative">
                  <PhoneIcon className="absolute left-3 top-3 w-4 h-4 text-secondary-400" />
                  <input
                    type="tel"
                    value={guestDetails.phone}
                    onChange={(e) => setGuestDetails(prev => ({ ...prev, phone: e.target.value }))}
                    className="input-field pl-10"
                    placeholder="+1 (555) 123-4567"
                    required
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-secondary-700 mb-2">
                  Special Requests (Optional)
                </label>
                <div className="relative">
                  <DocumentTextIcon className="absolute left-3 top-3 w-4 h-4 text-secondary-400" />
                  <textarea
                    value={guestDetails.specialRequests}
                    onChange={(e) => setGuestDetails(prev => ({ ...prev, specialRequests: e.target.value }))}
                    className="input-field pl-10 resize-none"
                    rows={3}
                    placeholder="Any special requests or dietary requirements..."
                  />
                </div>
              </div>
            </div>

            {/* Final Price Summary */}
            <div className="bg-primary-50 rounded-lg p-4">
              <div className="flex justify-between items-center text-lg font-bold text-primary-900">
                <span>Total Amount</span>
                <span>${total.toFixed(2)}</span>
              </div>
              <p className="text-primary-700 text-sm mt-1">
                For {days} night{days !== 1 ? 's' : ''} • {format(parseISO(checkIn), 'MMM dd')} - {format(parseISO(checkOut), 'MMM dd')}
              </p>
            </div>

            <div className="flex gap-3">
              <button
                type="button"
                onClick={() => setStep(1)}
                className="btn-secondary flex-1"
                disabled={isLoading}
              >
                Back
              </button>
              <button
                type="submit"
                className="btn-primary flex-1 flex items-center justify-center gap-2"
                disabled={isLoading}
              >
                {isLoading ? (
                  <>
                    <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    Processing...
                  </>
                ) : (
                  <>
                    <CreditCardIcon className="w-4 h-4" />
                    Confirm Booking
                  </>
                )}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
};

export default EnhancedBookingForm;