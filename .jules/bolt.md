
## 2023-10-24 - N+1 Query in `list_call_logs`
**Learning:** Found a severe N+1 query issue in the `list_call_logs` endpoint within `app/routers/admin.py`. The endpoint was iterating over all `CallLog` entries and making a separate query for the `CallMessage`s of each log. Given that the relationship is set up with an `order_by="CallMessage.sequence"`, we can simply use `selectinload(CallLog.messages)` to fetch and correctly order all messages for all logs in a single query.
**Action:** Always prefer SQLAlchemy's eager loading strategies like `selectinload` for relationships (especially 1-to-many like `CallLog.messages`) when iterating over collections, to reduce queries from O(N) to O(1).
