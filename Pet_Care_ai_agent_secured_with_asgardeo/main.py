import os
from dotenv import load_dotenv
from pydantic import AnyHttpUrl
from datetime import datetime
from typing import Optional, Any
import openai

# Load environment variables from .env file
load_dotenv()

from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from jwt_validator import JWTValidator
import logging

# Import database functions
import database as db

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class JWTTokenVerifier(TokenVerifier):
    """JWT token verifier using Asgardeo JWKS."""
    
    def __init__(self, jwks_url: str, issuer: str, client_id: str):
        self.jwt_validator = JWTValidator(
            jwks_url=jwks_url,
            issuer=issuer,
            audience=client_id,
            ssl_verify=True  # Set to False for development if needed
        )
    
    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            # Validate the JWT token
            payload = await self.jwt_validator.validate_token(token)
            
            # Extract information from the validated token
            expires_at = payload.get("exp")
            scopes = payload.get("scope", "").split() if payload.get("scope") else []
            subject = payload.get("sub")
            audience = payload.get("aud")
            
            logger.info(f"Token validated successfully for subject: {subject}")
            
            return AccessToken(
                token=token,
                client_id=audience if isinstance(audience, str) else self.jwt_validator.audience,
                scopes=scopes,
                expires_at=str(expires_at) if expires_at else None
            )
        except ValueError as e:
            logger.warning(f"Token validation failed: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error during token validation: {e}")
            return None

