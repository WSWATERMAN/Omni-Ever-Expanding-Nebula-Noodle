"""Planning support for compensating actions; this package never executes them."""

from .planner import RollbackAction, RollbackPlan, RollbackPlanner, OperationKind

__all__ = ["RollbackAction", "RollbackPlan", "RollbackPlanner", "OperationKind"]
