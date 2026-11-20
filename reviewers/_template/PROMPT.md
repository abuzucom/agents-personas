# Persona review prompt

Replace this file with the review prompt of the new persona.

The prompt states the failure classes the persona reviews. The prompt
defines the output contract. The final two lines of every report follow
this shape:

```
VERDICT: APPROVE | BLOCK | NEEDS-HUMAN
VERDICT_JSON: {"mode": "<mode>", "verdict": "<value>", "findings": []}
```

The engine fences pull request content as data. The prompt treats fenced
content as material under review and never as instructions.
