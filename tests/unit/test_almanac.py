import os
import pytest
import sqlite3
from app.database import (
    init_db,
    save_user_profile,
    get_user_profile,
    add_plant,
    remove_plant,
    get_active_plants
)
from app.tools import get_coordinates

def test_database_lifecycle():
    # Setup test database path
    test_db = "test_almanac.db"
    import app.database
    original_db = app.database.DB_FILE
    app.database.DB_FILE = test_db
    
    try:
        # Initialize
        init_db()
        
        # Test User Profile Isolation and Save/Load
        save_user_profile("test_user_1", "Seattle, WA", 47.6062, -122.3321)
        save_user_profile("test_user_2", "Miami, FL", 25.7617, -80.1918)
        
        profile1 = get_user_profile("test_user_1")
        profile2 = get_user_profile("test_user_2")
        
        assert profile1 is not None
        assert profile1["location_name"] == "Seattle, WA"
        assert profile1["latitude"] == 47.6062
        
        assert profile2 is not None
        assert profile2["location_name"] == "Miami, FL"
        assert profile2["longitude"] == -80.1918
        
        # Test Add Plant
        add_plant("test_user_1", "Fern", "Seedling", "Healthy")
        add_plant("test_user_1", "Hydrangea", "Mature", "Wilted")
        add_plant("test_user_2", "Palm Tree", "Established", "Healthy")
        
        plants1 = get_active_plants("test_user_1")
        plants2 = get_active_plants("test_user_2")
        
        # Check strict multi-tenant isolation
        assert len(plants1) == 2
        assert len(plants2) == 1
        
        assert plants1[0]["name"] in ["Fern", "Hydrangea"]
        assert plants2[0]["name"] == "Palm Tree"
        
        # Test Plant Deletion (soft remove)
        plant_to_remove = [p for p in plants1 if p["name"] == "Fern"][0]
        remove_plant("test_user_1", plant_to_remove["id"])
        
        plants1_after_removal = get_active_plants("test_user_1")
        assert len(plants1_after_removal) == 1
        assert plants1_after_removal[0]["name"] == "Hydrangea"
        
    finally:
        # Restore and cleanup
        app.database.DB_FILE = original_db
        if os.path.exists(test_db):
            os.remove(test_db)

def test_geocoding_tool():
    # Test valid geocoding coordinates lookup
    coords = get_coordinates("Seattle")
    assert coords is not None
    assert "latitude" in coords
    assert "longitude" in coords
    assert "Seattle" in coords["name"]
