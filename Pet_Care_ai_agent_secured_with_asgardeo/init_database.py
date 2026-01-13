import sqlite3
from datetime import datetime
import os

DATABASE_PATH = "pet_clinic.db"

def init_database():
    """Initialize the SQLite database with schema and sample data."""
    
    # Remove existing database if it exists
    if os.path.exists(DATABASE_PATH):
        os.remove(DATABASE_PATH)
        print(f"Removed existing database: {DATABASE_PATH}")
    
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    # Create Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            email TEXT PRIMARY KEY,
            user_id TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            account_status TEXT NOT NULL,
            registered_since DATE NOT NULL
        )
    """)
    
    # Create Pets table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pets (
            pet_id TEXT PRIMARY KEY,
            pet_name TEXT NOT NULL,
            type TEXT NOT NULL,
            owner_email TEXT NOT NULL,
            FOREIGN KEY (owner_email) REFERENCES users(email)
        )
    """)
    
    # Create Vaccinations table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vaccinations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pet_id TEXT NOT NULL,
            vaccine_name TEXT NOT NULL,
            date_administered DATE NOT NULL,
            veterinarian TEXT NOT NULL,
            next_due_date DATE,
            FOREIGN KEY (pet_id) REFERENCES pets(pet_id)
        )
    """)
    
    # Create Upcoming Vaccinations table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS upcoming_vaccinations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pet_id TEXT NOT NULL,
            vaccine_name TEXT NOT NULL,
            due_date DATE NOT NULL,
            status TEXT DEFAULT 'upcoming',
            FOREIGN KEY (pet_id) REFERENCES pets(pet_id)
        )
    """)
    
    # Create Appointments table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS appointments (
            appointment_id TEXT PRIMARY KEY,
            pet_id TEXT NOT NULL,
            date DATE NOT NULL,
            time TEXT NOT NULL,
            reason TEXT NOT NULL,
            status TEXT NOT NULL,
            veterinarian TEXT,
            clinic_name TEXT,
            clinic_address TEXT,
            booked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            canceled_at TIMESTAMP,
            cancellation_reason TEXT,
            FOREIGN KEY (pet_id) REFERENCES pets(pet_id)
        )
    """)
    
    print("Created database schema")
    
    # Insert sample users
    users_data = [
        ("pasansanjiiwa2022@gmail.com", "USER-PS2022", "Pasan Sanjiiwa", "active", "2022-05-10"),
        ("john.doe@example.com", "USER-JD1234", "John Doe", "active", "2023-01-15")
    ]
    
    cursor.executemany("""
        INSERT INTO users (email, user_id, name, account_status, registered_since)
        VALUES (?, ?, ?, ?, ?)
    """, users_data)
    
    print(f"Inserted {len(users_data)} users")
    
    # Insert sample pets
    pets_data = [
        ("123", "Buddy", "Dog", "pasansanjiiwa2022@gmail.com"),
        ("455", "Spot", "Dog", "pasansanjiiwa2022@gmail.com"),
        ("456", "Luna", "Cat", "john.doe@example.com")
    ]
    
    cursor.executemany("""
        INSERT INTO pets (pet_id, pet_name, type, owner_email)
        VALUES (?, ?, ?, ?)
    """, pets_data)
    
    print(f"Inserted {len(pets_data)} pets")
    
    # Insert vaccination history for Buddy (pet_id: 123)
    vaccinations_data = [
        ("123", "Rabies", "2024-01-15", "Dr. Smith", "2025-01-15"),
        ("123", "DHPP", "2024-03-20", "Dr. Johnson", "2025-03-20"),
        ("123", "Bordetella", "2024-06-10", "Dr. Smith", "2024-12-10")
    ]
    
    cursor.executemany("""
        INSERT INTO vaccinations (pet_id, vaccine_name, date_administered, veterinarian, next_due_date)
        VALUES (?, ?, ?, ?, ?)
    """, vaccinations_data)
    
    print(f"Inserted {len(vaccinations_data)} vaccination records")
    
    # Insert upcoming vaccinations
    upcoming_data = [
        ("123", "Bordetella", "2024-12-10", "upcoming")
    ]
    
    cursor.executemany("""
        INSERT INTO upcoming_vaccinations (pet_id, vaccine_name, due_date, status)
        VALUES (?, ?, ?, ?)
    """, upcoming_data)
    
    print(f"Inserted {len(upcoming_data)} upcoming vaccination records")
    
    conn.commit()
    conn.close()
    
    print(f"\nDatabase initialized successfully: {DATABASE_PATH}")
    print("You can now run the main application.")

if __name__ == "__main__":
    init_database()