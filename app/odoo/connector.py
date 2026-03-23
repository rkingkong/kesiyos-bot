"""
Kesiyos Bot — Odoo XML-RPC Connector (Phase 2)

This module will read from the odoo_sync_queue table and push
structured data to Odoo 17 via XML-RPC.

Currently stubbed out — the interface is defined so the rest of
the application can write to the queue without knowing about Odoo.
"""

import logging
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


class OdooConnector:
    """
    Handles synchronization between the bot's database and Odoo 17.

    Phase 2 implementation will use xmlrpc.client to connect to:
    - {odoo_url}/xmlrpc/2/common  (authentication)
    - {odoo_url}/xmlrpc/2/object  (CRUD operations)

    Odoo models to target:
    - sale.order + sale.order.line  (for customer orders)
    - res.partner                   (for new customer contacts)
    - Custom reservation model      (TBD based on Odoo setup)
    """

    def __init__(self):
        self.url = settings.odoo_url
        self.db = settings.odoo_db
        self.user = settings.odoo_user
        self.password = settings.odoo_password
        self._uid: int | None = None

    async def authenticate(self) -> bool:
        """Authenticate with Odoo and store UID. Not implemented yet."""
        logger.info("OdooConnector.authenticate() — Phase 2, not yet implemented")
        return False

    async def push_sale_order(self, order_data: dict[str, Any]) -> bool:
        """
        Create a sale.order in Odoo from a completed bot order.

        Expected order_data structure:
        {
            "customer_name": "Juan Pérez",
            "customer_phone": "+502...",
            "items": [
                {"product": "Kesiyo de Pollo", "quantity": 3, "unit_price": 39},
                ...
            ],
            "delivery_address": "Zona 16, Paseo Cayalá",  # if delivery
            "is_delivery": True,
            "notes": "Tortilla negra, salsa chipotle",
            "platform": "instagram",
        }
        """
        logger.info("OdooConnector.push_sale_order() — Phase 2, not yet implemented")
        return False

    async def push_reservation(self, reservation_data: dict[str, Any]) -> bool:
        """
        Create a reservation record in Odoo.

        Expected reservation_data structure:
        {
            "customer_name": "María López",
            "customer_phone": "+502...",
            "date": "2026-03-25",
            "time": "19:00",
            "party_size": 4,
            "notes": "Mesa para cumpleaños",
            "platform": "messenger",
        }
        """
        logger.info("OdooConnector.push_reservation() — Phase 2, not yet implemented")
        return False

    async def push_new_contact(self, contact_data: dict[str, Any]) -> bool:
        """
        Create or update a res.partner in Odoo.

        Expected contact_data structure:
        {
            "name": "Customer Name",
            "phone": "+502...",
            "platform": "instagram",
            "platform_id": "IGSID_12345",
        }
        """
        logger.info("OdooConnector.push_new_contact() — Phase 2, not yet implemented")
        return False

    async def process_sync_queue(self) -> int:
        """
        Batch process pending items in odoo_sync_queue.
        Returns the number of items successfully synced.
        Not implemented yet — will be a periodic task in Phase 2.
        """
        logger.info("OdooConnector.process_sync_queue() — Phase 2, not yet implemented")
        return 0
