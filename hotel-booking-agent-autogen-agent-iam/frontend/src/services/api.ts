import axios, { AxiosResponse, InternalAxiosRequestConfig } from 'axios';
import {
  HotelsResponse,
  Hotel,
  Booking,
  BookingCreate,
  SearchParams,
  SearchResponse,
  ReviewsResponse,
  BookingsResponse
} from '../types';

// Create axios instance with base configuration
const api = axios.create({
  baseURL: process.env.REACT_APP_API_BASE_URL,
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Function to get access token from Asgardeo SDK
let getAccessTokenFunction: (() => Promise<string>) | null = null;

export const setAccessTokenFunction = (fn: () => Promise<string>) => {
  getAccessTokenFunction = fn;
};

// List of public endpoints that don't require authentication
const publicEndpoints = [
  '/hotels',
  '/hotels/search',
  '/reviews'
];

const isPublicEndpoint = (url: string): boolean => {
  // More comprehensive check for public endpoints
  if (!url) return false;
  
  console.log('Checking if endpoint is public:', url);
  
  // Check if URL contains any of the public endpoints
  const isPublic = publicEndpoints.some(endpoint => url.includes(endpoint)) || 
         /\/hotels\/\d+$/.test(url) || // /hotels/{id}
         /\/hotels\/\d+\/reviews/.test(url) || // /hotels/{id}/reviews
         /\/reviews\/\d+$/.test(url) || // /reviews/{id}
         /\/staff\/\d+\/reviews/.test(url) || // /staff/{id}/reviews
         url.startsWith('/hotels') || // Any hotel-related endpoint
         url.startsWith('/reviews'); // Any review-related endpoint
  
  console.log('Is public endpoint?', isPublic, 'for URL:', url);
  return isPublic;
};

// Request interceptor to add access token (only for protected endpoints)
api.interceptors.request.use(
  async (config: InternalAxiosRequestConfig) => {
    console.log('API Request interceptor called for:', config.url);
    
    // Skip auth for public endpoints
    if (config.url && isPublicEndpoint(config.url)) {
      console.log('Public endpoint, skipping auth:', config.url);
      return config;
    }
    
    if (getAccessTokenFunction) {
      try {
        const token = await getAccessTokenFunction();
        console.log('Retrieved access token:', token ? 'Token exists' : 'No token');
        
        if (token) {
          config.headers.Authorization = `Bearer ${token}`;
          console.log('Added Authorization header:', config.headers.Authorization?.substring(0, 20) + '...');
        }
      } catch (error) {
        console.error('Failed to get access token:', error);
      }
    } else {
      console.log('No access token function available');
    }
    
    console.log('Final request headers:', config.headers);
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor for error handling
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Handle unauthorized errors
      console.error('Unauthorized access:', error);
    }
    return Promise.reject(error);
  }
);

// API methods
export const hotelAPI = {
  // Get all hotels (PUBLIC)
  getHotels: (params?: {
    city?: string;
    brand?: string;
    amenities?: string[];
    limit?: number;
    offset?: number;
  }): Promise<AxiosResponse<HotelsResponse>> => {
    const searchParams = new URLSearchParams();
    
    if (params?.city) searchParams.append('city', params.city);
    if (params?.brand) searchParams.append('brand', params.brand);
    if (params?.amenities) {
      params.amenities.forEach(amenity => searchParams.append('amenities', amenity));
    }
    if (params?.limit) searchParams.append('limit', params.limit.toString());
    if (params?.offset) searchParams.append('offset', params.offset.toString());
    
    return api.get(`/hotels?${searchParams}`);
  },

  // Search hotels with availability (PUBLIC)
  searchHotels: (searchParams: SearchParams): Promise<AxiosResponse<SearchResponse>> =>
    api.post('/hotels/search', searchParams),

  // Get hotel by ID (PUBLIC)
  getHotel: (hotelId: number): Promise<AxiosResponse<Hotel>> => 
    api.get(`/hotels/${hotelId}`),

  // Get hotel reviews (PUBLIC)
  getHotelReviews: (hotelId: number, params?: {
    limit?: number;
    rating?: number;
  }): Promise<AxiosResponse<ReviewsResponse>> => {
    const searchParams = new URLSearchParams();
    if (params?.limit) searchParams.append('limit', params.limit.toString());
    if (params?.rating) searchParams.append('rating', params.rating.toString());
    
    return api.get(`/hotels/${hotelId}/reviews?${searchParams}`);
  },

  // Create booking (PROTECTED)
  createBooking: (bookingData: BookingCreate): Promise<AxiosResponse<Booking>> => 
    api.post('/bookings', bookingData),

  // Get booking details (PROTECTED)
  getBooking: (bookingId: number): Promise<AxiosResponse<Booking>> => 
    api.get(`/bookings/${bookingId}`),

  // Cancel booking (PROTECTED)
  cancelBooking: (bookingId: number, reason?: string): Promise<AxiosResponse<Booking>> =>
    api.post(`/bookings/${bookingId}/cancel`, { reason }),

  // Get user bookings (PROTECTED)
  getUserBookings: (userId: string, params?: {
    status?: 'confirmed' | 'cancelled' | 'completed';
    limit?: number;
  }): Promise<AxiosResponse<BookingsResponse>> => {
    const searchParams = new URLSearchParams();
    if (params?.status) searchParams.append('status', params.status);
    if (params?.limit) searchParams.append('limit', params.limit.toString());
    
    return api.get(`/users/${userId}/bookings?${searchParams}`);
  },

  // Get specific user booking (PROTECTED)
  getUserBooking: (userId: string, bookingId: number): Promise<AxiosResponse<Booking>> =>
    api.get(`/users/${userId}/bookings/${bookingId}`),
};

export const reviewAPI = {
  // Get all reviews (PUBLIC)
  getReviews: (params?: {
    hotel_id?: number;
    rating?: number;
    limit?: number;
    offset?: number;
  }): Promise<AxiosResponse<ReviewsResponse>> => {
    const searchParams = new URLSearchParams();
    
    if (params?.hotel_id) searchParams.append('hotel_id', params.hotel_id.toString());
    if (params?.rating) searchParams.append('rating', params.rating.toString());
    if (params?.limit) searchParams.append('limit', params.limit.toString());
    if (params?.offset) searchParams.append('offset', params.offset.toString());
    
    return api.get(`/reviews?${searchParams}`);
  },

  // Get review by ID (PUBLIC)
  getReview: (reviewId: number): Promise<AxiosResponse<any>> =>
    api.get(`/reviews/${reviewId}`),

  // Get staff reviews (PUBLIC)
  getStaffReviews: (staffId: number, params?: {
    limit?: number;
    rating?: number;
  }): Promise<AxiosResponse<any>> => {
    const searchParams = new URLSearchParams();
    if (params?.limit) searchParams.append('limit', params.limit.toString());
    if (params?.rating) searchParams.append('rating', params.rating.toString());
    
    return api.get(`/staff/${staffId}/reviews?${searchParams}`);
  },

  // Create review (PROTECTED)
  createReview: (reviewData: any): Promise<AxiosResponse<any>> =>
    api.post('/reviews', reviewData),

  // Create user booking review (PROTECTED)
  createUserBookingReview: (userId: string, bookingId: number, reviewData: any): Promise<AxiosResponse<any>> =>
    api.post(`/users/${userId}/bookings/${bookingId}/reviews`, reviewData),
};

export default api;
