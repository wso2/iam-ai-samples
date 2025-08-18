// Updated types to match new API structure

// === Core API Types ===
export interface Address {
  street: string;
  city: string;
  state: string;
  country: string;
  postal_code: string;
}

export interface PriceRange {
  min: number;
  max: number;
}

export interface Hotel {
  id: number;
  name: string;
  brand: string;
  description: string;
  address: Address;
  rating: number;
  amenities: string[];
  images: string[];
  price_range: PriceRange;
  rooms?: Room[];
}

export interface Room {
  id: number;
  hotel_id: number;
  room_type: string;
  bed_type: string;
  max_occupancy: number;
  size_sqft: number;
  amenities: string[];
  images: string[];
  base_price: number;
}

export interface ReviewAspects {
  cleanliness?: number;
  service?: number;
  location?: number;
  value?: number;
  professionalism?: number;
  responsiveness?: number;
}

export interface Review {
  id: number;
  hotel_id: number;
  review_type: 'hotel' | 'staff';
  rating: number;
  title: string;
  comment: string;
  aspects: ReviewAspects;
  would_recommend: boolean;
  created_at: string;
  reviewer_name: string;
}

export interface StaffAssignment {
  id: number;
  booking_id: number;
  staff_id: number;
  staff_name: string;
  role: string;
  assignment_type: string;
  assigned_at: string;
  assigned_by: string;
  assignment_reason: string;
}

export interface UserInfo {
  id: string;
  email?: string;
  first_name?: string;
  last_name?: string;
  display_name?: string;
  phone?: string;
  loyalty_tier?: string;
  source: 'asgardeo_scim' | 'local_data';
}

export interface AgentInfo {
  id: string;
  display_name?: string;
  description?: string;
  ai_model?: string;
  owner?: string;
  email?: string;
  first_name?: string;
  last_name?: string;
  phone?: string;
  source: 'asgardeo_scim' | 'local_data';
}

export interface Booking {
  id: number;
  confirmation_number: string;
  user_id: string;
  hotel_id: number;
  hotel_name: string;
  room_id: number;
  room_type: string;
  check_in: string;
  check_out: string;
  guests: number;
  total_amount: number;
  status: 'confirmed' | 'cancelled' | 'completed';
  special_requests: string[];
  created_at: string;
  created_by: 'user' | 'agent';
  agent_id?: string;
  assigned_staff: StaffAssignment[];
  user_info?: UserInfo;
  agent_info?: AgentInfo;
}

// === API Response Types ===
export interface HotelsResponse {
  hotels: Hotel[];
  total: number;
}

export interface ReviewsResponse {
  reviews: Review[];
  total: number;
  summary?: {
    average_rating: number;
    total_reviews?: number;
    total_by_rating?: {
      "1": number;
      "2": number;
      "3": number;
      "4": number;
      "5": number;
    };
  };
}

export interface BookingsResponse {
  bookings: Booking[];
  total: number;
}

// === Search Types ===
export interface SearchParams {
  location: string;
  check_in: string;
  check_out: string;
  guests: number;
  rooms: number;
  brand?: string;
  amenities?: string[];
  price_range?: PriceRange;
}

export interface SearchResult extends Hotel {
  available_rooms: Array<Room & {
    available: boolean;
    price_per_night: number;
  }>;
  lowest_rate: number;
}

export interface SearchResponse {
  hotels: SearchResult[];
  search_id: string;
}

// === Request Types ===
export interface BookingCreate {
  user_id?: string;
  hotel_id: number;
  room_id: number;
  check_in: string;
  check_out: string;
  guests: number;
  special_requests?: string[];
}

export interface ReviewCreate {
  booking_id: number;
  review_type: 'hotel' | 'staff';
  hotel_id: number;
  staff_id?: number;
  rating: number;
  title: string;
  comment: string;
  aspects?: ReviewAspects;
  would_recommend: boolean;
}

// === Legacy Types for Compatibility ===
export interface HotelBasic {
  id: number;
  name: string;
  description: string;
  location: string;
  rating: number;
  roomTypes: string[];
}

export interface Hotels {
  hotels: HotelBasic[];
}

export interface RoomBasic {
  id: number;
  room_number: string;
  room_type: string;
  price_per_night: number;
  occupancy: number;
  is_available: boolean;
  amenities?: string[];
  cancellationPolicy?: string;
}

// === UI Types ===
export interface SearchFilters {
  location?: string;
  priceRange?: [number, number];
  rating?: number;
  roomType?: string;
  amenities?: string[];
}

export interface BookingPreferences {
  checkIn: string;
  checkOut: string;
  guests: number;
}

export interface BookingRequest extends BookingCreate {
  guestName?: string;
  guestEmail?: string;
  specialRequests?: string;
}

// === Auth Types (Asgardeo-compatible) ===
export interface User {
  sub: string;
  username?: string;
  email?: string;
  given_name?: string;
  family_name?: string;
  scopes?: string[];
}

export interface AuthContextType {
  isAuthenticated: boolean;
  isLoading: boolean;
  user: User | null;
  accessToken: string | null;
  signIn: () => Promise<void>;
  signOut: () => Promise<void>;
  hasScope: (scope: string) => boolean;
}

// === Component Props Types ===
export interface LoadingSpinnerProps {
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

export interface ErrorMessageProps {
  message: string;
  className?: string;
}

// === API Error Type ===
export interface APIError {
  message: string;
  status: number;
  details?: string;
}
