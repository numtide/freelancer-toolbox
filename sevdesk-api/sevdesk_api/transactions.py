"""Check Account Transaction operations for SevDesk API."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datetime import datetime

    from .client import SevDeskClient


class TransactionOperations:
    """Operations for check account transactions in SevDesk."""

    def __init__(self, client: SevDeskClient) -> None:
        """Initialize transaction operations.

        Args:
            client: The SevDesk client instance
        """
        self.client = client

    def get_transactions(
        self,
        check_account_id: int | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        status: int | None = None,
        limit: int | None = None,
        offset: int | None = None,
        embed: list[str] | None = None,
    ) -> dict[str, Any]:
        """Get check account transactions.

        Args:
            check_account_id: Filter by check account
            start_date: Filter by start date
            end_date: Filter by end date
            status: Filter by status (100=Created, 200=Linked, 300=Private, 400=Booked)
            limit: Limit number of results
            offset: Skip number of results
            embed: Embed related objects

        Returns:
            Response with transactions
        """
        params: dict[str, Any] = {}
        if check_account_id is not None:
            params["checkAccount[id]"] = check_account_id
            params["checkAccount[objectName]"] = "CheckAccount"
        if start_date:
            params["startDate"] = int(start_date.timestamp())
        if end_date:
            params["endDate"] = int(end_date.timestamp())
        if status is not None:
            params["status"] = status
        if limit is not None:
            params["limit"] = limit
        if offset is not None:
            params["offset"] = offset
        if embed:
            params["embed"] = ",".join(embed)

        return self.client.get("CheckAccountTransaction", params=params)

    def get_transaction(self, transaction_id: int) -> dict[str, Any]:
        """Get a specific check account transaction.

        Args:
            transaction_id: ID of the transaction

        Returns:
            Transaction data
        """
        return self.client.get(f"CheckAccountTransaction/{transaction_id}")

    def create_transaction(
        self,
        check_account_id: int,
        value_date: datetime,
        amount: float,
        status: int,
        payee_payer_name: str,
        entry_date: datetime | None = None,
        paymt_purpose: str | None = None,
        payee_payer_acct_no: str | None = None,
        payee_payer_bank_code: str | None = None,
    ) -> dict[str, Any]:
        """Create a new check account transaction.

        Args:
            check_account_id: ID of the check account
            value_date: Date the transaction was booked
            amount: Amount of the transaction
            status: Status (100=Created, 200=Linked, 300=Private, 400=Booked)
            payee_payer_name: Name of the other party
            entry_date: Date the transaction was imported (optional)
            paymt_purpose: Purpose of payment (optional)
            payee_payer_acct_no: IBAN or account number of other party (optional)
            payee_payer_bank_code: BIC or bank code of other party (optional)

        Returns:
            Created transaction data
        """
        data = {
            "checkAccount": {
                "id": check_account_id,
                "objectName": "CheckAccount",
            },
            "valueDate": value_date.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
            "amount": amount,
            "status": status,
            "payeePayerName": payee_payer_name,
        }

        if entry_date:
            data["entryDate"] = entry_date.strftime("%Y-%m-%dT%H:%M:%S+00:00")
        if paymt_purpose:
            data["paymtPurpose"] = paymt_purpose
        if payee_payer_acct_no:
            data["payeePayerAcctNo"] = payee_payer_acct_no
        if payee_payer_bank_code:
            data["payeePayerBankCode"] = payee_payer_bank_code

        return self.client.post("CheckAccountTransaction", json_data=data)

    def update_transaction(
        self,
        transaction_id: int,
        value_date: datetime | None = None,
        entry_date: datetime | None = None,
        amount: float | None = None,
        payee_payer_name: str | None = None,
        paymt_purpose: str | None = None,
        payee_payer_acct_no: str | None = None,
        payee_payer_bank_code: str | None = None,
    ) -> dict[str, Any]:
        """Update an existing check account transaction.

        Args:
            transaction_id: ID of the transaction to update
            value_date: Date the transaction was booked
            entry_date: Date the transaction was imported
            amount: Amount of the transaction
            payee_payer_name: Name of the other party
            paymt_purpose: Purpose of payment
            payee_payer_acct_no: IBAN or account number of other party
            payee_payer_bank_code: BIC or bank code of other party

        Returns:
            Updated transaction data
        """
        data: dict[str, Any] = {}

        if value_date:
            data["valueDate"] = value_date.strftime("%Y-%m-%dT%H:%M:%S+00:00")
        if entry_date:
            data["entryDate"] = entry_date.strftime("%Y-%m-%dT%H:%M:%S+00:00")
        if amount is not None:
            data["amount"] = amount
        if payee_payer_name:
            data["payeePayerName"] = payee_payer_name
        if paymt_purpose:
            data["paymtPurpose"] = paymt_purpose
        if payee_payer_acct_no:
            data["payeePayerAcctNo"] = payee_payer_acct_no
        if payee_payer_bank_code:
            data["payeePayerBankCode"] = payee_payer_bank_code

        return self.client.put(
            f"CheckAccountTransaction/{transaction_id}", json_data=data
        )

    def delete_transaction(self, transaction_id: int) -> dict[str, Any]:
        """Delete a check account transaction.

        Args:
            transaction_id: ID of the transaction to delete

        Returns:
            Response data
        """
        return self.client.delete(f"CheckAccountTransaction/{transaction_id}")
