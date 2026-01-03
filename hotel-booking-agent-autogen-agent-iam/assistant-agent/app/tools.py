"""
 Copyright (c) 2025, WSO2 LLC. (http://www.wso2.com). All Rights Reserved.

  This software is the property of WSO2 LLC. and its suppliers, if any.
  Dissemination of any information or reproduction of any material contained
  herein is strictly forbidden, unless permitted by WSO2 in accordance with
  the WSO2 Commercial License available at http://wso2.com/licenses.
  For specific language governing the permissions and limitations under
  this license, please see the license as well as any agreement you've
  entered into with WSO2 governing the purchase of this software and any
"""

import os
import logging
import traceback

import httpx
from dotenv import load_dotenv

from asgardeo.models import OAuthToken

# Configure logging for this module
logger = logging.getLogger(__name__)

load_dotenv()

hotel_api_base_url = os.environ.get('HOTEL_API_BASE_URL')
logger.info(f"[tools.py] Hotel API Base URL configured as: {hotel_api_base_url}")


async def _get(base_url: str, path: str, bearer_token: str, params: dict = None) -> dict:
    headers = {
        "Accept": "application/json"
    }
    
    # Only add Authorization header if token is provided and not empty
    if bearer_token and bearer_token.strip():
        headers["Authorization"] = f"Bearer {bearer_token}"
        logger.debug(f"[_get] Authorization header added (token length: {len(bearer_token)})")
    else:
        logger.debug("[_get] No bearer token provided, making unauthenticated request")

    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    logger.info(f"[_get] Making GET request to: {url}")
    logger.debug(f"[_get] Request params: {params}")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers, params=params)
            logger.info(f"[_get] Response status: {response.status_code} for URL: {url}")
            
            if response.status_code >= 400:
                logger.error(f"[_get] HTTP error {response.status_code}: {response.text[:500]}")
            
            response.raise_for_status()
            return response.json()
    except httpx.ConnectError as e:
        logger.error(f"[_get] Connection error to {url}: {str(e)}")
        logger.error(f"[_get] This usually means the backend service is not running or unreachable")
        logger.error(f"[_get] Base URL: {base_url}, Path: {path}")
        logger.error(f"[_get] Full traceback:\n{traceback.format_exc()}")
        raise
    except httpx.TimeoutException as e:
        logger.error(f"[_get] Timeout error for {url}: {str(e)}")
        logger.error(f"[_get] Full traceback:\n{traceback.format_exc()}")
        raise
    except httpx.HTTPStatusError as e:
        logger.error(f"[_get] HTTP status error for {url}: {e.response.status_code}")
        logger.error(f"[_get] Response body: {e.response.text[:1000]}")
        logger.error(f"[_get] Full traceback:\n{traceback.format_exc()}")
        raise
    except Exception as e:
        logger.error(f"[_get] Unexpected error for {url}: {type(e).__name__}: {str(e)}")
        logger.error(f"[_get] Full traceback:\n{traceback.format_exc()}")
        raise


