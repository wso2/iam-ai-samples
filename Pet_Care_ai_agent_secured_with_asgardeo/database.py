import sqlite3
from typing import Any, Optional
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)

DATABASE_PATH = "pet_clinic.db"

@contextmanager
def get_db_connection():
    """Context manager for database connections."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row  # Enable column access by name
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        conn.close()

def get_user_by_email(email: str) -> Optional[dict[str, Any]]:
    """Get user information by email."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT email, user_id, name, account_status, registered_since
            FROM users
            WHERE email = ?
        """, (email,))
        
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None

def get_pets_by_owner_email(email: str) -> list[dict[str, Any]]:
    """Get all pets owned by a user identified by email."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT pet_id, pet_name, type, owner_email
            FROM pets
            WHERE owner_email = ?
        """, (email,))
        
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def get_user_by_user_id(user_id: str) -> Optional[dict[str, Any]]:
    """Get user information by user_id."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT email, user_id, name, account_status, registered_since
            FROM users
            WHERE user_id = ?
        """, (user_id,))
        
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None

def get_pet_by_id(pet_id: str) -> Optional[dict[str, Any]]:
    """Get pet information by pet_id."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT pet_id, pet_name, type, owner_email
            FROM pets
            WHERE pet_id = ?
        """, (pet_id,))
        
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None

def get_vaccination_history(pet_id: str) -> list[dict[str, Any]]:
    """Get vaccination history for a pet."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT vaccine_name, date_administered, veterinarian, next_due_date
            FROM vaccinations
            WHERE pet_id = ?
            ORDER BY date_administered DESC
        """, (pet_id,))
        
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def get_upcoming_vaccinations(pet_id: str) -> list[dict[str, Any]]:
    """Get upcoming vaccinations for a pet."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT vaccine_name, due_date, status
            FROM upcoming_vaccinations
            WHERE pet_id = ? AND status = 'upcoming'
            ORDER BY due_date ASC
        """, (pet_id,))
        
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def create_appointment(
    appointment_id: str,
    pet_id: str,
    date: str,
    time: str,
    reason: str,
    status: str = "confirmed",
    veterinarian: str = "Dr. Smith",
    clinic_name: str = "Happy Paws Veterinary Clinic",
    clinic_address: str = "123 Main Street, City, State 12345"
) -> dict[str, Any]:
    """Create a new appointment."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO appointments (
                appointment_id, pet_id, date, time, reason, status,
                veterinarian, clinic_name, clinic_address
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (appointment_id, pet_id, date, time, reason, status,
              veterinarian, clinic_name, clinic_address))
        
        # Fetch the created appointment
        cursor.execute("""
            SELECT * FROM appointments WHERE appointment_id = ?
        """, (appointment_id,))
        
        row = cursor.fetchone()
        return dict(row) if row else {}

def cancel_appointment(appointment_id: str, reason: str) -> Optional[dict[str, Any]]:
    """Cancel an existing appointment."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Check if appointment exists
        cursor.execute("""
            SELECT * FROM appointments WHERE appointment_id = ?
        """, (appointment_id,))
        
        row = cursor.fetchone()
        if not row:
            return None
        
        # Update appointment status
        cursor.execute("""
            UPDATE appointments
            SET status = 'canceled',
                canceled_at = CURRENT_TIMESTAMP,
                cancellation_reason = ?
            WHERE appointment_id = ?
        """, (reason, appointment_id))
        
        # Fetch updated appointment
        cursor.execute("""
            SELECT * FROM appointments WHERE appointment_id = ?
        """, (appointment_id,))
        
        row = cursor.fetchone()
        return dict(row) if row else None

def get_appointment_by_id(appointment_id: str) -> Optional[dict[str, Any]]:
    """Get appointment information by appointment_id."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM appointments WHERE appointment_id = ?
        """, (appointment_id,))
        
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None