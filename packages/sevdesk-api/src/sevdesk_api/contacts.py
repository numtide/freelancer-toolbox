"""Contact operations for SevDesk API."""

from typing import Any

from .client import SevDeskClient
from .models import Contact, ContactCategory


class ContactOperations:
    """Operations for managing contacts."""

    def __init__(self, client: SevDeskClient) -> None:
        """Initialize ContactOperations.

        Args:
            client: SevDeskClient instance

        """
        self.client = client

    def get_contacts(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        depth: bool = True,
        name: str | None = None,
        customer_number: str | None = None,
        category: ContactCategory | None = None,
    ) -> list[Contact]:
        """Get a list of contacts.

        Args:
            limit: Number of results to return
            offset: Offset for pagination
            depth: If True, retrieve both organizations and persons
            name: Filter by name (searches name, surename, and familyname)
            customer_number: Filter by customer number
            category: Filter by category

        Returns:
            List of Contact objects

        """
        params: dict[str, Any] = {
            "limit": limit,
            "offset": offset,
        }

        if depth:
            params["depth"] = 1
        if name:
            params["name"] = name
        if customer_number:
            params["customerNumber"] = customer_number
        if category:
            params["category[id]"] = category.value
            params["category[objectName]"] = "Category"

        response = self.client.get("Contact", params=params)
        contacts: list[Contact] = []

        if "objects" in response:
            contacts.extend(
                Contact.from_dict(contact_data) for contact_data in response["objects"]
            )

        return contacts

    def get_contact(self, contact_id: int) -> Contact:
        """Get a specific contact by ID.

        Args:
            contact_id: The contact ID

        Returns:
            Contact object

        """
        response = self.client.get(f"Contact/{contact_id}")

        if response.get("objects"):
            return Contact.from_dict(response["objects"][0])
        msg = f"Contact with ID {contact_id} not found"
        raise ValueError(msg)

    def search_by_name(self, name: str) -> list[Contact]:
        """Search for contacts by name.

        Args:
            name: The name to search for

        Returns:
            List of matching contacts

        """
        return self.get_contacts(name=name)

    def create_contact(self, contact: Contact) -> Contact:
        """Create a new contact.

        Args:
            contact: Contact object to create

        Returns:
            Created contact with ID

        """
        data = contact.to_dict()
        response = self.client.post("Contact", json_data=data)

        if "objects" in response:
            return Contact.from_dict(response["objects"])
        msg = "Failed to create contact"
        raise ValueError(msg)

    def update_contact(self, contact: Contact) -> Contact:
        """Update an existing contact.

        Args:
            contact: Contact object with ID to update

        Returns:
            Updated contact

        """
        if not contact.id:
            msg = "Contact must have an ID to update"
            raise ValueError(msg)

        data = contact.to_dict()
        response = self.client.put(f"Contact/{contact.id}", json_data=data)

        if "objects" in response:
            return Contact.from_dict(response["objects"])
        msg = "Failed to update contact"
        raise ValueError(msg)

    def check_customer_number_availability(self, customer_number: str) -> bool:
        """Check if a customer number is available.

        Args:
            customer_number: The customer number to check

        Returns:
            True if available, False otherwise

        """
        response = self.client.get(
            "Contact/Mapper/checkCustomerNumberAvailability",
            params={"customerNumber": customer_number},
        )
        return bool(response.get("objects", False))

    def get_next_customer_number(self) -> str:
        """Get the next available customer number.

        Returns:
            Next customer number

        """
        response = self.client.get("Contact/Factory/getNextCustomerNumber")
        return str(response.get("objects", ""))
