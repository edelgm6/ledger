"""Guardrail constants and action vocabulary shared across the recharacterize
service package.

The only mutations allowed are setting/clearing an item's entity and swapping one
account for another. Amounts and debit/credit type are never touched, so the
per-journal-entry balance is structurally preserved.
"""

from api.models import Account, JournalEntryItem

# Starting-equity, retained-earnings, and unrealized-gains accounts are derived
# by statement and reconciliation logic (see api/statement.py cash-flow logic
# and Reconciliation.plug_investment_change), so their balances must never be
# moved by an account swap. Their items may still be re-tagged with an entity —
# entity tagging never touches a balance — so this set blocks account swaps only.
SWAP_BLOCKED_SPECIAL_TYPES = [
    Account.SpecialType.UNREALIZED_GAINS_AND_LOSSES,
    Account.SpecialType.STARTING_EQUITY,
]
SWAP_BLOCKED_SUB_TYPES = [
    Account.SubType.RETAINED_EARNINGS,
    Account.SubType.UNREALIZED_INVESTMENT_GAINS,
]

VALID_ENTRY_TYPES = {
    JournalEntryItem.JournalEntryType.DEBIT,
    JournalEntryItem.JournalEntryType.CREDIT,
}
ACTION_SET_ENTITY = "set_entity"
ACTION_CLEAR_ENTITY = "clear_entity"
ACTION_CHANGE_ACCOUNT = "change_account"
# A view operation only inspects the matched items; it never mutates the ledger,
# so it carries no Apply button and cannot be applied.
ACTION_VIEW = "view"

MUTATING_ACTIONS = {ACTION_SET_ENTITY, ACTION_CLEAR_ENTITY, ACTION_CHANGE_ACCOUNT}

SAMPLE_LIMIT = 25

# Revert is a near-term "oops" safety net, not a permanent audit log. Each apply
# records a RecharacterizeChange plus one RecharacterizeChangeItem per affected
# item, so we cap the history to the most recent N applied changes and prune the
# rest (cascading their items) to keep the snapshot tables bounded over time.
RECHARACTERIZE_HISTORY_LIMIT = 50
