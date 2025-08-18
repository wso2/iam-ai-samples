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

from asgardeo.models import OAuthToken

load_dotenv()

hotel_api_base_url = os.environ.get('HOTEL_API_BASE_URL')


async def _get(base_url: str, path: str, bearer_token: str, params: dict = None) -> dict:
    headers = {
        "Accept": "application/json"
    }
    
    # Only add Authorization header if token is provided and not empty
    if bearer_token and bearer_token.strip():
        headers["Authorization"] = f"Bearer {bearer_token}"

    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()

async def _patch(base_url: str, path: str, bearer_token: str, data: dict = None, params: dict = None) -> dict:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    # Only add Authorization header if token is provided and not empty
    if bearer_token and bearer_token.strip():
        headers["Authorization"] = f"Bearer {bearer_token}"

    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"

    async with httpx.AsyncClient() as client:
        response = await client.patch(url, headers=headers, json=data, params=params)
        response.raise_for_status()
        return response.json()
    
# === ADMIN ENDPOINTS ===

async def update_booking_admin(booking_id: int, contact_person_id: int, token: OAuthToken = None) -> dict:
    """
    Update booking to assign the contact person (admin endpoint).
    
    Args:
        booking_id: ID of the booking to update
        contact_person_id: Staff ID to assign as contact person
        token: OAuth token for authorization
    
    Returns:
        Updated the contact person of the booking
    """
    path = f"api/admin/bookings/{booking_id}"
    data = {}
    
    if contact_person_id is not None:
        data["contact_person_id"] = contact_person_id
    else:
        data["contact_person_id"] = None
        
    return await _patch(hotel_api_base_url, path, token.access_token, data)

async def get_available_staff(hotel_id: int = None, token: OAuthToken = None) -> dict:
    """
    Get available contact persons for assignment to bookings (admin endpoint).
    
    Args:
        hotel_id: Optional hotel ID to filter staff by specific hotel
        token: OAuth token for authorization
    
    Returns:
        List of available staff members who can be assigned as contact persons
    """
    path = "api/admin/staff/available"
    params = {}
    if hotel_id:
        params["hotel_id"] = hotel_id
    
    return await _get(hotel_api_base_url, path, token.access_token, params)

async def get_booking_admin(booking_id: str, token: OAuthToken = None) -> dict:
    """
    Get booking details by ID (admin endpoint).
    
    Args:
        booking_id: ID of the booking to retrieve
        token: OAuth token for authorization

    Returns:
        Booking details
    """
    path = f"api/admin/bookings/{booking_id}"
    return await _get(hotel_api_base_url, path, token.access_token)
