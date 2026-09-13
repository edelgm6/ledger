import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)

from api.models import Account, Entity, Transaction
from api.rest_api.serializers import (
    AccountSerializer,
    BulkJournalEntryInputSerializer,
    EntitySerializer,
    JournalEntryInputSerializer,
    TransactionSerializer,
)
from api.services.rest_api_services import (
    bulk_create_journal_entries,
    create_journal_entry_from_api,
)


class TransactionListView(APIView):
    """GET /api/v1/transactions/ — list transactions with optional filters."""

    def get(self, request):
        queryset = Transaction.objects.select_related(
            "account", "suggested_account", "suggested_entity"
        ).order_by("-date")

        # Filter by is_closed
        is_closed = request.query_params.get("is_closed")
        if is_closed is not None:
            queryset = queryset.filter(is_closed=is_closed.lower() == "true")

        # Filter by account name
        account_name = request.query_params.get("account")
        if account_name:
            queryset = queryset.filter(account__name=account_name)

        # Filter by transaction type
        transaction_type = request.query_params.get("type")
        if transaction_type:
            queryset = queryset.filter(type=transaction_type)

        # Filter by linked transaction
        linked = request.query_params.get("linked")
        if linked is not None:
            has_linked = linked.lower() == "true"
            queryset = queryset.filter(linked_transaction__isnull=not has_linked)

        serializer = TransactionSerializer(queryset, many=True)
        return Response(
            {"count": len(serializer.data), "transactions": serializer.data}
        )


class AccountListView(APIView):
    """GET /api/v1/accounts/ — list accounts with optional filters."""

    def get(self, request):
        queryset = Account.objects.select_related("entity").order_by("name")

        is_closed = request.query_params.get("is_closed")
        if is_closed is not None:
            queryset = queryset.filter(is_closed=is_closed.lower() == "true")

        account_type = request.query_params.get("type")
        if account_type:
            queryset = queryset.filter(type=account_type)

        serializer = AccountSerializer(queryset, many=True)
        return Response(
            {"count": len(serializer.data), "accounts": serializer.data}
        )


class EntityListView(APIView):
    """GET /api/v1/entities/ — list entities with optional filters."""

    def get(self, request):
        queryset = Entity.objects.order_by("name")

        is_closed = request.query_params.get("is_closed")
        if is_closed is not None:
            queryset = queryset.filter(is_closed=is_closed.lower() == "true")

        serializer = EntitySerializer(queryset, many=True)
        return Response(
            {"count": len(serializer.data), "entities": serializer.data}
        )


class JournalEntryCreateView(APIView):
    """POST /api/v1/journal-entries/ — create single or bulk journal entries."""

    def post(self, request):
        # Detect single vs bulk by checking for 'journal_entries' key
        if "journal_entries" in request.data:
            return self._handle_bulk(request)
        return self._handle_single(request)

    @staticmethod
    def _created_or_error(create, log_message):
        """Runs a creation service and maps its outcome to a response.

        The services raise ValueError for anything the caller can fix (unknown
        transaction, already closed, unbalanced) and let everything else
        surface as a 500. Both entry points handle it identically, so the
        handling lives here once.
        """
        try:
            result = create()
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception(log_message)
            return Response(
                {"error": "An internal error occurred."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        return Response(result, status=status.HTTP_201_CREATED)

    def _handle_single(self, request):
        serializer = JournalEntryInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        return self._created_or_error(
            lambda: create_journal_entry_from_api(
                transaction_id=data["transaction_id"],
                debits_data=data["debits"],
                credits_data=data["credits"],
                created_by=data["created_by"],
            ),
            "Unexpected error creating journal entry",
        )

    def _handle_bulk(self, request):
        serializer = BulkJournalEntryInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entries_data = serializer.validated_data["journal_entries"]

        return self._created_or_error(
            lambda: bulk_create_journal_entries(entries_data),
            "Unexpected error in bulk journal entry creation",
        )
