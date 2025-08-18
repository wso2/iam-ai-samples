import React, { createContext, useContext, ReactNode, useEffect, useState, useCallback } from 'react';
import { useAuthContext, BasicUserInfo } from "@asgardeo/auth-react";
import { AuthContextType, User } from '../types';
import { setAccessTokenFunction } from '../services/api';

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AsgardeoAuthProvider');
  }
  return context;
};

interface AsgardeoAuthProviderProps {
  children: ReactNode;
}

export const AsgardeoAuthProvider: React.FC<AsgardeoAuthProviderProps> = ({ children }) => {
  const {
    state,
    signIn,
    signOut,
    getBasicUserInfo,
    getAccessToken,
    getDecodedIDToken
  } = useAuthContext();

  const [user, setUser] = useState<User | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);

  const getToken = useCallback((): Promise<string> => {
    console.log('getToken function called for API request');
    console.log('Current auth state:', {
      isAuthenticated: state.isAuthenticated,
      isLoading: state.isLoading
    });
    
    return getAccessToken()
      .then((accessToken) => {
        console.log('getToken: Retrieved token from Asgardeo SDK:', accessToken ? 'Token exists' : 'No token');
        
        if (accessToken) {
          console.log('getToken: Returning token for API request');
          return accessToken;
        } else {
          console.log('getToken: No token available, returning empty string');
          return '';
        }
      })
      .catch((error) => {
        console.error('getToken: Error getting access token:', error);
        return '';
      });
  }, [getAccessToken, state.isAuthenticated, state.isLoading]);

  // Set up the access token function for API calls
  useEffect(() => {
    console.log('Setting access token function in auth context');
    setAccessTokenFunction(getToken);
  }, [getToken]);

  useEffect(() => {
    if (state.isAuthenticated) {
      console.log('User authenticated, fetching user data...');
      
      // Get basic user info
      getBasicUserInfo()
        .then((basicUserInfo: BasicUserInfo) => {
          console.log('Basic user info retrieved:', basicUserInfo);
          
          // Get access token using the correct pattern
          getAccessToken()
            .then((accessToken) => {
              console.log('Access token retrieved successfully:', accessToken ? 'Token exists' : 'No token');
              
              if (accessToken) {
                console.log('Token preview:', accessToken.substring(0, 50) + '...');
                setAccessToken(accessToken);

                // Extract scopes from access token
                try {
                  const tokenPayload = JSON.parse(atob(accessToken.split('.')[1]));
                  const scopes = tokenPayload.scope ? tokenPayload.scope.split(' ') : [];
                  console.log('Token scopes:', scopes);

                  // Construct user object
                  const userData: User = {
                    sub: basicUserInfo.sub || '',
                    username: basicUserInfo.username,
                    email: basicUserInfo.email,
                    given_name: basicUserInfo.given_name,
                    family_name: basicUserInfo.family_name,
                    scopes: scopes
                  };

                  console.log('Final user data:', userData);
                  setUser(userData);
                } catch (e) {
                  console.error('Error parsing access token:', e);
                }
              } else {
                console.log('No access token available');
                setAccessToken(null);
              }
            })
            .catch((error) => {
              console.error('Error getting access token:', error);
              setAccessToken(null);
            });
        })
        .catch((error) => {
          console.error('Error getting basic user info:', error);
          setUser(null);
          setAccessToken(null);
        });
    } else {
      console.log('User not authenticated, clearing data');
      setUser(null);
      setAccessToken(null);
    }
  }, [state.isAuthenticated, getBasicUserInfo, getAccessToken]);

  const handleSignIn = async (): Promise<void> => {
    try {
      await signIn();
    } catch (error) {
      console.error('Sign in error:', error);
      throw error;
    }
  };

  const handleSignOut = async (): Promise<void> => {
    try {
      await signOut();
    } catch (error) {
      console.error('Sign out error:', error);
      throw error;
    }
  };

  const hasScope = (requiredScope: string): boolean => {
    return user?.scopes?.includes(requiredScope) || false;
  };

  const value: AuthContextType = {
    isAuthenticated: state.isAuthenticated,
    isLoading: state.isLoading,
    user,
    accessToken,
    signIn: handleSignIn,
    signOut: handleSignOut,
    hasScope,
  };

  console.log('Auth Context State:', {
    isAuthenticated: state.isAuthenticated,
    isLoading: state.isLoading,
    hasUser: !!user,
    hasAccessToken: !!accessToken
  });

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
};