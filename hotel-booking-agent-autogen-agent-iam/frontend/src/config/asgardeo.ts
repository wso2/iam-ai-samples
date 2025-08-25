import { AuthReactConfig } from "@asgardeo/auth-react";

const asgardeoConfig: AuthReactConfig = {
    signInRedirectURL: process.env.REACT_APP_ASGARDEO_SIGN_IN_REDIRECT_URL || "http://localhost:3000",
    signOutRedirectURL: process.env.REACT_APP_ASGARDEO_SIGN_OUT_REDIRECT_URL || "http://localhost:3000",
    clientID: process.env.REACT_APP_ASGARDEO_CLIENT_ID || "",
    clientSecret: process.env.REACT_APP_ASGARDEO_CLIENT_SECRET || "",
    baseUrl: process.env.REACT_APP_ASGARDEO_BASE_URL || "",
    scope: ["openid", "profile", "read_hotels", "read_rooms", "create_bookings", "read_bookings"],
    resourceServerURLs: [
        process.env.REACT_APP_API_BASE_URL || "http://localhost:8001/api"
    ],
    enablePKCE: true,
    enableOIDCSessionManagement: true,
    storage: "sessionStorage",
    disableTrySignInSilently: true
};

export default asgardeoConfig;
