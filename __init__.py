"""ComfyUI entrypoint for the Prompt & Dimensions from LLM node.

ComfyUI imports this module as the custom node package, so the
``comfy_entrypoint()`` lives here and re-exports the node defined in
``comfy_nodes.py``.
"""

from .comfy_nodes import PromptDimensionsFromLLM, comfy_entrypoint

__all__ = ["PromptDimensionsFromLLM", "comfy_entrypoint"]
