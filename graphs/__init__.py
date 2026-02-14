"""
AI-crew Graphs Package
======================

Contains LangGraph graph definitions.

Available graphs:
  - ``dev_team``      - Full development pipeline (PM -> Analyst -> Architect -> Developer -> QA)
  - ``simple_dev``    - Quick development (Developer -> git_commit)
  - ``standard_dev``  - Standard development (PM -> Developer -> Reviewer -> git_commit)
  - ``research``      - Web research and analysis (Researcher -> report)
  - ``qa_agent_test`` - QA testing scenario (Developer -> QA -> report)

Aegra loads graphs via importlib from ``aegra.json`` config,
so direct imports from this package are not required at runtime.
"""