async def _post(base_url: str, path: str, bearer_token: str, data: dict = None, params: dict = None) -> dict:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    # Only add Authorization header if token is provided and not empty
    if bearer_token and bearer_token.strip():
        headers["Authorization"] = f"Bearer {bearer_token}"
        logger.debug(f"[_post] Authorization header added (token length: {len(bearer_token)})")
    else:
        logger.debug("[_post] No bearer token provided, making unauthenticated request")

    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    logger.info(f"[_post] Making POST request to: {url}")
    logger.debug(f"[_post] Request data: {data}")
    logger.debug(f"[_post] Request params: {params}")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=data, params=params)
            logger.info(f"[_post] Response status: {response.status_code} for URL: {url}")
            
            if response.status_code >= 400:
                logger.error(f"[_post] HTTP error {response.status_code}: {response.text[:500]}")
            
            response.raise_for_status()
            return response.json()
    except httpx.ConnectError as e:
        logger.error(f"[_post] Connection error to {url}: {str(e)}")
        logger.error(f"[_post] This usually means the backend service is not running or unreachable")
        logger.error(f"[_post] Base URL: {base_url}, Path: {path}")
        logger.error(f"[_post] Full traceback:\n{traceback.format_exc()}")
        raise
    except httpx.TimeoutException as e:
        logger.error(f"[_post] Timeout error for {url}: {str(e)}")
        logger.error(f"[_post] Full traceback:\n{traceback.format_exc()}")
        raise
    except httpx.HTTPStatusError as e:
        logger.error(f"[_post] HTTP status error for {url}: {e.response.status_code}")
        logger.error(f"[_post] Response body: {e.response.text[:1000]}")
        logger.error(f"[_post] Full traceback:\n{traceback.format_exc()}")
        raise
    except Exception as e:
        logger.error(f"[_post] Unexpected error for {url}: {type(e).__name__}: {str(e)}")
        logger.error(f"[_post] Full traceback:\n{traceback.format_exc()}")
        raise


async def _patch(base_url: str, path: str, bearer_token: str, data: dict = None, params: dict = None) -> dict:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    # Only add Authorization header if token is provided and not empty
    if bearer_token and bearer_token.strip():
        headers["Authorization"] = f"Bearer {bearer_token}"
        logger.debug(f"[_patch] Authorization header added (token length: {len(bearer_token)})")
    else:
        logger.debug("[_patch] No bearer token provided, making unauthenticated request")

    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    logger.info(f"[_patch] Making PATCH request to: {url}")
    logger.debug(f"[_patch] Request data: {data}")
    logger.debug(f"[_patch] Request params: {params}")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.patch(url, headers=headers, json=data, params=params)
            logger.info(f"[_patch] Response status: {response.status_code} for URL: {url}")
            
            if response.status_code >= 400:
                logger.error(f"[_patch] HTTP error {response.status_code}: {response.text[:500]}")
            
            response.raise_for_status()
            return response.json()
    except httpx.ConnectError as e:
        logger.error(f"[_patch] Connection error to {url}: {str(e)}")
        logger.error(f"[_patch] This usually means the backend service is not running or unreachable")
        logger.error(f"[_patch] Base URL: {base_url}, Path: {path}")
        logger.error(f"[_patch] Full traceback:\n{traceback.format_exc()}")
        raise
    except httpx.TimeoutException as e:
        logger.error(f"[_patch] Timeout error for {url}: {str(e)}")
        logger.error(f"[_patch] Full traceback:\n{traceback.format_exc()}")
        raise
    except httpx.HTTPStatusError as e:
        logger.error(f"[_patch] HTTP status error for {url}: {e.response.status_code}")
        logger.error(f"[_patch] Response body: {e.response.text[:1000]}")
        logger.error(f"[_patch] Full traceback:\n{traceback.format_exc()}")
        raise
    except Exception as e:
        logger.error(f"[_patch] Unexpected error for {url}: {type(e).__name__}: {str(e)}")
        logger.error(f"[_patch] Full traceback:\n{traceback.format_exc()}")
        raise


async def fetch_hotels(token: OAuthToken = None, city: str = None, brand: str = None, amenities: list = None, limit: int = 20, offset: int = 0) -> dict:

    path = "api/hotels"
    params = {}
    if city:
        params['city'] = city
    if brand:
        params['brand'] = brand
    if amenities:
        params['amenities'] = amenities
    if limit:
        params['limit'] = limit
    if offset:
        params['offset'] = offset
    bearer_token = token.access_token if token else ""
    return await _get(hotel_api_base_url, path, bearer_token, params)


async def fetch_hotel_details(hotel_id: int, token: OAuthToken = None) -> dict:

    path = f"api/hotels/{hotel_id}"
    bearer_token = token.access_token if token else ""
    return await _get(hotel_api_base_url, path, bearer_token)


