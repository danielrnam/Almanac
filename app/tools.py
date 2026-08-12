import requests
import json
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, field_validator

# --- Strict Input Validation Schemas ---

class GeocodingInput(BaseModel):
    location_name: str = Field(
        ...,
        description="The name of the city, state, or region to search for (e.g., 'Seattle, WA'). Must not be empty or blank."
    )

    @field_validator("location_name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Location name cannot be empty or purely whitespace.")
        return v.strip()


class ForecastInput(BaseModel):
    latitude: float = Field(
        ...,
        description="The latitude coordinate. Must be a valid float between -90.0 and 90.0 degrees."
    )
    longitude: float = Field(
        ...,
        description="The longitude coordinate. Must be a valid float between -180.0 and 180.0 degrees."
    )

    @field_validator("latitude")
    @classmethod
    def validate_latitude(cls, v: float) -> float:
        if not (-90.0 <= v <= 90.0):
            raise ValueError(f"Latitude must be within the range [-90.0, 90.0]. Got: {v}")
        return v

    @field_validator("longitude")
    @classmethod
    def validate_longitude(cls, v: float) -> float:
        if not (-180.0 <= v <= 180.0):
            raise ValueError(f"Longitude must be within the range [-180.0, 180.0]. Got: {v}")
        return v


# --- Tool Implementation with Guided LLM Error Recovery ---

def get_coordinates(location_name: str) -> Dict[str, Any]:
    """Converts a location name (e.g. Seattle, WA) into latitude and longitude coordinates.

    Args:
        location_name: The name of the city, state, or region to search for.

    Returns:
        A dictionary with the resolved coordinates or a detailed LLM guided recovery block if geocoding fails.
    """
    # 1. Enforce strict JSON schema validation via Pydantic
    try:
        validated = GeocodingInput(location_name=location_name)
        location_name = validated.location_name
    except Exception as ve:
        return {
            "success": False,
            "error_type": "ValidationError",
            "message": f"Input validation failed: {ve}",
            "recovery_instructions": (
                "Please provide a valid, non-empty location name. Check for typos or empty values. "
                "Re-invoke get_coordinates with a complete city name, state, or country string (e.g., 'Miami, FL')."
            )
        }

    url = "https://geocoding-api.open-meteo.com/v1/search"
    params = {
        "name": location_name,
        "count": 1,
        "language": "en",
        "format": "json"
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        results = data.get("results", [])
        if results:
            result = results[0]
            return {
                "success": True,
                "latitude": result.get("latitude"),
                "longitude": result.get("longitude"),
                "name": result.get("name")
            }
        else:
            return {
                "success": False,
                "error_type": "NoResultsFound",
                "message": f"Could not find any location named '{location_name}'.",
                "recovery_instructions": (
                    "The location name was not found. Please specify a more common, larger, or standard city name "
                    "or include regional indicators (e.g., instead of 'Drnam's Garden', use 'Palo Alto, CA')."
                )
            }
    except Exception as e:
        return {
            "success": False,
            "error_type": "NetworkOrServiceError",
            "message": f"REST endpoint failed: {e}",
            "recovery_instructions": (
                "The geocoding service is temporarily unreachable or rate-limited. "
                "You may retry the request after a few seconds or proceed by asking the user to provide "
                "their approximate latitude and longitude coordinates manually if the issue persists."
            )
        }


def get_7_day_forecast(latitude: float, longitude: float) -> str:
    """Fetches a highly detailed 7-day daily weather forecast for given coordinates.

    Args:
        latitude: The latitude of the location.
        longitude: The longitude of the location.

    Returns:
        A structured JSON string outlining the daily forecast or an LLM guided recovery block if the API fails.
    """
    # 1. Enforce strict JSON schema validation via Pydantic
    try:
        validated = ForecastInput(latitude=latitude, longitude=longitude)
        lat = validated.latitude
        lon = validated.longitude
    except Exception as ve:
        return json.dumps({
            "success": False,
            "error_type": "ValidationError",
            "message": f"Input validation failed: {ve}",
            "recovery_instructions": (
                "The coordinates supplied fell outside the accepted bounds of [-90, 90] for latitude and "
                "[-180, 180] for longitude. Please check your coordinate lookup and re-run get_7_day_forecast "
                "using the precise, valid float coordinates returned by the get_coordinates tool."
            )
        }, indent=2)

    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,wind_speed_10m_max",
        "timezone": "auto"
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        daily = data.get("daily", {})
        
        forecast = []
        for i in range(len(daily.get("time", []))):
            forecast.append({
                "date": daily["time"][i],
                "max_temp_c": daily["temperature_2m_max"][i],
                "min_temp_c": daily["temperature_2m_min"][i],
                "precipitation_mm": daily["precipitation_sum"][i],
                "precipitation_probability_pct": daily["precipitation_probability_max"][i],
                "max_wind_speed_kmh": daily["wind_speed_10m_max"][i]
            })
            
        return json.dumps({
            "success": True,
            "timezone": data.get("timezone"),
            "elevation": data.get("elevation"),
            "daily_forecast": forecast
        }, indent=2)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error_type": "MeteoServiceError",
            "message": f"API request failed: {e}",
            "recovery_instructions": (
                "The Open-Meteo REST service is currently down, slow, or returning invalid payloads. "
                "Please retry the tool call in a moment. If the failure persists, let the user know that "
                "live weather forecasts cannot be loaded, and formulate a safe default summer/winter "
                "watering recommendation based on typical seasonal averages for their region."
            )
        }, indent=2)
