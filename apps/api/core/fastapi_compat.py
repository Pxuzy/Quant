from __future__ import annotations

from functools import wraps


def apply_starlette_router_compat() -> None:
    """Allow FastAPI 0.109 to run with Starlette builds that removed startup args."""
    from starlette.routing import Router

    if getattr(Router, "_quant_startup_arg_compat", False):
        return

    original_init = Router.__init__

    @wraps(original_init)
    def patched_init(self, *args, **kwargs):
        on_startup = kwargs.pop("on_startup", None)
        on_shutdown = kwargs.pop("on_shutdown", None)
        original_init(self, *args, **kwargs)
        self.on_startup = list(on_startup or [])
        self.on_shutdown = list(on_shutdown or [])

    def add_event_handler(self, event_type, func):
        if event_type == "startup":
            self.on_startup.append(func)
        elif event_type == "shutdown":
            self.on_shutdown.append(func)
        else:
            raise ValueError(f"Unsupported event type: {event_type}")

    Router.__init__ = patched_init
    Router.add_event_handler = add_event_handler
    Router._quant_startup_arg_compat = True
