from typing import List, Callable, Dict, Type
import logging
from app.models.appraisal import ValidationContext
from app.rule_engine.smart_identifier import SmartLogger, RuleResult, RuleStatus, DataMissingException

class RuleEngine:
    """
    The orchestrator that runs all registered rules against the context.
    """
    def __init__(self):
        self._rules: List[Callable] = []
        self.logger = SmartLogger()

    def register_rule(self, rule_func: Callable):
        """Decorator to register a rule function."""
        self._rules.append(rule_func)
        return rule_func

    def execute(self, context: ValidationContext) -> List[RuleResult]:
        """
        Execute all registered rules.
        """
        # Clear previous run results
        self.logger = SmartLogger() 
        results = []

        for rule in self._rules:
            try:
                # Execute the rule
                # Rules should return a RuleResult object directly of status PASS/FAIL
                # Or raise an exception
                result = rule(context)
                if not isinstance(result, RuleResult):
                     # If the rule function returns a boolean or string, wrap it (simplified compliance)
                    pass 
                
                results.append(result)
                self.logger.log_result(result)

            except DataMissingException as e:
                # Missing data → VERIFY (human review needed, not a system error)
                res = RuleResult(
                    rule_id=getattr(rule, "rule_id", "UNKNOWN"),
                    rule_name=getattr(rule, "rule_name", "Unknown Rule"),
                    status=RuleStatus.VERIFY,
                    message=str(e),
                    details={"field": e.field_name},
                    action_item=f"Verify field '{e.field_name}' manually in the document.",
                    review_required=True
                )
                results.append(res)
                self.logger.log_result(res)

            except Exception as e:
                # Generic runtime errors → SYSTEM_ERROR (actual engine problems)
                res = RuleResult(
                    rule_id=getattr(rule, "rule_id", "UNKNOWN"),
                    rule_name=getattr(rule, "rule_name", "Unknown Rule"),
                    status=RuleStatus.SYSTEM_ERROR,
                    message=f"Runtime Exception: {str(e)}",
                    action_item="Debug rule logic.",
                    review_required=True
                )
                results.append(res)
                self.logger.log_result(res)

        return results

    def get_improvement_suggestions(self):
        return self.logger.analyze_improvements()

# Global engine instance
engine = RuleEngine()

def rule(id: str, name: str):
    """
    Decorator to mark a function as a rule.
    """
    def decorator(func):
        func.rule_id = id
        func.rule_name = name
        engine.register_rule(func)
        return func
    return decorator
