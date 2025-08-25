import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AsgardeoAuthContext';
import { hotelAPI } from '../services/api';
import { Hotel, BookingPreferences, SearchParams } from '../types';
import EnhancedHotelCard from '../components/hotels/EnhancedHotelCard';
import SearchBar from '../components/common/SearchBar';
import LoadingSpinner from '../components/common/LoadingSpinner';
import ErrorMessage from '../components/common/ErrorMessage';
import { EnhancedHeader } from '../components/layout/EnhancedHeader';
import { useSearch } from '../contexts/SearchContext';
import { 
  FunnelIcon, 
  Squares2X2Icon, 
  ListBulletIcon,
  MapIcon
} from '@heroicons/react/24/outline';

const EnhancedHotelListPage: React.FC = () => {
  useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const { searchParams: contextSearchParams, updateSearchParams } = useSearch();
  const [hotels, setHotels] = useState<Hotel[]>([]);
  const [filteredHotels, setFilteredHotels] = useState<Hotel[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchPreferences, setSearchPreferences] = useState<BookingPreferences | null>(null);
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid');
  const [sortBy, setSortBy] = useState<'rating' | 'name' | 'location'>('rating');
  const [filterByLocation, setFilterByLocation] = useState<string>('all');
  const [isSearchResults, setIsSearchResults] = useState(false);
  const [searchParams, setSearchParams] = useState<SearchParams | null>(null);

  // Hotel listing is now public - no authentication required

  useEffect(() => {
    const checkForSearchResults = () => {
      // Check if we have search results from navigation state
      const navigationState = location.state as any;
      
      if (navigationState?.searchResults && navigationState?.searchParams) {
        // We have search results from navigation, use them
        const searchResults = navigationState.searchResults;
        const searchParams = navigationState.searchParams;
        
        setHotels(searchResults.hotels || []);
        setFilteredHotels(searchResults.hotels || []);
        setSearchParams(searchParams);
        setIsSearchResults(true);
        setLoading(false);
      } else {
        // No search results, fetch all hotels
        fetchAllHotels();
      }
    };

    const fetchAllHotels = async () => {
      try {
        setLoading(true);
        setError(null);
        console.log('Fetching all hotels...');
        const response = await hotelAPI.getHotels();
        console.log('Hotels response:', response);
        setHotels(response.data.hotels);
        setFilteredHotels(response.data.hotels);
        setIsSearchResults(false);
        setSearchParams(null);
      } catch (err: any) {
        console.error('Hotel fetch error:', err);
        setError(err.response?.data?.detail || 'Failed to load hotels');
      } finally {
        setLoading(false);
      }
    };

    checkForSearchResults();
  }, [location.state]); // Re-run when navigation state changes

  useEffect(() => {
    let filtered = [...hotels];

    // Filter by location
    if (filterByLocation !== 'all') {
      filtered = filtered.filter(hotel => 
        hotel.address.city.toLowerCase().includes(filterByLocation.toLowerCase())
      );
    }

    // Sort hotels
    filtered.sort((a, b) => {
      switch (sortBy) {
        case 'rating':
          return b.rating - a.rating;
        case 'name':
          return a.name.localeCompare(b.name);
        case 'location':
          return a.address.city.localeCompare(b.address.city);
        default:
          return 0;
      }
    });

    setFilteredHotels(filtered);
  }, [hotels, sortBy, filterByLocation]);

  const handleSearch = async (searchData: SearchParams) => {
    setLoading(true);
    setError(null);
    
    try {
      console.log('Performing hotel search with params:', searchData);
      const response = await hotelAPI.searchHotels(searchData);
      const results = response.data;
      
      console.log('Search results:', results);
      
      // Update state with search results
      setHotels(results.hotels || []);
      setFilteredHotels(results.hotels || []);
      setSearchParams(searchData);
      setIsSearchResults(true);
      
      // Update context with search data
      updateSearchParams(searchData);
      
    } catch (err: any) {
      console.error('Search failed:', err);
      setError(err.response?.data?.detail || 'Search failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const uniqueLocations = Array.from(new Set(hotels.map(hotel => 
    hotel.address.city.trim()
  )));

  if (loading) {
    return (
      <div className="min-h-screen bg-white">
        <EnhancedHeader />
        <div className="container mx-auto px-4 py-8">
          <div className="flex justify-center items-center h-64">
            <LoadingSpinner size="lg" />
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
          <ErrorMessage message={error} />
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-white">
      <EnhancedHeader />
      
      {/* Hero Section - matching home page style but simplified */}
      <div className="relative bg-gradient-to-r from-blue-600 to-blue-800 text-white">
        <div className="relative py-16">
          <div className="container mx-auto px-4">
            {isSearchResults && searchParams ? (
              <div className="text-center">
                <h1 className="text-4xl md:text-5xl font-bold mb-4">
                  Search Results
                </h1>
                <div className="bg-white bg-opacity-90 text-gray-800 px-6 py-4 rounded-lg max-w-4xl mx-auto">
                  <p className="text-lg font-medium">
                    {filteredHotels.length} properties found in {searchParams.location} •{' '}
                    {new Date(searchParams.check_in).toLocaleDateString()} -{' '}
                    {new Date(searchParams.check_out).toLocaleDateString()} • {searchParams.guests} guest
                    {searchParams.guests > 1 ? 's' : ''} • {searchParams.rooms} room{searchParams.rooms > 1 ? 's' : ''}
                  </p>
                  <button
                    onClick={async () => {
                      setIsSearchResults(false);
                      setSearchParams(null);
                      setLoading(true);
                      try {
                        const response = await hotelAPI.getHotels();
                        setHotels(response.data.hotels);
                        setFilteredHotels(response.data.hotels);
                      } catch (err: any) {
                        console.error('Failed to reload hotels:', err);
                      } finally {
                        setLoading(false);
                      }
                    }}
                    className="mt-3 text-blue-600 hover:text-blue-800 font-medium"
                  >
                    ← Back to all hotels
                  </button>
                </div>
              </div>
            ) : (
              <div className="text-center">

              </div>
            )}
          </div>
        </div>
      </div>

      <div className="container mx-auto px-4 py-8">
        <div className="space-y-8">
          {/* Search Bar - always show but with different positioning */}
          <div className={`max-w-6xl mx-auto -mt-16 relative z-10`}>
            <SearchBar 
              onSearch={handleSearch} 
              showDestination={true}
              initialDestination={searchParams?.location || contextSearchParams.location}
              className="bg-white rounded-lg shadow-lg" 
            />
          </div>

          {/* Filters and Controls */}
          <div className="flex flex-col lg:flex-row gap-4 items-start lg:items-center justify-between bg-white border border-gray-200 rounded-lg p-4 shadow-sm">
            <div className="flex flex-wrap items-center gap-4">
              <h2 className="text-xl font-bold text-gray-900">
                {isSearchResults ? 'Refine Your Search' : 'Browse Hotels'}
              </h2>
              
              {/* Location Filter */}
              <div className="flex items-center gap-2">
                <MapIcon className="w-4 h-4 text-blue-600" />
                <select
                  value={filterByLocation}
                  onChange={(e) => setFilterByLocation(e.target.value)}
                  className="text-sm border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                >
                  <option value="all">All Locations</option>
                  {uniqueLocations.map(location => (
                    <option key={location} value={location}>{location}</option>
                  ))}
                </select>
              </div>

              {/* Sort Options */}
              <div className="flex items-center gap-2">
                <FunnelIcon className="w-4 h-4 text-blue-600" />
                <select
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value as 'rating' | 'name' | 'location')}
                  className="text-sm border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                >
                  <option value="rating">Sort by Rating</option>
                  <option value="name">Sort by Name</option>
                  <option value="location">Sort by Location</option>
                </select>
              </div>
            </div>

            {/* View Mode Toggle */}
            <div className="flex items-center gap-2">
              <button
                onClick={() => setViewMode('grid')}
                className={`p-2 rounded-lg transition-colors ${
                  viewMode === 'grid'
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
              >
                <Squares2X2Icon className="w-5 h-5" />
              </button>
              <button
                onClick={() => setViewMode('list')}
                className={`p-2 rounded-lg transition-colors ${
                  viewMode === 'list'
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
              >
                <ListBulletIcon className="w-5 h-5" />
              </button>
            </div>
          </div>

          {/* Results Count */}
          <div className="flex items-center justify-between">
            <span className="text-lg font-medium text-gray-600">
              {filteredHotels.length} hotel{filteredHotels.length !== 1 ? 's' : ''} found
            </span>
          </div>

          {/* Hotels Display */}
          {filteredHotels.length === 0 ? (
            <div className="text-center py-12">
              <div className="space-y-4">
                <MapIcon className="w-16 h-16 text-gray-300 mx-auto" />
                <div>
                  <h3 className="text-lg font-medium text-gray-900">
                    No hotels found
                  </h3>
                  <p className="text-gray-600">
                    Try adjusting your filters or search criteria
                  </p>
                </div>
                <button
                  onClick={() => {
                    setFilterByLocation('all');
                    setSortBy('rating');
                  }}
                  className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-2 rounded-lg font-medium transition-colors"
                >
                  Clear Filters
                </button>
              </div>
            </div>
          ) : (
            <div 
              className={
                viewMode === 'grid' 
                  ? 'grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6'
                  : 'space-y-6'
              }
            >
              {filteredHotels.map((hotel) => (
                <EnhancedHotelCard 
                  key={hotel.id} 
                  hotel={hotel} 
                  searchPreferences={
                    searchParams ? {
                      checkIn: searchParams.check_in,
                      checkOut: searchParams.check_out,
                      guests: searchParams.guests
                    } : (searchPreferences || undefined)
                  }
                />
              ))}
            </div>
          )}

          {/* Load More Button (for future pagination) */}
          {filteredHotels.length > 0 && (
            <div className="text-center pt-8">
              <p className="text-gray-600 text-sm">
                Showing all available hotels
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default EnhancedHotelListPage;
