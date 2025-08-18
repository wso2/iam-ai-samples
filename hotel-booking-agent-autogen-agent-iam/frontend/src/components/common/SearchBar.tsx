import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { MagnifyingGlassIcon, CalendarIcon, UserGroupIcon, MapPinIcon } from '@heroicons/react/24/outline';
import { format, addDays } from 'date-fns';
import { SearchParams } from '../../types';
import { hotelAPI } from '../../services/api';
import { useSearch } from '../../contexts/SearchContext';
import { getSriLankaDate } from '../../utils/dateUtils';

interface SearchBarProps {
  onSearch?: (searchParams: SearchParams) => void;
  className?: string;
  showDestination?: boolean;
  initialDestination?: string;
  variant?: 'home' | 'hotels'; // 'home' for homepage with yellow border, 'hotels' for hotel list page
  navigateToResults?: boolean; // Whether to navigate to results page or use callback
}

const SearchBar: React.FC<SearchBarProps> = ({ 
  onSearch, 
  className = '', 
  showDestination = true,
  initialDestination = '',
  variant = 'hotels',
  navigateToResults = false
}) => {
  const { searchParams, updateSearchParams } = useSearch();
  const [destination, setDestination] = useState(initialDestination || searchParams.location);
  const [checkIn, setCheckIn] = useState(searchParams.check_in);
  const [checkOut, setCheckOut] = useState(searchParams.check_out);
  const [guests, setGuests] = useState(searchParams.guests);
  const [rooms, setRooms] = useState(searchParams.rooms);
  const [isSearching, setIsSearching] = useState(false);
  const [isDestinationTouched, setIsDestinationTouched] = useState(false); // Track if user has interacted with destination
  const [isDatesTouched, setIsDatesTouched] = useState(false); // Track if user has modified dates
  const navigate = useNavigate();

  // Sync with SearchContext, but preserve user changes
  useEffect(() => {
    // Only sync destination if user hasn't touched it and no initial destination is provided
    if (!isDestinationTouched && !initialDestination) {
      setDestination(searchParams.location);
    }
    
    // Only sync dates if user hasn't manually changed them
    if (!isDatesTouched) {
      if (searchParams.check_in && searchParams.check_in !== checkIn) {
        setCheckIn(searchParams.check_in);
      }
      if (searchParams.check_out && searchParams.check_out !== checkOut) {
        setCheckOut(searchParams.check_out);
      }
    }
    
    // Always sync guests and rooms as these are less likely to cause conflicts
    if (searchParams.guests !== guests) {
      setGuests(searchParams.guests);
    }
    if (searchParams.rooms !== rooms) {
      setRooms(searchParams.rooms);
    }
  }, [searchParams.location, searchParams.check_in, searchParams.check_out, searchParams.guests, searchParams.rooms, isDestinationTouched, initialDestination, isDatesTouched, checkIn, checkOut, guests, rooms]);

  // Handle check-in date change and automatically update check-out date
  const handleCheckInChange = (newCheckInDate: string) => {
    setCheckIn(newCheckInDate);
    setIsDatesTouched(true); // Mark dates as touched by user
    
    // Automatically set check-out to the next day
    const checkInDate = new Date(newCheckInDate);
    const nextDay = addDays(checkInDate, 1);
    const newCheckOutDate = format(nextDay, 'yyyy-MM-dd');
    setCheckOut(newCheckOutDate);
  };

  // Handle check-out date change with validation
  const handleCheckOutChange = (newCheckOutDate: string) => {
    setIsDatesTouched(true); // Mark dates as touched by user
    
    // Ensure check-out is not before check-in
    if (new Date(newCheckOutDate) <= new Date(checkIn)) {
      const checkInDate = new Date(checkIn);
      const nextDay = addDays(checkInDate, 1);
      setCheckOut(format(nextDay, 'yyyy-MM-dd'));
    } else {
      setCheckOut(newCheckOutDate);
    }
  };

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (showDestination && !destination.trim()) {
      alert('Please enter a destination');
      return;
    }

    const searchData: SearchParams = {
      location: destination.trim(),
      check_in: checkIn,
      check_out: checkOut,
      guests,
      rooms
    };

    // Update global search context
    updateSearchParams(searchData);

    // Reset touched states after search so context can update fields again
    setIsDestinationTouched(false);
    setIsDatesTouched(false);

    if (navigateToResults) {
      // Home page behavior: call API and navigate
      setIsSearching(true);
      try {
        const response = await hotelAPI.searchHotels(searchData);
        const results = response.data;

        // Navigate to hotels page with search results in state
        navigate('/hotels', {
          state: {
            searchResults: results,
            searchParams: searchData,
            isSearchResults: true
          }
        });
      } catch (error) {
        console.error('Search failed:', error);
        alert('Search failed. Please try again.');
      } finally {
        setIsSearching(false);
      }
    } else {
      // Hotel list page behavior: use callback
      onSearch?.(searchData);
    }
  };

  const containerClass = variant === 'home' 
    ? `bg-yellow-400 p-1 rounded-lg shadow-lg ${className}`
    : `bg-white rounded-lg shadow-lg border border-gray-200 p-6 ${className}`;

  const innerClass = variant === 'home' 
    ? 'bg-white rounded-lg p-6'
    : '';

  return (
    <div className={containerClass}>
      <div className={innerClass}>
        <form onSubmit={handleSearch} className={`grid gap-4 items-end ${
          showDestination 
            ? 'grid-cols-1 md:grid-cols-5' 
            : 'grid-cols-1 md:grid-cols-4'
        }`}>
        
        {/* Destination */}
        {showDestination && (
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Destination
            </label>
            <div className="relative">
              <MapPinIcon className="absolute left-3 top-3 w-4 h-4 text-gray-400" />
              <input
                type="text"
                placeholder="Where are you going?"
                value={destination}
                onChange={(e) => {
                  setDestination(e.target.value);
                  setIsDestinationTouched(true); // Mark as touched when user types
                }}
                onFocus={() => setIsDestinationTouched(true)} // Mark as touched when user focuses
                className="w-full pl-10 pr-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                required
              />
            </div>
          </div>
        )}

        {/* Check-in */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Check-in
          </label>
          <div className="relative">
            <CalendarIcon className="absolute left-3 top-3 w-4 h-4 text-gray-400" />
            <input
              type="date"
              value={checkIn}
              onChange={(e) => handleCheckInChange(e.target.value)}
              min={format(getSriLankaDate(), 'yyyy-MM-dd')}
              className="w-full pl-10 pr-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              required
            />
          </div>
        </div>

        {/* Check-out */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Check-out
          </label>
          <div className="relative">
            <CalendarIcon className="absolute left-3 top-3 w-4 h-4 text-gray-400" />
            <input
              type="date"
              value={checkOut}
              onChange={(e) => handleCheckOutChange(e.target.value)}
              min={checkIn}
              className="w-full pl-10 pr-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              required
            />
          </div>
        </div>

        {/* Guests & Rooms */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Guests & Rooms
          </label>
          <div className="relative">
            <UserGroupIcon className="absolute left-3 top-3 w-4 h-4 text-gray-400" />
            <select
              value={`${guests}-${rooms}`}
              onChange={(e) => {
                const [g, r] = e.target.value.split('-').map(Number);
                setGuests(g);
                setRooms(r);
              }}
              className="w-full pl-10 pr-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              <option value="1-1">1 Guest • 1 Room</option>
              <option value="2-1">2 Guests • 1 Room</option>
              <option value="3-1">3 Guests • 1 Room</option>
              <option value="4-1">4 Guests • 1 Room</option>
              <option value="2-2">2 Guests • 2 Rooms</option>
              <option value="4-2">4 Guests • 2 Rooms</option>
              <option value="6-2">6 Guests • 2 Rooms</option>
            </select>
          </div>
        </div>

        {/* Search Button */}
        <button
          type="submit"
          disabled={isSearching}
          className="bg-blue-600 hover:bg-blue-700 text-white py-2 px-6 rounded-lg font-medium transition-colors flex items-center justify-center gap-2 h-11 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <MagnifyingGlassIcon className="w-4 h-4" />
          {isSearching ? 'Searching...' : 'Search'}
        </button>
        </form>
      </div>
    </div>
  );
};

export default SearchBar;
