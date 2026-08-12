import requests
import json
from typing import Dict, Any, Optional

def get_coordinates(location_name: str) -> Optional[Dict[str, Any]]:
    """Converts a location name (e.g. Seattle, WA) into latitude and longitude coordinates.

    Args:
        location_name: The name of the city, state, or region.

    Returns:
        A dictionary with keys 'latitude', 'longitude', and 'name', or None if not found.
    """
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
                "latitude": result.get("latitude"),
                "longitude": result.get("longitude"),
                "name": result.get("name")
            }
    except Exception as e:
        print(f"Error in geocoding location '{location_name}': {e}")
        
    return None

def get_7_day_forecast(latitude: float, longitude: float) -> str:
    """Fetches a highly detailed 7-day daily weather forecast for given coordinates.

    Args:
        latitude: The latitude of the location.
        longitude: The longitude of the location.

    Returns:
        A structured JSON string outlining the daily temperature, precipitation, and wind speeds over 7 days.
    """
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,wind_speed_10m_max",
        "timezone": "auto"
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        daily = data.get("daily", {})
        
        # Format the daily parameters into a simplified structured dictionary for the agent
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
            "timezone": data.get("timezone"),
            "elevation": data.get("elevation"),
            "daily_forecast": forecast
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Failed to retrieve 7-day forecast: {e}"})
