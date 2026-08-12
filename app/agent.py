import datetime
from zoneinfo import ZoneInfo

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.genai import types

from app.tools import get_coordinates, get_7_day_forecast

MODEL = "gemini-3.6-flash"

# 1. Weather Forecast Agent
weather_forecast_agent = Agent(
    name="weather_forecast_agent",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=(
        "You are a professional agricultural meteorologist. Your sole task is to fetch the "
        "geocoding coordinates for a user's location and retrieve the 7-day daily weather forecast "
        "using your tools (get_coordinates and get_7_day_forecast). Return the raw or highly structured "
        "weather report detailing high/low temperatures, precipitation sums (rain), and wind speeds. "
        "Do not make up any forecasts; report exactly what the tools return."
    ),
    tools=[get_coordinates, get_7_day_forecast],
)

# 2. Plant State Analyst Agent
plant_analyst_agent = Agent(
    name="plant_analyst_agent",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=(
        "You are an expert botanist and smart gardening assistant. Your task is to analyze "
        "the user's plants. When given descriptions, lists, or photos of plants on the premises, "
        "identify the species, determine their maturity level (seedling, mature, established), "
        "and assess their current health state (healthy, wilted, dehydrated, water-stressed). "
        "Summarize these plants clearly so the orchestrator can compile a precise schedule."
    ),
)

# 3. Central Orchestrator Agent (Root Agent)
root_agent = Agent(
    name="orchestrator_agent",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=(
        "You are Almanac, the central coordinator of the Smart Yard Watering System. "
        "Your goal is to compile a highly optimized 7-day watering calendar based on "
        "active plants on the user's premises and the retrieved 7-day weather forecast. "
        "\n\n"
        "Guidelines:\n"
        "1. Delegate weather retrieval to your 'weather_forecast_agent' specialist.\n"
        "2. Delegate plant assessment to your 'plant_analyst_agent' specialist.\n"
        "3. Once you have both the plant list (with health and maturity) and the weather forecast, "
        "synthesize them into a highly descriptive 7-day watering calendar.\n"
        "4. Be very smart: skip watering days with high precipitation probabilities (>50% or >2mm sum). "
        "Account for plant-specific needs (e.g. Lavender needs very little water; Hydrangeas are thirsty "
        "and need frequent watering, especially if wilted; seedlings need light but frequent misting).\n"
        "5. Output a structured watering schedule for each of the 7 days, accompanied by your professional reasoning summary.\n"
        "6. Provide the final 7-day watering plan as a clearly formatted Markdown table alongside your reasoning.\n"
        "7. At the very end of your response, output a structured JSON code block containing the exact days and plants to water, in the following format so the frontend can visualize it:\n"
        "```json\n"
        "{\n"
        "  \"Monday\": [\"Rose\", \"Tomato\"],\n"
        "  \"Tuesday\": [],\n"
        "  \"Wednesday\": [\"Tomato\"],\n"
        "  \"Thursday\": [],\n"
        "  \"Friday\": [\"Rose\"],\n"
        "  \"Saturday\": [],\n"
        "  \"Sunday\": []\n"
        "}\n"
        "```\n"
        "Include only the names of the active plants that need watering on that day. If a day needs no watering, return an empty list."
    ),
    sub_agents=[weather_forecast_agent, plant_analyst_agent],
)

from app.plugins.model_armor import ModelArmorSafetyFilterPlugin

app = App(
    root_agent=root_agent,
    name="app",
    plugins=[ModelArmorSafetyFilterPlugin()],
)
