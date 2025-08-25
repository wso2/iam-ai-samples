import React, { createContext, useContext, useState, ReactNode } from 'react';
import { format, addDays } from 'date-fns';
import { SearchParams } from '../types';
import { getSriLankaDate } from '../utils/dateUtils';

interface SearchContextType {
  searchParams: SearchParams;
  updateSearchParams: (params: Partial<SearchParams>) => void;
  resetSearchParams: () => void;
  setInitialDates: () => void;
}

const defaultSearchParams: SearchParams = {
  location: '',
  check_in: format(getSriLankaDate(), 'yyyy-MM-dd'),
  check_out: format(addDays(getSriLankaDate(), 1), 'yyyy-MM-dd'),
  guests: 2,
  rooms: 1
};

const SearchContext = createContext<SearchContextType | undefined>(undefined);

interface SearchProviderProps {
  children: ReactNode;
}

export const SearchProvider: React.FC<SearchProviderProps> = ({ children }) => {
  const [searchParams, setSearchParams] = useState<SearchParams>(defaultSearchParams);

  const updateSearchParams = (params: Partial<SearchParams>) => {
    setSearchParams(prev => ({ ...prev, ...params }));
  };

  const resetSearchParams = () => {
    setSearchParams(defaultSearchParams);
  };

  const setInitialDates = () => {
    const today = getSriLankaDate();
    const tomorrow = addDays(today, 1);
    
    setSearchParams(prev => ({
      ...prev,
      check_in: format(today, 'yyyy-MM-dd'),
      check_out: format(tomorrow, 'yyyy-MM-dd')
    }));
  };

  return (
    <SearchContext.Provider 
      value={{ 
        searchParams, 
        updateSearchParams, 
        resetSearchParams,
        setInitialDates
      }}
    >
      {children}
    </SearchContext.Provider>
  );
};

export const useSearch = (): SearchContextType => {
  const context = useContext(SearchContext);
  if (!context) {
    throw new Error('useSearch must be used within a SearchProvider');
  }
  return context;
};

export default SearchContext;
