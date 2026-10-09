"""Aadesh AWS adapters — thin I/O layer over aadesh_core.

Lambda handlers:
  - api_handler.py — Main API Gateway handler (HTTP routes)
  - ingest_handler.py — EventBridge-triggered AQI ingestion
  - resolve_handler.py — Obligation resolution (pure deterministic core)
  - standing_order_handler.py — Standing Order CRUD
  - parchi_ack_handler.py — Worker Parchi acknowledgment
  - task_waiter.py — Step Functions wait-for-ack task
  - parchi_creation_handler.py — Step Functions: create Parchis
  - parchi_seal_handler.py — Step Functions: seal acknowledged Parchis
  - audit_handler.py — Step Functions: final audit record
  - stage_trip_handler.py — Step Functions: determine invoked stage

Every handler is a thin adapter. Business logic lives in aadesh_core,
which has zero AWS imports. Same core runs locally, in tests, and here.
"""
