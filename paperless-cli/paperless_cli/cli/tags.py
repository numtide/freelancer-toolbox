"""Tag management commands for Paperless-ngx."""

from dataclasses import dataclass

from paperless_cli.api import PaperlessClient
from paperless_cli.cli.formatter import print_table
from paperless_cli.errors import TagNotFoundError


def resolve_tag_names_to_ids(client: PaperlessClient, tag_names_str: str) -> list[int]:
    """Convert comma-separated tag names to tag IDs.

    Args:
        client: PaperlessClient instance
        tag_names_str: Comma-separated string of tag names

    Returns:
        List of tag IDs

    Raises:
        TagNotFoundError: If any tags are not found
    """
    # Get all existing tags
    all_tags = client.get_tags()
    tag_dict = {tag["name"].lower(): tag["id"] for tag in all_tags}

    # Parse tag names
    tag_names = [name.strip() for name in tag_names_str.split(",")]
    tag_ids = []
    invalid_tags = []

    for tag_name in tag_names:
        tag_name_lower = tag_name.lower()
        if tag_name_lower in tag_dict:
            tag_ids.append(tag_dict[tag_name_lower])
        else:
            invalid_tags.append(tag_name)

    if invalid_tags:
        available_tag_names = sorted(tag["name"] for tag in all_tags)
        raise TagNotFoundError(invalid_tags, available_tag_names)

    return tag_ids


@dataclass
class TagsListCommand:
    """Tags list command."""


@dataclass
class TagsCreateCommand:
    """Tags create command."""

    name: str
    color: str | None = None


@dataclass
class TagsDeleteCommand:
    """Tags delete command."""

    tag_id: int
    force: bool = False


def list_tags(client: PaperlessClient) -> None:
    """List all tags."""
    tags = client.get_tags()
    if not tags:
        print("No tags found.")
        return

    headers = ["ID", "Name", "Color", "Documents"]
    rows = [
        [
            tag["id"],
            tag["name"],
            tag.get("color", "-"),
            tag.get("document_count", 0),
        ]
        for tag in tags
    ]
    print_table(headers, rows)


def create_tag(client: PaperlessClient, name: str, color: str | None) -> None:
    """Create a new tag."""
    data = {"name": name}
    if color:
        data["color"] = color

    tag = client.create_tag(data)
    print(f"Created tag '{tag['name']}' with ID {tag['id']}")


def delete_tag(client: PaperlessClient, tag_id: int, force: bool) -> None:
    """Delete a tag."""
    if not force:
        tags = client.get_tags()
        tag = next((t for t in tags if t["id"] == tag_id), None)
        if not tag:
            print(f"Tag with ID {tag_id} not found.")
            return

        confirm = input(
            f"Are you sure you want to delete tag '{tag['name']}' (ID: {tag_id})? [y/N]: "
        )
        if confirm.lower() != "y":
            print("Cancelled.")
            return

    client.delete_tag(tag_id)
    print(f"Deleted tag with ID {tag_id}")
