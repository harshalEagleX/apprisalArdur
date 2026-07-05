"""
QC rule engine — transaction-level quality control over appraisal documents.

Public entry point: app.qc.transaction.run_transaction_qc_paths(appraisal, ...)
— the file-paths QC path invoked by the Java backend via /qc/process and the
Celery worker. Importing app.qc.rules registers all rules with the registry.
"""