async def make_booking(hotel_id: int, room_id: int, check_in: str, check_out: str, guests: int,
                       user_id: str = None, special_requests: list = None, token: OAuthToken = None) -> dict:
    path = "api/bookings"
    data = {
        "hotel_id": hotel_id,
        "room_id": room_id,
        "check_in": check_in,
        "check_out": check_out,
        "guests": guests
    }
    if user_id:
        data["user_id"] = user_id
    if special_requests:
        data["special_requests"] = special_requests
    
    return await _post(hotel_api_base_url, path, token.access_token, data)


# === HOTEL ENDPOINTS ===

async def search_hotels(location: str, check_in: str, check_out: str, guests: int = 1, 
                       rooms: int = 1, brand: str = None, amenities: list = None,
                       price_range: dict = None, token: OAuthToken = None) -> dict:
    path = "api/hotels/search"
    data = {
        "location": location,
        "check_in": check_in,
        "check_out": check_out,
        "guests": guests,
        "rooms": rooms
    }
    if brand:
        data["brand"] = brand
    if amenities:
        data["amenities"] = amenities
    if price_range:
        data["price_range"] = price_range
    
    # This is a public endpoint, but include token if available
    bearer_token = token.access_token if token else ""
    return await _post(hotel_api_base_url, path, bearer_token, data)


async def fetch_hotel_reviews(hotel_id: int, limit: int = 10, rating: float = None, token: OAuthToken = None) -> dict:
    path = f"api/hotels/{hotel_id}/reviews"
    params = {"limit": limit}
    if rating:
        params["rating"] = rating
    
    # This is a public endpoint, but include token if available
    bearer_token = token.access_token if token else ""
    return await _get(hotel_api_base_url, path, bearer_token, params)


# === BOOKING ENDPOINTS ===

async def get_booking(booking_id: int, token: OAuthToken = None) -> dict:
    path = f"api/bookings/{booking_id}"
    bearer_token = token.access_token if token else ""
    return await _get(hotel_api_base_url, path, bearer_token)


async def cancel_booking(booking_id: int, reason: str = None, token: OAuthToken = None) -> dict:
    path = f"api/bookings/{booking_id}/cancel"
    data = {}
    if reason:
        data["reason"] = reason
    return await _post(hotel_api_base_url, path, token.access_token, data)


# === REVIEW ENDPOINTS ===

async def fetch_reviews(hotel_id: int = None, rating: float = None, limit: int = 20, 
                       offset: int = 0, token: OAuthToken = None) -> dict:
    path = "api/reviews"
    params = {"limit": limit, "offset": offset}
    if hotel_id:
        params["hotel_id"] = hotel_id
    if rating:
        params["rating"] = rating
    
    # This is a public endpoint, but include token if available
    bearer_token = token.access_token if token else ""
    return await _get(hotel_api_base_url, path, bearer_token, params)


async def create_review(booking_id: int, hotel_id: int, review_type: str, rating: float,
                       title: str, comment: str, staff_id: int = None, aspects: dict = None,
                       would_recommend: bool = None, token: OAuthToken = None) -> dict:
    path = "api/reviews"
    data = {
        "booking_id": booking_id,
        "hotel_id": hotel_id,
        "review_type": review_type,
        "rating": rating,
        "title": title,
        "comment": comment
    }
    if staff_id:
        data["staff_id"] = staff_id
    if aspects:
        data["aspects"] = aspects
    if would_recommend is not None:
        data["would_recommend"] = would_recommend
    
    return await _post(hotel_api_base_url, path, token.access_token, data)


async def get_review(review_id: int, token: OAuthToken = None) -> dict:
    path = f"api/reviews/{review_id}"
    # This is a public endpoint, but include token if available
    bearer_token = token.access_token if token else ""
    return await _get(hotel_api_base_url, path, bearer_token)
