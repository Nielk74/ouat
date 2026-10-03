"""Small hypothetical problem stories; data only, independent of the renderer."""


def _node(identifier, label, kind="generic", **fields):
    return {"id": identifier, "label": label, "kind": kind,
            "status": "unchanged", **fields}


def _edge(source, target, label, **fields):
    return {"from": source, "to": target, "label": label,
            "status": "unchanged", **fields}


def _demo(identifier, title, nodes, edges, **fields):
    return {"id": identifier, "title": title,
            "visual": {"template": "flow", "nodes": nodes, "edges": edges, **fields}}


def problem_demos():
    """Return fresh stories with visible mechanisms and short, concrete labels."""
    return [
        _demo(
            "problem-timeout", "Why did work finish after a timeout?",
            [_node("caller", "Caller", "client"),
             _node("worker", "Export worker", "worker"),
             _node("file", "Export file", "storage")],
            [_edge("caller", "worker", "Start export", transport="request"),
             _edge("worker", "file", "Save file", transport="write")],
            scenario={"template": "timeout", "from": "caller", "at": "worker", "to": "file",
                      "condition": "The caller's deadline expires.",
                      "cause": "Timeout ends the wait without cancelling the worker.",
                      "consequence": "The caller times out; the export completes and its file is available."},
        ),
        _demo(
            "problem-duplicate-effect", "Why was the order charged twice?",
            [_node("client", "Client", "client", meta="Order #42"),
             _node("payment", "Payment service", "service", meta="No deduplication"),
             _node("ledger", "Charge ledger", "database", meta="Order #42")],
            [_edge("client", "payment", "Charge Order #42", transport="request"),
             _edge("payment", "ledger", "Record charge", transport="write"),
             _edge("payment", "client", "Acknowledgement lost", transport="request",
                   issue="The charge succeeds, but its acknowledgement never reaches the client.")],
            scenario={"template": "duplicate-effect", "from": "client", "at": "payment", "to": "ledger",
                      "subject": "Order #42",
                      "condition": "The acknowledgement is lost after the charge succeeds.",
                      "cause": "The client retries the same order; the service has no deduplication key.",
                      "consequence": "Both attempts charge Order #42."},
        ),
        _demo(
            "problem-out-of-order", "Why do the results show an older search?",
            [_node("browser", "Browser", "client", meta="Current query: cat"),
             _node("search", "Search service", "service"),
             _node("results", "Visible results", "generic")],
            [_edge("browser", "search", "Search ca", transport="request"),
             _edge("browser", "search", "Search cat", transport="request"),
             _edge("search", "results", "cat returns first", transport="read"),
             _edge("search", "results", "ca returns later", transport="read")],
            scenario={"template": "out-of-order", "from": "browser", "at": "search", "to": "results",
                      "earlier": "ca", "later": "cat",
                      "condition": "The older search responds after the newer search.",
                      "cause": "Every response replaces the results without a freshness check.",
                      "consequence": "The input says cat, but the displayed results belong to ca."},
        ),
        _demo(
            "problem-partial-failure", "Why does the account exist without its email?",
            [_node("signup", "Signup", "function"),
             _node("account", "Account record", "database"),
             _node("email", "Welcome email", "message")],
            [_edge("signup", "account", "Create account", transport="write"),
             _edge("signup", "email", "Send email", transport="message")],
            scenario={"template": "partial-failure", "from": "signup", "at": "account", "to": "email",
                      "condition": "The email step fails after the account is created.",
                      "cause": "Account creation commits before email delivery is attempted.",
                      "consequence": "The account exists, but this attempt sends no welcome email."},
        ),
        _demo(
            "problem-lost-update", "Why did two increments add only one?",
            [_node("counter", "Shared counter", "database", meta="Stored 11; expected 12",
                   issue="Both workers read 10 and write 11; one increment is lost."),
             _node("worker-a", "Worker A", "worker", meta="Read 10; write 11"),
             _node("worker-b", "Worker B", "worker", meta="Read 10; write 11")],
            [_edge("counter", "worker-a", "Read 10", transport="read"),
             _edge("counter", "worker-b", "Read 10", transport="read"),
             _edge("worker-a", "counter", "Write 11", transport="write"),
             _edge("worker-b", "counter", "Write 11", transport="write")],
            caption="Both reads happen before either write.",
        ),
        _demo(
            "problem-deadlock", "Why can neither task continue?",
            [_node("task-a", "Task A", "worker",
                   issue="A keeps X while waiting for Y."),
             _node("lock-x", "Lock X"),
             _node("task-b", "Task B", "worker",
                   issue="B keeps Y while waiting for X."),
             _node("lock-y", "Lock Y")],
            [_edge("lock-x", "task-a", "Held by A"),
             _edge("task-a", "lock-y", "Waits for Y"),
             _edge("lock-y", "task-b", "Held by B"),
             _edge("task-b", "lock-x", "Waits for X")],
            caption="Neither task releases its first lock before obtaining the other.",
        ),
        _demo(
            "problem-poison-message", "Why does this job keep failing?",
            [_node("queue", "Job queue", "queue", meta="Message #7"),
             _node("worker", "Worker", "worker",
                   issue="The account ID is missing; retrying the unchanged message cannot fix it.")],
            [_edge("queue", "worker", "Fetch invalid job", transport="message"),
             _edge("worker", "queue", "Requeue unchanged", transport="message")],
            sequence=[{"edge": 1, "label": "Fetch #7"},
                      {"edge": 2, "label": "Reject and requeue"},
                      {"edge": 1, "label": "Fetch #7 again"},
                      {"edge": 2, "label": "Reject and requeue"}],
        ),
        _demo(
            "problem-queue-mismatch", "Why are accepted jobs not processed?",
            [_node("producer", "Producer", "service"),
             _node("new-queue", "jobs.v2", "queue", meta="Jobs accumulate",
                   issue="The consumer listens to a different queue."),
             _node("old-queue", "jobs.v1", "queue", meta="Empty"),
             _node("consumer", "Consumer", "worker")],
            [_edge("producer", "new-queue", "Publish to jobs.v2", transport="message"),
             _edge("old-queue", "consumer", "Listen on jobs.v1", transport="message")],
        ),
        _demo(
            "problem-early-ack", "Why was the job lost?",
            [_node("ack", "Acknowledge job", "queue", meta="Removed from queue"),
             _node("crash", "Worker crashes", "process", meta="Before saving"),
             _node("missing", "Result missing", "storage",
                   issue="No result was saved; acknowledgement prevents redelivery.")],
            [_edge("ack", "crash", "Then crash", transport="flow"),
             _edge("crash", "missing", "No redelivery", transport="flow")],
        ),
    ]
