import React from 'react';
import { EnhancedHeader } from '../components/layout/EnhancedHeader';
import { HeroSection } from '../components/common/HeroSection';
import SearchBar from '../components/common/SearchBar';
import ChatComponent from '../components/common/ChatComponent';

const HomePage: React.FC = () => {
  return (
    <div className="min-h-screen bg-white">
      <EnhancedHeader />
      <HeroSection />
      <div className="container mx-auto px-4 py-8 -mt-16">
        <SearchBar 
          variant="home"
          navigateToResults={true}
          className="relative z-10 max-w-6xl mx-auto"
        />
        
        {/* Weekend Deals Section - matching Gardeo Hotel style */}
        <div className="mt-12">
          <h2 className="text-2xl font-bold text-center mb-8">Weekend Deals</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="bg-white border border-gray-200 rounded-lg overflow-hidden hover:shadow-lg transition-shadow">
              <img 
                src="https://images.unsplash.com/photo-1566073771259-6a8506099945?ixlib=rb-4.0.3&auto=format&fit=crop&w=400&h=250"
                alt="Gardeo Saman Villa"
                className="w-full h-48 object-cover"
              />
              <div className="p-4">
                <h3 className="font-bold text-lg mb-2">Gardeo Saman Villa</h3>
                <p className="text-gray-600 text-sm mb-2">Bentota, Sri Lanka</p>
                <div className="flex items-center justify-between">
                  <div className="flex items-center">
                    <span className="bg-blue-600 text-white px-2 py-1 rounded text-sm font-bold mr-2">4.5</span>
                    <span className="text-sm text-gray-600">Excellent</span>
                  </div>
                  <div className="text-right">
                    <span className="text-lg font-bold">$200</span>
                    <p className="text-sm text-gray-600">per night</p>
                  </div>
                </div>
              </div>
            </div>

            <div className="bg-white border border-gray-200 rounded-lg overflow-hidden hover:shadow-lg transition-shadow">
              <img 
                src="https://images.unsplash.com/photo-1578683010236-d716f9a3f461?ixlib=rb-4.0.3&auto=format&fit=crop&w=400&h=250"
                alt="Gardeo Colombo Seven"
                className="w-full h-48 object-cover"
              />
              <div className="p-4">
                <h3 className="font-bold text-lg mb-2">Gardeo Colombo Seven</h3>
                <p className="text-gray-600 text-sm mb-2">Colombo, Sri Lanka</p>
                <div className="flex items-center justify-between">
                  <div className="flex items-center">
                    <span className="bg-blue-600 text-white px-2 py-1 rounded text-sm font-bold mr-2">4.9</span>
                    <span className="text-sm text-gray-600">Outstanding</span>
                  </div>
                  <div className="text-right">
                    <span className="text-lg font-bold">$200</span>
                    <p className="text-sm text-gray-600">per night</p>
                  </div>
                </div>
              </div>
            </div>

            <div className="bg-white border border-gray-200 rounded-lg overflow-hidden hover:shadow-lg transition-shadow">
              <img 
                src="https://images.unsplash.com/photo-1571003123894-1f0594d2b5d9?ixlib=rb-4.0.3&auto=format&fit=crop&w=400&h=250"
                alt="Gardeo Kandy Hills"
                className="w-full h-48 object-cover"
              />
              <div className="p-4">
                <h3 className="font-bold text-lg mb-2">Gardeo Kandy Hills</h3>
                <p className="text-gray-600 text-sm mb-2">Kandy, Sri Lanka</p>
                <div className="flex items-center justify-between">
                  <div className="flex items-center">
                    <span className="bg-blue-600 text-white px-2 py-1 rounded text-sm font-bold mr-2">4.7</span>
                    <span className="text-sm text-gray-600">Excellent</span>
                  </div>
                  <div className="text-right">
                    <span className="text-lg font-bold">$200</span>
                    <p className="text-sm text-gray-600">per night</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Unique Properties Section */}
        <div className="mt-12">
          <h2 className="text-2xl font-bold text-center mb-8">Unique Properties</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            <div className="text-center">
              <div className="w-16 h-16 bg-blue-100 rounded-full flex items-center justify-center mx-auto mb-4">
                <span className="text-2xl">🏖️</span>
              </div>
              <h3 className="font-semibold mb-2">Beachfront Luxury</h3>
              <p className="text-sm text-gray-600">Experience pristine beaches with world-class amenities</p>
            </div>
            
            <div className="text-center">
              <div className="w-16 h-16 bg-blue-100 rounded-full flex items-center justify-center mx-auto mb-4">
                <span className="text-2xl">🏛️</span>
              </div>
              <h3 className="font-semibold mb-2">Cultural Heritage</h3>
              <p className="text-sm text-gray-600">Stay near ancient temples and historical sites</p>
            </div>
            
            <div className="text-center">
              <div className="w-16 h-16 bg-blue-100 rounded-full flex items-center justify-center mx-auto mb-4">
                <span className="text-2xl">🏔️</span>
              </div>
              <h3 className="font-semibold mb-2">Mountain Retreats</h3>
              <p className="text-sm text-gray-600">Escape to serene hill country with stunning views</p>
            </div>
            
            <div className="text-center">
              <div className="w-16 h-16 bg-blue-100 rounded-full flex items-center justify-center mx-auto mb-4">
                <span className="text-2xl">🏙️</span>
              </div>
              <h3 className="font-semibold mb-2">Urban Sophistication</h3>
              <p className="text-sm text-gray-600">Modern luxury in the heart of vibrant cities</p>
            </div>
          </div>
        </div>
      </div>
      
      <ChatComponent />
    </div>
  );
};

export default HomePage;
