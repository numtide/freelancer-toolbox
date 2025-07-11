"""Document management commands for Paperless-ngx."""

from dataclasses import dataclass
from pathlib import Path
import time

from paperless_cli.api import PaperlessAPIError, PaperlessClient
from paperless_cli.cli.formatter import print_table
from paperless_cli.cli.tags import resolve_tag_names_to_ids
from paperless_cli.models import (
    BulkEditRequest,
    DocumentSearchParams,
    DocumentUpdateRequest,
)


@dataclass
class DocumentsSearchCommand:
    """Documents search command."""

    query: str | None = None
    tags: str | None = None
    page: int = 1
    page_size: int = 25


@dataclass
class DocumentsGetCommand:
    """Documents get command."""

    document_id: int
    download: bool = False
    original: bool = False
    output: str | None = None
    metadata: bool = False


@dataclass
class DocumentsUploadCommand:
    """Documents upload command."""

    file_path: str
    title: str | None = None
    tags: str | None = None


@dataclass
class DocumentsDeleteCommand:
    """Documents delete command."""

    document_id: int
    force: bool = False


@dataclass
class DocumentsUpdateCommand:
    """Documents update command."""

    document_id: int
    add_tags: str | None = None
    remove_tags: str | None = None
    set_tags: str | None = None


@dataclass
class DocumentsBulkCommand:
    """Documents bulk command."""

    document_ids: list[int]
    add_tags: str | None = None
    remove_tags: str | None = None


def search_documents(client: PaperlessClient, cmd: DocumentsSearchCommand) -> None:
    """Search for documents."""
    # Build search parameters
    search_params = DocumentSearchParams(
        query=cmd.query,
        page=cmd.page,
        page_size=cmd.page_size,
    )

    # Add tag filtering if specified
    if cmd.tags:
        tag_ids = resolve_tag_names_to_ids(client, cmd.tags)
        search_params.tags__id__in = tag_ids

    result = client.search_documents(search_params)

    if not result.results:
        print("No documents found.")
        return

    headers = ["ID", "Title", "Correspondent", "Created", "Tags"]
    rows = []

    # Cache tags and correspondents for efficiency
    all_tags = client.get_tags()
    tag_dict = {t.id: t.name for t in all_tags}

    correspondents = client.get_correspondents()
    corr_dict = {c.id: c.name for c in correspondents}

    for doc in result.results:
        # Get tag names
        tag_names = [tag_dict.get(tag_id, str(tag_id)) for tag_id in doc.tags]

        # Get correspondent name
        correspondent = corr_dict.get(doc.correspondent, "") if doc.correspondent else ""

        rows.append(
            [
                doc.id,
                doc.title or "Untitled",
                correspondent or "-",
                doc.created.strftime("%Y-%m-%d"),
                ", ".join(tag_names) if tag_names else "-",
            ]
        )

    print_table(headers, rows)

    # Print pagination info
    if result.count > cmd.page_size:
        print(f"\nShowing page {cmd.page} of {(result.count + cmd.page_size - 1) // cmd.page_size}")
        print(f"Total documents: {result.count}")


def get_document(client: PaperlessClient, cmd: DocumentsGetCommand) -> None:
    """Get document details or download it."""
    if cmd.download:
        # Download the document
        content = client.download_document(cmd.document_id, cmd.original)

        if cmd.output:
            output_path = cmd.output
        else:
            # Get document info to determine filename
            doc = client.get_document(cmd.document_id)
            filename = doc.original_file_name or f"document_{cmd.document_id}.pdf"
            output_path = filename

        with Path(output_path).open("wb") as f:
            f.write(content)
        print(f"Downloaded document to: {output_path}")

    elif cmd.metadata:
        # Show metadata
        metadata = client.get_document_metadata(cmd.document_id)
        print(f"\nDocument Metadata (ID: {cmd.document_id})")
        print("=" * 50)
        for key, value in metadata.items():
            print(f"{key}: {value}")

    else:
        # Show document details
        doc = client.get_document(cmd.document_id)

        print(f"\nDocument Details (ID: {doc.id})")
        print("=" * 50)
        print(f"Title: {doc.title or 'Untitled'}")
        print(f"ASN: {doc.archive_serial_number or '-'}")
        print(f"Created: {doc.created.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Added: {doc.added.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Modified: {doc.modified.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Original filename: {doc.original_file_name or '-'}")

        # Correspondent
        if doc.correspondent:
            correspondents = client.get_correspondents()
            corr = next((c for c in correspondents if c.id == doc.correspondent), None)
            if corr:
                print(f"Correspondent: {corr.name}")

        # Document type
        if doc.document_type:
            doc_types = client.get_document_types()
            doc_type = next((dt for dt in doc_types if dt.id == doc.document_type), None)
            if doc_type:
                print(f"Document type: {doc_type.name}")

        # Tags
        if doc.tags:
            tags = client.get_tags()
            tag_names = [tag.name for tag in tags if tag.id in doc.tags]
            print(f"Tags: {', '.join(tag_names)}")

        # Content
        if doc.content:
            print("\nContent preview:")
            print("-" * 20)
            # Show first 500 characters
            content_str = doc.content[:500]
            if len(doc.content) > 500:
                content_str += "..."
            print(content_str)


