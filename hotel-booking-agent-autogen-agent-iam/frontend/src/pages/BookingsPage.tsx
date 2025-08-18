import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { format } from 'date-fns';
import { CalendarIcon, MapPinIcon, EyeIcon } from '@heroicons/react/24/outline';
import { useAuth } from '../contexts/AsgardeoAuthContext';
import { hotelAPI } from '../services/api';
import { Booking } from '../types';
import LoadingSpinner from '../components/common/LoadingSpinner';
import ErrorMessage from '../components/common/ErrorMessage';
import { EnhancedHeader } from '../components/layout/EnhancedHeader';

const BookingsPage: React.FC = () => {
  const { user, hasScope } = useAuth();
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedBooking, setExpandedBooking] = useState<number | null>(null);

  useEffect(() => {
    const fetchBookings = async () => {
      if (!user?.sub) return;
      
      try {
        setLoading(true);
        setError(null);
        const response = await hotelAPI.getUserBookings(user.sub);
        setBookings(response.data.bookings || []);
      } catch (err: any) {
        setError(err.response?.data?.detail || 'Failed to load bookings');
      } finally {
        setLoading(false);
      }
    };

    fetchBookings();
  }, [user, hasScope]);

  if (loading) {
    return (
      <div className="min-h-screen bg-white">
        <EnhancedHeader />
        <div className="container mx-auto px-4 py-8">
          <div className="flex justify-center items-center h-64">
            <div className="text-center space-y-4">
              <LoadingSpinner size="lg" />
              <p className="text-gray-600 font-medium">Loading your bookings...</p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-white">
        <EnhancedHeader />
        <div className="container mx-auto px-4 py-8">
          <div className="max-w-2xl mx-auto">
            <ErrorMessage message={error} />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-white">
      <EnhancedHeader />
      <div className="container mx-auto px-4 py-8">
        <div className="space-y-8">
          {/* Book New Stay Button */}
          <div className="flex justify-end">
            <Link 
              to="/hotels" 
              className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-2 rounded-lg font-medium transition-colors"
            >
              Book New Stay
            </Link>
          </div>

        {/* Bookings List */}
        {bookings.length === 0 ? (
          <div className="text-center py-12">
            <div className="bg-white rounded-lg shadow-md p-8 max-w-lg mx-auto border">
              <div className="space-y-4">
                <CalendarIcon className="w-16 h-16 text-gray-400 mx-auto" />
                <div>
                  <h3 className="text-lg font-medium text-gray-900">
                    No bookings yet
                  </h3>
                  <p className="text-gray-600 mt-1">
                    Start planning your next getaway!
                  </p>
                </div>
                <Link 
                  to="/hotels"
                  className="inline-block bg-blue-600 hover:bg-blue-700 text-white px-6 py-2 rounded-lg font-medium transition-colors"
                >
                  Explore Hotels
                </Link>
              </div>
            </div>
          </div>
        ) : (
          <div className="space-y-6">
            {bookings.map((booking) => {
              const isExpanded = expandedBooking === booking.id;
              return (
                <div key={booking.id} className="bg-white rounded-lg shadow-md hover:shadow-lg transition-shadow border p-6">
                  <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
                    <div className="flex-1 space-y-3">
                      <div className="flex items-start justify-between">
                        <div>
                          <h3 className="text-xl font-semibold text-gray-900">
                            {booking.hotel_name}
                          </h3>
                          <p className="text-gray-600">
                            Room {booking.room_id} • {booking.room_type.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase())}
                          </p>
                          {/* Agent Indicator */}
                          {booking.created_by === 'agent' && booking.agent_info && (
                            <div className="flex items-center gap-1 mt-1">
                              <svg className="w-4 h-4 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                              </svg>
                              <span className="text-sm text-blue-600 font-medium">
                                Booked by {booking.agent_info.display_name || 'Agent'}
                              </span>
                            </div>
                          )}
                          
                        </div>
                        <span className="px-3 py-1 bg-green-100 text-green-800 rounded-full text-sm font-medium">
                          Confirmed
                        </span>
                      </div>

                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                        <div className="flex items-center gap-2 text-gray-600">
                          <CalendarIcon className="w-4 h-4" />
                          <span className="text-sm">
                            {format(new Date(booking.check_in), 'MMM dd')} - {' '}
                            {format(new Date(booking.check_out), 'MMM dd, yyyy')}
                          </span>
                        </div>
                        <div className="flex items-center gap-2 text-gray-600">
                          <MapPinIcon className="w-4 h-4" />
                          <span className="text-sm">Booking #{booking.id}</span>
                        </div>
                      </div>

                      {/* Expanded Details */}
                      {isExpanded && (
                        <div className="mt-6 pt-6 border-t border-gray-200 space-y-4">
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                            <div className="space-y-3">
                              <h4 className="font-semibold text-gray-900">Booking Information</h4>
                              <div className="space-y-2 text-sm">
                                <div className="flex justify-between">
                                  <span className="text-gray-600">Booking ID:</span>
                                  <span className="font-medium">#{booking.id}</span>
                                </div>
                                <div className="flex justify-between">
                                  <span className="text-gray-600">Guest Name:</span>
                                  <span className="font-medium">
                                    {booking.user_info?.display_name || booking.user_info?.first_name || user?.given_name || 'N/A'}
                                  </span>
                                </div>
                                <div className="flex justify-between">
                                  <span className="text-gray-600">Number of Guests:</span>
                                  <span className="font-medium">{booking.guests} {booking.guests === 1 ? 'Guest' : 'Guests'}</span>
                                </div>
                                <div className="flex justify-between">
                                  <span className="text-gray-600">Booked By:</span>
                                  <span className="font-medium">
                                    {booking.created_by === 'agent' ? (
                                      <span className="flex items-center gap-1 text-blue-600">
                                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                                        </svg>
                                        {booking.agent_info?.display_name || 'Agent'}
                                      </span>
                                    ) : (
                                      'Direct Booking'
                                    )}
                                  </span>
                                </div>
                                <div className="flex justify-between">
                                  <span className="text-gray-600">Special Requests:</span>
                                  <span className="font-medium">{booking.special_requests?.length > 0 ? booking.special_requests.join(', ') : 'None'}</span>
                                </div>
                              </div>
                            </div>
                            <div className="space-y-3">
                              <h4 className="font-semibold text-gray-900">Stay Details</h4>
                              <div className="space-y-2 text-sm">
                                <div className="flex justify-between">
                                  <span className="text-gray-600">Check-in:</span>
                                  <span className="font-medium">{format(new Date(booking.check_in), 'EEEE, MMM dd, yyyy')}</span>
                                </div>
                                <div className="flex justify-between">
                                  <span className="text-gray-600">Check-out:</span>
                                  <span className="font-medium">{format(new Date(booking.check_out), 'EEEE, MMM dd, yyyy')}</span>
                                </div>
                                <div className="flex justify-between">
                                  <span className="text-gray-600">Duration:</span>
                                  <span className="font-medium">
                                    {Math.ceil((new Date(booking.check_out).getTime() - new Date(booking.check_in).getTime()) / (1000 * 60 * 60 * 24))} nights
                                  </span>
                                </div>
                                <div className="flex justify-between">
                                  <span className="text-gray-600">Room Type:</span>
                                  <span className="font-medium">{booking.room_type.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase())}</span>
                                </div>
                              </div>
                            </div>
                          </div>

                          {/* Assigned Staff Information */}
                          {booking.assigned_staff && booking.assigned_staff.length > 0 && (
                            <div className="pt-4 border-t border-gray-100">
                              <h4 className="font-semibold text-gray-900 mb-3 flex items-center gap-2">
                                <svg className="w-4 h-4 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.196-2.12L17 20zM9 12a4 4 0 100-8 4 4 0 000 8zm8 0a4 4 0 100-8 4 4 0 000 8zM9 20h8v-2a3 3 0 00-3-3H9v5z" />
                                </svg>
                                Assigned Contact Person
                              </h4>
                              <div className="space-y-3">
                                {booking.assigned_staff.map((staff) => (
                                  <div key={staff.id} className="bg-green-50 rounded-lg p-4 border border-green-200">
                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                                      <div className="flex justify-between">
                                        <span className="text-gray-600">Contact Person:</span>
                                        <span className="font-medium text-green-700">{staff.staff_name}</span>
                                      </div>
                                      <div className="flex justify-between">
                                        <span className="text-gray-600">Role:</span>
                                        <span className="font-medium capitalize">{staff.role}</span>
                                      </div>
                                      <div className="flex justify-between">
                                        <span className="text-gray-600">Assignment Type:</span>
                                        <span className="font-medium capitalize">{staff.assignment_type.replace('_', ' ')}</span>
                                      </div>
                                      <div className="flex justify-between">
                                        <span className="text-gray-600">Assigned:</span>
                                        <span className="font-medium">
                                          {format(new Date(staff.assigned_at), 'MMM dd, yyyy HH:mm')}
                                        </span>
                                      </div>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {/* No Assigned Staff Message */}
                          {(!booking.assigned_staff || booking.assigned_staff.length === 0) && (
                            <div className="pt-4 border-t border-gray-100">
                              <h4 className="font-semibold text-gray-900 mb-3 flex items-center gap-2">
                                <svg className="w-4 h-4 text-orange-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                                </svg>
                                Contact Person Assignment
                              </h4>
                              <div className="bg-orange-50 rounded-lg p-4 border border-orange-200">
                                <div className="flex items-center gap-3">
                                  <svg className="w-5 h-5 text-orange-500 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                                  </svg>
                                  <div>
                                    <p className="text-sm font-medium text-orange-800">
                                      Contact person not assigned yet
                                    </p>
                                    <p className="text-sm text-orange-700 mt-1">
                                      A dedicated contact person will be assigned to your booking shortly.
                                    </p>
                                  </div>
                                </div>
                              </div>
                            </div>
                          )}

                          {/* Contact Information */}
                          {/* <div className="pt-4 border-t border-gray-100">
                            <h4 className="font-semibold text-gray-900 mb-3">Contact Information</h4>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                              <div className="flex justify-between">
                                <span className="text-gray-600">Email:</span>
                                <span className="font-medium">
                                  {booking.user_info?.email || user?.email || 'N/A'}
                                </span>
                              </div>
                              <div className="flex justify-between">
                                <span className="text-gray-600">Phone:</span>
                                <span className="font-medium">
                                  {booking.user_info?.phone || '+94 77 123 4567'}
                                </span>
                              </div>
                              {booking.user_info?.loyalty_tier && (
                                <div className="flex justify-between">
                                  <span className="text-gray-600">Loyalty Tier:</span>
                                  <span className="font-medium capitalize text-blue-600">
                                    {booking.user_info.loyalty_tier}
                                  </span>
                                </div>
                              )}
                            </div>
                          </div> */}

                          {/* Payment Information */}
                          <div className="pt-4 border-t border-gray-100">
                            <h4 className="font-semibold text-gray-900 mb-3">Payment Details</h4>
                            <div className="bg-gray-50 rounded-lg p-4">
                              <div className="flex justify-between items-center">
                                <span className="text-lg font-semibold text-gray-900">Total Amount:</span>
                                <span className="text-2xl font-bold text-blue-600">
                                  ${booking.total_amount?.toLocaleString()}
                                </span>
                              </div>
                              <div className="mt-2 text-sm text-gray-600">
                                Booking confirmed and payment needs to be completed.
                              </div>
                            </div>
                          </div>
                        </div>
                      )}

                      <div className="flex items-center justify-between pt-3 border-t border-gray-200">
                        <span className="text-2xl font-bold text-blue-600">
                          ${booking.total_amount?.toLocaleString()}
                        </span>
                        <button
                          onClick={() => setExpandedBooking(isExpanded ? null : booking.id)}
                          className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg font-medium transition-colors"
                        >
                          <EyeIcon className="w-4 h-4" />
                          {isExpanded ? 'Hide Details' : 'View Details'}
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
        </div>
      </div>
    </div>
  );
};

export default BookingsPage;
