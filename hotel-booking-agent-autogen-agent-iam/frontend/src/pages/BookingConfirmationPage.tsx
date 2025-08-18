import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { CheckCircle, Calendar, Users } from 'lucide-react';
import { EnhancedHeader } from '../components/layout/EnhancedHeader';
import { Booking } from '../types';

export function BookingConfirmationPage() {
  const [booking, setBooking] = useState<Booking | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    const bookingData = sessionStorage.getItem('bookingConfirmation');
    if (bookingData) {
      setBooking(JSON.parse(bookingData));
    }
  }, []);

  if (!booking) {
    return (
      <div className="min-h-screen bg-white">
        <EnhancedHeader />
        <div className="container mx-auto px-4 py-8">
          <div className="text-center">
            <h1 className="text-2xl font-bold mb-4">Booking not found</h1>
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
        <div className="max-w-2xl mx-auto">
          {/* Success Header */}
          <div className="text-center mb-8">
            <CheckCircle className="w-16 h-16 text-green-500 mx-auto mb-4" />
            <h1 className="text-3xl font-bold text-green-600 mb-2">Booking Confirmed!</h1>
            <p className="text-gray-600">Your reservation has been successfully created.</p>
          </div>

          {/* Booking Details */}
          <div className="bg-white border border-gray-200 rounded-lg p-6 mb-8">
            <h2 className="text-xl font-bold mb-4">Booking Details</h2>

            <div className="space-y-4">
              <div className="flex justify-between">
                <span className="font-medium">Booking ID:</span>
                <span className="font-mono">#{booking.id}</span>
              </div>

              {booking.confirmation_number && (
                <div className="flex justify-between">
                  <span className="font-medium">Confirmation Number:</span>
                  <span className="font-mono">{booking.confirmation_number}</span>
                </div>
              )}

              <div className="flex justify-between">
                <span className="font-medium">Hotel:</span>
                <span>{booking.hotel_name}</span>
              </div>

              <div className="flex justify-between">
                <span className="font-medium">Room Type:</span>
                <span className="capitalize">{booking.room_type}</span>
              </div>

              <div className="flex justify-between">
                <span className="font-medium">Status:</span>
                <span className="capitalize text-green-600 font-semibold">{booking.status}</span>
              </div>

              <div className="flex items-center justify-between">
                <span className="font-medium flex items-center gap-2">
                  <Calendar className="w-4 h-4" />
                  Check-in:
                </span>
                <span>{new Date(booking.check_in).toLocaleDateString()}</span>
              </div>

              <div className="flex items-center justify-between">
                <span className="font-medium flex items-center gap-2">
                  <Calendar className="w-4 h-4" />
                  Check-out:
                </span>
                <span>{new Date(booking.check_out).toLocaleDateString()}</span>
              </div>

              <div className="flex items-center justify-between">
                <span className="font-medium flex items-center gap-2">
                  <Users className="w-4 h-4" />
                  Guests:
                </span>
                <span>{booking.guests}</span>
              </div>

              <div className="border-t pt-4">
                <div className="flex justify-between text-lg font-bold">
                  <span>Total Amount:</span>
                  <span>${booking.total_amount?.toLocaleString()}</span>
                </div>
              </div>
            </div>
          </div>

          {/* Special Requests */}
          {booking.special_requests && booking.special_requests.length > 0 && (
            <div className="bg-white border border-gray-200 rounded-lg p-6 mb-8">
              <h3 className="font-bold mb-2">Special Requests:</h3>
              <ul className="list-disc list-inside space-y-1">
                {booking.special_requests.map((request, index) => (
                  <li key={index} className="text-gray-700">
                    {request}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Next Steps */}
          <div className="bg-white border border-gray-200 rounded-lg p-6 mb-8">
            <h3 className="font-bold mb-4">What's Next?</h3>
            <ul className="space-y-2 text-gray-700">
              <li>• You'll receive a confirmation email shortly</li>
              <li>• Check-in time is typically 2:00 PM</li>
              <li>• Check-out time is typically 11:00 AM</li>
              <li>• Contact the hotel directly for any special arrangements</li>
              <li>• Present your confirmation number at check-in</li>
            </ul>
          </div>

          {/* Action Buttons */}
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <button
              onClick={() => navigate('/')}
              className="bg-transparent border border-gray-300 hover:bg-gray-50 text-gray-700 px-6 py-2 rounded-lg font-medium transition-colors w-full sm:w-auto"
            >
              Book Another Stay
            </button>
            <button
              onClick={() => navigate('/bookings')}
              className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-2 rounded-lg font-medium transition-colors w-full sm:w-auto"
            >
              View My Bookings
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default BookingConfirmationPage;