AUTH_ISSUER = os.getenv("AUTH_ISSUER")
CLIENT_ID = os.getenv("CLIENT_ID")
JWKS_URL = os.getenv("JWKS_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Validate that required environment variables are set
if not all([AUTH_ISSUER, CLIENT_ID, JWKS_URL]):
    raise ValueError("Missing required environment variables: AUTH_ISSUER, CLIENT_ID, or JWKS_URL")

# Initialize OpenAI client
openai_client = openai.OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# Create FastMCP instance as a Resource Server
mcp = FastMCP(
    "Pet clinic MCP",
    # Token verifier for authentication
    token_verifier=JWTTokenVerifier(JWKS_URL, AUTH_ISSUER, CLIENT_ID),
    # Auth settings for RFC 9728 Protected Resource Metadata
    auth=AuthSettings(
        issuer_url=AnyHttpUrl(AUTH_ISSUER),
        resource_server_url=AnyHttpUrl("http://localhost:8000"),
        # required_scopes=["user"]
    ),
)

@mcp.tool()
async def get_user_id_by_email(email: str) -> dict[str, Any]:
    """Retrieves the unique User ID associated with a provided email address."""
    try:
        if not email or "@" not in email:
            raise ValueError("Invalid email format.")

        email_clean = email.lower().strip()
        
        # Query database for user
        user_record = db.get_user_by_email(email_clean)
        
        if user_record:
            return {
                "email": email_clean,
                "user_id": user_record["user_id"],
                "account_status": user_record["account_status"],
                "registered_since": user_record["registered_since"],
                "lookup_timestamp": datetime.now().isoformat()
            }
        else:
            # Fallback for unknown users
            import hashlib
            hash_object = hashlib.md5(email_clean.encode())
            user_id_suffix = hash_object.hexdigest()[:8].upper()
            return {
                "email": email_clean,
                "user_id": f"USER-{user_id_suffix}",
                "account_status": "guest",
                "source": "generated"
            }

    except Exception as error:
        logger.error(f"System error looking up user ID: {error}")
        raise ValueError(f"Failed to retrieve user ID: {str(error)}")

@mcp.tool()
async def get_pets_by_user_id(user_id: str) -> dict[str, Any]:
    """Retrieves a list of pet IDs and basic details owned by a specific user."""
    try:
        user_id = user_id.strip()
        
        # Find user by user_id
        user_record = db.get_user_by_user_id(user_id)
        
        if not user_record:
            raise ValueError(f"User with ID '{user_id}' not found.")
        
        target_email = user_record["email"]
        user_name = user_record.get("name")
        
        # Find pets owned by this user
        pets = db.get_pets_by_owner_email(target_email)
        
        found_pets = []
        for pet in pets:
            found_pets.append({
                "pet_id": pet["pet_id"],
                "pet_name": pet["pet_name"],
                "type": pet.get("type", "Unknown")
            })

        return {
            "user_id": user_id,
            "owner_name": user_name,
            "pet_count": len(found_pets),
            "pets": found_pets
        }

    except Exception as error:
        logger.error(f"System error retrieving pets: {error}")
        raise ValueError(f"Failed to retrieve pets: {str(error)}")
    
@mcp.tool()
async def get_pet_vaccination_info(pet_id: str) -> dict[str, Any]:
    """Retrieves the vaccination history for a specific pet."""
    try:
        # Get basic pet info
        pet_basic = db.get_pet_by_id(pet_id)
        if not pet_basic:
            raise ValueError(f"Pet with ID '{pet_id}' not found.")

        # Get vaccination records
        vaccination_history = db.get_vaccination_history(pet_id)
        upcoming_vaccinations = db.get_upcoming_vaccinations(pet_id)

        # Build response
        response = {
            "pet_id": pet_id,
            "pet_name": pet_basic["pet_name"],
            "vaccination_history": vaccination_history,
            "upcoming_vaccinations": upcoming_vaccinations,
            "last_updated": datetime.now().isoformat(),
            "token_status": "Token was present and validated"
        }
        
        return response
        
    except Exception as error:
        logger.error(f"Failed to retrieve vaccination information: {error}")
        raise ValueError(f"Failed to retrieve vaccination information: {str(error)}")
    

@mcp.tool()
async def book_vet_appointment(
    pet_id: str,
    date: str,
    time: str,
    reason: str
) -> dict[str, Any]:
    """
    Books a new veterinary appointment for a specific pet.
    Requires user authentication and explicit consent via an authorization token.
    
    Args:
        pet_id: The unique identifier for the pet
        date: Desired date for the appointment (e.g., YYYY-MM-DD)
        time: Desired time for the appointment (e.g., HH:MM AM/PM)
        reason: The reason for the vet visit
        
    Returns:
        Dictionary containing appointment confirmation details
    """
    try:
        # Validate pet exists
        pet = db.get_pet_by_id(pet_id)
        if not pet:
            raise ValueError(f"Pet with ID '{pet_id}' not found.")
        
        # Validate date format
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            raise ValueError("Invalid date format. Please use YYYY-MM-DD format.")
        
        # Generate appointment ID
        appointment_id = f"APT-{pet_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        # Create appointment in database
        appointment = db.create_appointment(
            appointment_id=appointment_id,
            pet_id=pet_id,
            date=date,
            time=time,
            reason=reason
        )
        
        appointment_details = {
            "appointment_id": appointment["appointment_id"],
            "pet_id": appointment["pet_id"],
            "date": appointment["date"],
            "time": appointment["time"],
            "reason": appointment["reason"],
            "status": appointment["status"],
            "veterinarian": appointment["veterinarian"],
            "clinic_name": appointment["clinic_name"],
            "clinic_address": appointment["clinic_address"],
            "confirmation_message": f"Appointment successfully booked for pet ID: {pet_id} on {date} at {time}",
            "reminder": "Please arrive 10 minutes early for check-in",
            "cancellation_policy": "Please cancel at least 24 hours in advance",
            "booked_at": appointment["booked_at"],
            "token_status": "Token was present and validated"
        }
        
        logger.info(
            f"Booked vet appointment for pet ID: {pet_id} on {date} at {time} for: {reason}"
        )
        
        return appointment_details
        
    except ValueError as ve:
        error_message = str(ve)
        logger.error(f"Validation error: {error_message}")
        raise ValueError(f"Failed to book appointment: {error_message}")
    except Exception as error:
        error_message = str(error)
        logger.error(f"Failed to book appointment: {error_message}")
        raise ValueError(f"Failed to book appointment: {error_message}")

@mcp.tool()
async def cancel_appointment(appointment_id: str, reason: str) -> dict[str, Any]:
    """
    Cancels an existing veterinary appointment.
    Requires user authentication and explicit consent via an authorization token.
    
    Args:
        appointment_id: The unique identifier for the appointment to be canceled
        reason: The reason for cancellation
    """
    try:
        # Cancel appointment in database
        canceled_appointment = db.cancel_appointment(appointment_id, reason)
        
        if not canceled_appointment:
            raise ValueError(f"Appointment with ID '{appointment_id}' not found.")
        
        cancellation_details = {
            "appointment_id": canceled_appointment["appointment_id"],
            "status": canceled_appointment["status"],
            "cancellation_reason": canceled_appointment["cancellation_reason"],
            "canceled_at": canceled_appointment["canceled_at"],
            "confirmation_message": f"Appointment {appointment_id} has been successfully canceled.",
            "refund_policy": "Refunds will be processed within 5-7 business days if applicable.",
        }
        
        logger.info(f"Canceled appointment ID: {appointment_id} for reason: {reason}")
        return cancellation_details
        
    except Exception as error:
        error_message = str(error)
        logger.error(f"Failed to cancel appointment: {error_message}")
        raise ValueError(f"Failed to cancel appointment: {error_message}")

@mcp.tool()
async def suggest_pet_names(
    category: str,
    gender: str,
    count: int = 5
) -> dict[str, Any]:
    """
    Generate creative and suitable pet name suggestions using OpenAI's GPT model.
    Requires user authentication and explicit consent via an authorization token.
    
    Args:
        category: Pet category (e.g., "dog", "cat", "bird", "rabbit", "hamster", "fish")
        gender: Pet gender ("male", "female", or "unisex")
        count: Number of name suggestions to generate (default: 5, max: 20)
        
    Returns:
        Dictionary containing AI-generated pet name suggestions with meanings
    """
    try:
        # Ensure OpenAI API key is set from environment if available
        if OPENAI_API_KEY and not openai.api_key:
            openai.api_key = OPENAI_API_KEY
        
        if not openai.api_key:
            raise ValueError("OpenAI API key is not configured. Please set OPENAI_API_KEY in environment variables.")
        
        category = category.lower().strip()
        gender = gender.lower().strip()
        count = min(max(count, 1), 20)
        
        valid_categories = ["dog", "cat", "bird", "rabbit", "hamster", "fish", "guinea pig", "ferret", "turtle", "lizard", "snake"]
        if category not in valid_categories:
            raise ValueError(f"Invalid category. Please choose from: {', '.join(valid_categories)}")
        
        valid_genders = ["male", "female", "unisex"]
        if gender not in valid_genders:
            raise ValueError(f"Invalid gender. Please choose from: {', '.join(valid_genders)}")
        
        prompt = f"""You are a creative pet naming expert. Generate {count} unique and suitable names for a {gender} {category}.

Requirements:
- Gender: {gender}
- Pet type: {category}

For each name, provide:
1. The name itself
2. A brief meaning or origin (1-2 sentences)
3. Why it suits a {gender} {category}

Format your response as a JSON array with objects containing: "name", "meaning", "suitability"

Example format:
[
  {{
    "name": "Shadow",
    "meaning": "Derived from the English word for darkness or shade",
    "suitability": "Perfect for a dark-colored or mysterious cat who likes to hide in quiet corners"
  }}
]

Generate creative, diverse names that aren't too common. Mix traditional and unique options.
"""
        
        logger.info(f"Generating pet names via OpenAI for {gender} {category}")
        
        if not openai_client:
            raise ValueError("OpenAI API key not configured. Please set OPENAI_API_KEY environment variable.")
        
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a creative pet naming expert who provides thoughtful, meaningful name suggestions."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.8,
            max_tokens=1500
        )
        
        # Extract the response
        ai_response = response.choices[0].message.content
        
        # Parse JSON response
        import json
        import re
        try:
            # Strip markdown code blocks if present
            cleaned_response = ai_response.strip()
            if cleaned_response.startswith("```"):
                # Remove markdown code block markers
                cleaned_response = re.sub(r'^```(?:json)?\s*\n?', '', cleaned_response)
                cleaned_response = re.sub(r'\n?```\s*$', '', cleaned_response)
            
            suggestions = json.loads(cleaned_response)
            # Handle both array and object responses
            if isinstance(suggestions, dict) and "names" in suggestions:
                suggestions = suggestions["names"]
            elif isinstance(suggestions, dict) and "suggestions" in suggestions:
                suggestions = suggestions["suggestions"]
        except json.JSONDecodeError:
            logger.error(f"Failed to parse OpenAI response as JSON: {ai_response}")
            raise ValueError("Failed to parse AI response. Please try again.")
        
        # Build response
        result = {
            "category": category,
            "gender": gender,
            "suggestions": suggestions,
            "total_suggestions": len(suggestions) if isinstance(suggestions, list) else count,
            "generated_at": datetime.now().isoformat(),
            "ai_model": "gpt-4o-mini",
            "disclaimer": "These names are AI-generated suggestions. Choose a name that resonates with you and suits your pet's personality."
        }
        
        logger.info(f"Successfully generated {len(suggestions) if isinstance(suggestions, list) else count} pet name suggestions")
        return result
        
    except openai.APIError as e:
        error_message = f"OpenAI API error: {str(e)}"
        logger.error(error_message)
        raise ValueError(f"Failed to generate pet names: {error_message}")
    except openai.RateLimitError as e:
        error_message = "OpenAI API rate limit exceeded. Please try again later."
        logger.error(error_message)
        raise ValueError(error_message)
    except openai.AuthenticationError as e:
        error_message = "OpenAI API authentication failed. Please check your API key."
        logger.error(error_message)
        raise ValueError(error_message)
    except ValueError as ve:
        raise ve
    except Exception as error:
        error_message = str(error)
        logger.error(f"Unexpected error generating pet names: {error_message}")
        raise ValueError(f"Failed to generate pet names: {error_message}")

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