def upload_document(client: PaperlessClient, cmd: DocumentsUploadCommand) -> None:
    """Upload a document."""
    # Check if file exists
    if not Path(cmd.file_path).exists():
        print(f"Error: File not found: {cmd.file_path}")
        return

    # Parse tags if provided
    tag_ids = None
    if cmd.tags:
        tag_ids = resolve_tag_names_to_ids(client, cmd.tags)

    try:
        print(f"Uploading '{Path(cmd.file_path).name}'...")
        result = client.upload_document(cmd.file_path, cmd.title, tag_ids)

        # Get task_id from response
        task_id = result.get("task_id")
        if not task_id:
            print("Document uploaded but no task ID returned")
            return

        print("Upload successful. Waiting for processing...")

        # Poll for task completion
        start_time = time.time()
        dots = 0

        while True:
            task = client.get_task_status(task_id)
            if not task:
                print("\nError: Could not find task status")
                return

            status = task.status

            if status not in ["PENDING", "STARTED"]:
                # Task completed (success or failure)
                processing_time = time.time() - start_time
                print()  # New line after dots

                if status == "SUCCESS":
                    print("✓ Document processed successfully!")

                    # Extract document ID from result message
                    result_msg = task.result or ""
                    print(f"  Result: {result_msg}")
                    print(f"  Processing time: {processing_time:.1f} seconds")

                    # Try to extract document ID from result
                    if task.related_document:
                        # Construct URL based on the known pattern
                        base_url = client.url.replace("-api", "")  # Remove -api from URL
                        print(f"  View at: {base_url}/documents/{task.related_document}")
                else:
                    print("✗ Document processing failed!")
                    result_msg = task.result or "Unknown error"
                    print(f"  Result: {result_msg}")
                    print(f"  Processing time: {processing_time:.1f} seconds")

                return

            # Still processing, show progress
            print(".", end="", flush=True)
            dots += 1
            time.sleep(2)

    except PaperlessAPIError as e:
        print(f"Error uploading document: {e}")


def delete_document(client: PaperlessClient, document_id: int, force: bool) -> None:
    """Delete a document."""
    if not force:
        doc = client.get_document(document_id)
        confirm = input(
            f"Are you sure you want to delete document '{doc.title or 'Untitled'}' (ID: {document_id})? [y/N]: "
        )
        if confirm.lower() != "y":
            print("Cancelled.")
            return

    client.delete_document(document_id)
    print(f"Deleted document with ID {document_id}")


def update_document(client: PaperlessClient, cmd: DocumentsUpdateCommand) -> None:
    """Update a document's tags."""
    # Get current document to show what we're updating
    doc = client.get_document(cmd.document_id)

    # Get current tags
    all_tags = client.get_tags()
    tag_dict = {t.id: t.name for t in all_tags}
    current_tag_names = [tag_dict.get(tag_id, str(tag_id)) for tag_id in doc.tags]

    print(f"Updating document: {doc.title}")
    print(f"Current tags: {', '.join(current_tag_names) if current_tag_names else 'None'}")

    # Build update request
    update_request = DocumentUpdateRequest()

    if cmd.set_tags is not None:
        # Replace all tags
        tag_ids = resolve_tag_names_to_ids(client, cmd.set_tags) if cmd.set_tags else []
        update_request.tags = tag_ids
        action = f"Setting tags to: {cmd.set_tags if cmd.set_tags else 'None'}"
    else:
        # Add/remove tags incrementally
        new_tag_ids = set(doc.tags)
        actions = []

        if cmd.add_tags:
            add_ids = resolve_tag_names_to_ids(client, cmd.add_tags)
            new_tag_ids.update(add_ids)
            actions.append(f"Adding: {cmd.add_tags}")

        if cmd.remove_tags:
            remove_ids = resolve_tag_names_to_ids(client, cmd.remove_tags)
            new_tag_ids.difference_update(remove_ids)
            actions.append(f"Removing: {cmd.remove_tags}")

        update_request.tags = list(new_tag_ids)
        action = "; ".join(actions)

    print(action)

    # Update the document
    updated_doc = client.update_document(cmd.document_id, update_request)

    # Show new tags
    new_tag_names = [tag_dict.get(tag_id, str(tag_id)) for tag_id in updated_doc.tags]
    print(f"Updated tags: {', '.join(new_tag_names) if new_tag_names else 'None'}")


def bulk_edit_documents(client: PaperlessClient, cmd: DocumentsBulkCommand) -> None:
    """Perform bulk tag operations on multiple documents."""
    # Validate document IDs exist
    print(f"Validating {len(cmd.document_ids)} documents...")
    valid_docs = []
    for doc_id in cmd.document_ids:
        try:
            doc = client.get_document(doc_id)
            valid_docs.append(doc)
        except PaperlessAPIError:
            print(f"Warning: Document {doc_id} not found, skipping")

    if not valid_docs:
        print("No valid documents found.")
        return

    print(f"Found {len(valid_docs)} valid documents")

    # Determine operation
    if cmd.add_tags:
        tag_ids = resolve_tag_names_to_ids(client, cmd.add_tags)
        if len(tag_ids) > 1:
            print("Error: Bulk add operation only supports one tag at a time")
            return

        bulk_request = BulkEditRequest(
            documents=[doc.id for doc in valid_docs],
            method="add_tag",
            parameters={"tag": tag_ids[0]},
        )
        print(f"Adding tag '{cmd.add_tags}' to {len(valid_docs)} documents...")

    elif cmd.remove_tags:
        tag_ids = resolve_tag_names_to_ids(client, cmd.remove_tags)
        if len(tag_ids) > 1:
            print("Error: Bulk remove operation only supports one tag at a time")
            return

        bulk_request = BulkEditRequest(
            documents=[doc.id for doc in valid_docs],
            method="remove_tag",
            parameters={"tag": tag_ids[0]},
        )
        print(f"Removing tag '{cmd.remove_tags}' from {len(valid_docs)} documents...")
    else:
        print("Error: No operation specified (use --add-tags or --remove-tags)")
        return

    # Execute bulk operation
    result = client.bulk_edit_documents(bulk_request)
    print(f"✓ Updated {len(result.affected_documents)} documents")
