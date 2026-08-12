import os
import logging
from typing import Any, Optional
from google.adk.plugins import base_plugin
from google.adk.agents import invocation_context
from google.adk.models import llm_response
from google.adk.tools import base_tool, tool_context
from google.genai import types

BasePlugin = base_plugin.BasePlugin
CallbackContext = base_plugin.CallbackContext
InvocationContext = invocation_context.InvocationContext
ToolContext = tool_context.ToolContext
BaseTool = base_tool.BaseTool
LlmResponse = llm_response.LlmResponse

_USER_PROMPT_REMOVED_MESSAGE = "A safety filter has removed the last user prompt as it was deemed unsafe (Potential Prompt Injection / Malicious Intent)."
_MODEL_RESPONSE_REMOVED_MESSAGE = "A safety filter has removed the model's response as it was deemed unsafe."
_UNSAFE_TOOL_OUTPUT_MESSAGE = "Unable to emit tool result due to unsafe outputs."

class ModelArmorSafetyFilterPlugin(BasePlugin):
    """Safety guardrail plugin wrapping ADK run times to detect prompt injections and unsafe outputs."""

    def __init__(self, project_id: str = "", location_id: str = "", template_id: str = ""):
        super().__init__(name="ModelArmorPlugin")
        self._project_id = project_id or os.environ.get("GOOGLE_CLOUD_PROJECT", "")
        self._location_id = location_id or os.environ.get("GOOGLE_CLOUD_LOCATION", "")
        self._template_id = template_id or os.environ.get("MODEL_ARMOR_TEMPLATE_ID", "")
        self._client = None
        self._model_armor_url = ""
        
        # Safe initialization
        if self._project_id and self._location_id and self._template_id:
            try:
                from google.cloud import modelarmor_v1
                from google.api_core.client_options import ClientOptions
                self._model_armor_url = f"projects/{self._project_id}/locations/{self._location_id}/templates/{self._template_id}"
                self._client = modelarmor_v1.ModelArmorClient(
                    client_options=ClientOptions(
                        api_endpoint=f"modelarmor.{self._location_id}.rep.googleapis.com"
                    ),
                )
                logging.info("Model Armor initialized successfully for Vertex AI.")
            except Exception as e:
                logging.warning(f"Failed to load Vertex AI Model Armor client: {e}. Falling back to local safety heuristics.")
        else:
            logging.info("Model Armor configuration missing. Operating in Local Safety Heuristics Mode.")

    def _check_local_heuristics(self, text: str) -> Optional[str]:
        """Provides robust fallback detection for prompt injections / jailbreaks locally."""
        lower_text = text.lower()
        adversarial_terms = [
            "ignore previous", 
            "ignore all instructions", 
            "bypass system", 
            "system override", 
            "you are now a", 
            "jailbreak",
            "sql injection", 
            "drop table"
        ]
        for term in adversarial_terms:
            if term in lower_text:
                return f"[Local Safety Warning: Adversarial pattern '{term}']"
        return None

    def _get_safety_verdict(self, text: str) -> Optional[str]:
        """Checks text against Model Armor API, falling back to local checks if unavailable."""
        local_warning = self._check_local_heuristics(text)
        if local_warning:
            return local_warning

        if not self._client:
            return None

        try:
            from google.cloud import modelarmor_v1
            user_prompt_data = modelarmor_v1.DataItem(text=text)
            request = modelarmor_v1.SanitizeUserPromptRequest(
                name=self._model_armor_url,
                user_prompt_data=user_prompt_data,
            )
            response = self._client.sanitize_user_prompt(request=request)
            # Check response validation results
            if response.sanitize_result and response.sanitize_result.is_unsafe:
                return "[Vertex Model Armor Flagged Input]"
        except Exception as e:
            logging.debug(f"Model Armor API error: {e}")
            
        return None

    async def on_user_message_callback(
        self,
        invocation_context: InvocationContext,
        user_message: types.Content,
    ) -> types.Content | None:
        if not user_message.parts or not user_message.parts[0].text:
            return None
            
        text = user_message.parts[0].text
        if verdict := self._get_safety_verdict(text):
            invocation_context.session.state["is_user_prompt_safe"] = False
            return types.Content(
                role="user",
                parts=[
                    types.Part.from_text(
                        text=f"{_USER_PROMPT_REMOVED_MESSAGE} Reason: {verdict}"
                    )
                ],
            )

    async def before_run_callback(
        self,
        invocation_context: InvocationContext,
    ) -> types.Content | None:
        if not invocation_context.session.state.get("is_user_prompt_safe", True):
            # Reset to allow future normal turns
            invocation_context.session.state["is_user_prompt_safe"] = True
            return types.Content(
                role="model",
                parts=[
                    types.Part.from_text(text=_USER_PROMPT_REMOVED_MESSAGE)
                ],
            )

    async def after_model_callback(
        self,
        callback_context: CallbackContext,
        llm_response: LlmResponse,
    ) -> LlmResponse | None:
        llm_content = llm_response.content
        if not llm_content or not llm_content.parts:
            return None
            
        model_output = "\n".join([part.text or "" for part in llm_content.parts]).strip()
        if not model_output:
            return None
            
        if self._get_safety_verdict(model_output):
            return LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part.from_text(text=_MODEL_RESPONSE_REMOVED_MESSAGE)
                    ],
                )
            )

    async def after_tool_callback(
        self,
        tool: BaseTool,
        tool_args: dict[str, Any],
        tool_context: ToolContext,
        result: dict[str, Any],
    ) -> dict[str, Any] | None:
        if verdict := self._get_safety_verdict(str(result)):
            return {
                "error": f"{_UNSAFE_TOOL_OUTPUT_MESSAGE} Reason: {verdict}"
            }
