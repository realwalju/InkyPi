from plugins.base_plugin.base_plugin import BasePlugin
from openai import OpenAI
from PIL import Image
from io import BytesIO
import base64
import logging

logger = logging.getLogger(__name__)

# gpt-image-1 was shut down 2026-10-23 and gpt-image-2 shuts down 2027-02-10;
# OpenAI names the gpt-image-2.6 family as the replacement for both.
# Flare is the fast model, Sunburst the more detailed one (same token pricing).
IMAGE_MODELS = ["gpt-image-2.6-flare", "gpt-image-2.6-sunburst"]
DEFAULT_IMAGE_MODEL = "gpt-image-2.6-flare"
LEGACY_IMAGE_MODELS = {"gpt-image-1", "gpt-image-1-mini", "gpt-image-1.5", "gpt-image-2", "dall-e-2", "dall-e-3"}
IMAGE_QUALITIES = ["low", "medium", "high"]
DEFAULT_IMAGE_QUALITY = "medium"

class AIImage(BasePlugin):
    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params['api_key'] = {
            "required": True,
            "service": "OpenAI",
            "expected_key": "OPEN_AI_SECRET"
        }
        return template_params

    def generate_image(self, settings, device_config):
        logger.info("=== AI Image Plugin: Starting image generation ===")

        api_key = device_config.load_env_key("OPEN_AI_SECRET")
        if not api_key:
            logger.error("OpenAI API Key not configured")
            raise RuntimeError("OPEN AI API Key not configured.")

        text_prompt = (settings.get("textPrompt") or "").strip()
        if not text_prompt:
            raise RuntimeError("Text Prompt is required.")
        image_model = settings.get('imageModel') or DEFAULT_IMAGE_MODEL

        if image_model in LEGACY_IMAGE_MODELS:
            logger.warning(f"Image model '{image_model}' is retired by OpenAI, using {DEFAULT_IMAGE_MODEL} instead")
            image_model = DEFAULT_IMAGE_MODEL

        if image_model not in IMAGE_MODELS:
            logger.error(f"Invalid image model: {image_model}")
            raise RuntimeError("Invalid Image Model provided.")

        image_quality = settings.get('quality') or DEFAULT_IMAGE_QUALITY
        if image_quality not in IMAGE_QUALITIES:
            logger.warning(f"Invalid image quality '{image_quality}', using {DEFAULT_IMAGE_QUALITY}")
            image_quality = DEFAULT_IMAGE_QUALITY
        orientation = device_config.get_config("orientation")

        logger.info(f"Settings: model={image_model}, quality={image_quality}, orientation={orientation}")
        logger.debug(f"Prompt: '{text_prompt}'")

        image = None
        try:
            ai_client = OpenAI(api_key = api_key)

            logger.info(f"Generating image with {image_model}...")
            image = self.fetch_image(
                ai_client,
                text_prompt,
                model=image_model,
                quality=image_quality,
                orientation=orientation
            )

            if image:
                logger.info(f"AI image generated successfully: {image.size[0]}x{image.size[1]}")

        except Exception as e:
            logger.error(f"Failed to make OpenAI request: {str(e)}")
            raise RuntimeError("Open AI request failure, please check logs.")

        logger.info("=== AI Image Plugin: Image generation complete ===")
        return image

    def fetch_image(self, ai_client, prompt, model=DEFAULT_IMAGE_MODEL, quality=DEFAULT_IMAGE_QUALITY, orientation="horizontal"):
        """
        Fetch image from OpenAI API. Now an instance method to access image_loader.
        """
        logger.info(f"Generating image for prompt: {prompt}, model: {model}, quality: {quality}")
        prompt += (
            ". The image should fully occupy the entire canvas without any frames, "
            "borders, or cropped areas. No blank spaces or artificial framing."
        )
        prompt += (
            "Focus on simplicity, bold shapes, and strong contrast to enhance clarity "
            "and visual appeal. Avoid excessive detail or complex gradients, ensuring "
            "the design works well with flat, vibrant colors."
        )
        args = {
            "model": model,
            "prompt": prompt,
            "size": "1536x1024" if orientation == "horizontal" else "1024x1536",
            "quality": quality,
        }

        response = ai_client.images.generate(**args)
        image_base64 = response.data[0].b64_json
        image_bytes = base64.b64decode(image_base64)
        img = Image.open(BytesIO(image_bytes))
        return img
