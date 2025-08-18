import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from "@asgardeo/auth-react";
import { AsgardeoAuthProvider } from './contexts/AsgardeoAuthContext';
import { SearchProvider } from './contexts/SearchContext';
import asgardeoConfig from './config/asgardeo';
import HomePage from './pages/HomePage';
import EnhancedHotelListPage from './pages/EnhancedHotelListPage';
import { EnhancedHotelDetailPage } from './pages/EnhancedHotelDetailPage';
import BookingsPage from './pages/BookingsPage';
import BookingConfirmationPage from './pages/BookingConfirmationPage';

const App: React.FC = () => {
  return (
    <AuthProvider config={asgardeoConfig}>
      <AsgardeoAuthProvider>
        <SearchProvider>
          <Router>
          <div className="App">
            <Routes>
              {/* Public Routes */}
              <Route path="/" element={<HomePage />} />
              <Route 
                path="/hotels" 
                element={<EnhancedHotelListPage />} 
              />
              <Route 
                path="/hotels/:id" 
                element={<EnhancedHotelDetailPage />} 
              />
              
              {/* Protected Routes */}
              <Route 
                path="/bookings" 
                element={
                    <BookingsPage />
                } 
              />
              <Route 
                path="/booking-confirmation" 
                element={
                    <BookingConfirmationPage />
                } 
              />
              
              {/* Catch all route */}
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </div>
          </Router>
        </SearchProvider>
      </AsgardeoAuthProvider>
    </AuthProvider>
  );
};

export default App;
