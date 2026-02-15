I want to build an API for creating journal entries that is usable by Claude Code. I.e., it should be easy for me to build out a separate MCP server for this API.

I want this to have the following features —
* Call an API endpoint to GET all transactions and any important related objects attached to them. I should be able to filter for open v. closed and the originating Account
* Call an endpoint to POST journal entries, both one at a time or in bulk. Note: it's critical that these POST operations use the atomic feature to avoid partial updates and follow all of the critical rules around journal entries (debits + credits have to balance, one debit or credit has to equal the amount of the transaction, etc.)
* When creating journal entries, I should be able to pass in an optional identifier. This should default to 'user' but I should be able to override this (e.g., to say 'Claude')
* There has to be obvious security — can only access with a key