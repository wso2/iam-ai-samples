import React from 'react';

interface HeroSectionProps {
  className?: string;
}

export function HeroSection({ className = '' }: HeroSectionProps) {
  return (
    <div className={`relative bg-gradient-to-r from-blue-600 to-blue-800 text-white ${className}`}>
      <div className="absolute inset-0 bg-black opacity-40"></div>
      <div 
        className="relative bg-cover bg-center bg-no-repeat min-h-[500px] flex items-center"
        style={{
          backgroundImage: "url('https://images.unsplash.com/photo-1566073771259-6a8506099945?ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D&auto=format&fit=crop&w=2070&q=80')"
        }}
      >
        <div className="absolute inset-0 bg-black opacity-50"></div>
        <div className="relative container mx-auto px-4 text-center">
          <h1 className="text-4xl md:text-6xl font-bold mb-6 leading-tight">
            Discover Your Perfect Stay
          </h1>
          <p className="text-xl md:text-2xl mb-8 max-w-3xl mx-auto leading-relaxed">
            Experience luxury and comfort at Gardeo Hotels across Sri Lanka. 
            From pristine beaches to cultural heritage sites, find your ideal getaway.
          </p>
        </div>
      </div>
    </div>
  );
}
