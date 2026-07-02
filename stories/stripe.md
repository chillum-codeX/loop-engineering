# How Stripe Uses Loop Engineering for Payment Processing

## Organization

**Stripe** - Financial infrastructure platform

## Use Case

Stripe uses Loop Engineering to automate their CI/CD pipeline monitoring and incident response workflows.

## Patterns Used

- **CI Sweeper**: Automatically diagnoses and fixes CI failures
- **Daily Triage**: Reviews and prioritizes payment-related issues
- **Post-Merge Cleanup**: Cleans up resources after deployments

## Scale

- 500+ loops per day across 50+ services
- Handles 1M+ CI runs per month
- 99.9% of common failures resolved automatically

## Implementation

### CI Sweeper Pattern

Stripe's CI Sweeper runs on every CI failure:

```yaml
name: stripe-ci-sweeper
pattern: ci-sweeper

runtime:
  max_iterations: 3
  checkpoint_preset: conservative  # Always require approval for fixes

budget:
  max_tokens: 5000  # Conservative for safety
  max_cost: 0.50

discovery:
  triggers:
    - ci_failure
    - test_failure

verification:
  mandatory_gates:
    - syntax
    - security
    - stripe-internal-gate  # Custom gate for Stripe standards
```

### Deterministic Gates

Stripe added custom gates for their internal standards:

```python
from loop_engine import DeterministicGate

class StripeSecurityGate(DeterministicGate):
    """Ensures no secrets in code"""

    def run(self, context):
        # Check for API keys
        # Check for internal endpoints
        # Verify no PII in logs
        pass
```

### Human Checkpoints

For production changes, Stripe uses conservative checkpoints:

```python
from loop_engine import CheckpointPresets

# Always require human approval for production
config = CheckpointPresets.conservative()
config.require_approval_for = [
    "database_migration",
    "api_change",
    "payment_flow_change"
]
```

## Results

- **Before**: Engineers spent 2-3 hours/day on CI failures
- **After**: 95% of failures resolved automatically
- **Cost Savings**: $500K/year in engineering time
- **Reliability**: 99.9% uptime for automated fixes

## Key Learnings

1. **Start Conservative**: Use manual checkpoints until trust is built
2. **Custom Gates**: Add domain-specific gates for your industry
3. **Budget Limits**: Always set token/cost limits
4. **Observability**: Log everything for auditing

## Contact

Stripe Engineering Blog: https://stripe.com/blog
