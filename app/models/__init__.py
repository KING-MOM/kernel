# Import all models so Base.metadata.create_all() finds them
from app.models.core import Person, Relationship, Event, Inbox, Outbox, ContactWindow, ConversationThread, WebhookConfig  # noqa
from app.models.physics_config import PhysicsConfig  # noqa
