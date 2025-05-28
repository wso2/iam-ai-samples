"""
 Copyright (c) 2025, WSO2 LLC. (http://www.wso2.com). All Rights Reserved.

  This software is the property of WSO2 LLC. and its suppliers, if any.
  Dissemination of any information or reproduction of any material contained
  herein is strictly forbidden, unless permitted by WSO2 in accordance with
  the WSO2 Commercial License available at http://wso2.com/licenses.
  For specific language governing the permissions and limitations under
  this license, please see the license as well as any agreement you’ve
  entered into with WSO2 governing the purchase of this software and any
"""

import os

import httpx
from dotenv import load_dotenv

from sdk.auth import OAuthToken

load_dotenv()

hotel_api_base_url = os.environ.get('HOTEL_API_BASE_URL')


async def _get(base_url: str, path: str, bearer_token: str, params: dict = None) -> dict:
    headers = {
        "Authorization": f"Bearer {bearer_token}",
        "Accept": "application/json"
    }

    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()


async def fetch_hotels(token: OAuthToken) -> dict:
    print("**agent token to fetch hotels**", token.access_token)
    path = "api/hotels"
    return await _get(hotel_api_base_url, path, token.access_token)


async def fetch_rooms(hotel_id: int, token: OAuthToken) -> dict:
    path = f"api/hotels/{hotel_id}"
    return await _get(hotel_api_base_url, path, token.access_token)


async def make_booking(hotel_id: int, room_id: int, date_from: str, date_to: str,  # used for API
                       hotel_name: str, total_cost: str,  # used for confirmation
                       token: OAuthToken  # used for authorization
                       ):
    async with httpx.AsyncClient() as client:
        # Set the authorization header with the access token
        headers = {
            "Authorization": f"Bearer {token.access_token}",
            "Content-Type": "application/json"
        }

        # Prepare the booking data
        booking_data = {
            "hotel_id": hotel_id,
            "room_id": room_id,
            "check_in": date_from,
            "check_out": date_to
        }

        headers["X-JWT-Assertion"] = headers["Authorization"].split(" ")[1]
        
        # Make the POST request to the bookings endpoint
        response = await client.post(
            f"{hotel_api_base_url}/api/bookings",
            json=booking_data,
            headers=headers
        )

        # Raise an exception for HTTP errors
        response.raise_for_status()

        # Return the JSON response
        return response.json()
